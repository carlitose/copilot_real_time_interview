#!/usr/bin/env python3
"""
Flask application initialization for Intervista Assistant API.
Initializes the Flask app and Socket.IO server.
"""
import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import jwt
from dotenv import load_dotenv

# Load environment variables from .env files
load_dotenv()  # First load from .env if exists
load_dotenv('.env.local', override=True)  # Then load from .env.local, overriding if needed

# Import from our modules
from intervista_assistant.api.routes import register_routes
from intervista_assistant.api.socketio_handlers import register_socketio_handlers

# Logging configuration
logging.basicConfig(
    level=logging.INFO if os.getenv('DEBUG', 'false').lower() == 'true' else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log'),
        logging.StreamHandler()  # Added console handler
    ]
)
logger = logging.getLogger(__name__)
logger.info("Backend server started")

# JWT settings
JWT_SECRET = os.environ.get('JWT_SECRET', 'super-secret-jwt-token-with-at-least-32-characters-long')
logger.info(f"Using JWT_SECRET: {'custom value' if os.environ.get('JWT_SECRET') else 'default value'}")

def verify_token(token):
    """Verifies the JWT token."""
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
            
        # Decode and validate the token
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Initialize Socket.IO
    socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
    
    # Middleware to validate token for HTTP requests
    @app.before_request
    def validate_token():
        # Skip token validation for OPTIONS requests (preflight)
        if request.method == 'OPTIONS':
            return
            
        # Skip token validation for login/signup
        if request.path.startswith('/api/auth'):
            return
            
        # Get token from headers
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            logger.warning("No Authorization header found")
            return jsonify({'error': 'Authorization header is required'}), 401
            
        # Verify token
        payload = verify_token(auth_header)
        if not payload:
            logger.warning("Invalid token")
            return jsonify({'error': 'Invalid token'}), 401
            
        # Store user info in request context
        request.user_id = payload.get('sub')
        request.user_role = payload.get('role')
        
        # Get OpenAI API key from request
        if request.is_json:
            data = request.get_json()
            if data and 'openai_api_key' in data:
                request.openai_api_key = data.get('openai_api_key')
                # Remove from payload to avoid leaking it in logs
                data_copy = data.copy()
                del data_copy['openai_api_key']
                logger.debug(f"Request data (sanitized): {data_copy}")
        
        # Use system OpenAI API key if provided and user didn't provide one
        if not hasattr(request, 'openai_api_key') and os.environ.get('OPENAI_API_KEY'):
            request.openai_api_key = os.environ.get('OPENAI_API_KEY')
            logger.debug("Using system OpenAI API key")
    
    # Socket.IO authentication middleware
    @socketio.on('connect')
    def handle_connect():
        logger.info("Socket.IO connection attempt")
        
        # Get auth token from request arguments
        auth_token = request.args.get('token')
        
        # If no token in args, check for the auth header
        if not auth_token:
            auth_header = request.headers.get('Authorization')
            if auth_header:
                # Extract token from Bearer format
                if auth_header.startswith('Bearer '):
                    auth_token = auth_header[7:]
        
        # Validate token
        if not auth_token:
            logger.warning("Socket.IO connection rejected: No auth token")
            return False  # Reject the connection
            
        payload = verify_token(auth_token)
        if not payload:
            logger.warning("Socket.IO connection rejected: Invalid token")
            return False  # Reject the connection
            
        # Store user info for this connection
        request.user_id = payload.get('sub')
        request.user_role = payload.get('role')
        
        logger.info(f"Socket.IO connection established for user {request.user_id}")
        return True  # Accept the connection
    
    # Register API routes
    register_routes(app)
    
    # Register Socket.IO handlers
    register_socketio_handlers(socketio)
    
    return app, socketio

def run_server(host='0.0.0.0', port=8000, debug=True):
    """Run the Flask server with the given configuration."""
    app, socketio = create_app()
    
    # Start the server
    logger.info(f"Starting server on {host}:{port}, debug={debug}")
    socketio.run(app, debug=debug, host=host, port=port)

if __name__ == '__main__':
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    run_server(port=port, debug=debug) 