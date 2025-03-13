#!/usr/bin/env python3
"""
Flask application initialization for Intervista Assistant API.
Initializes the Flask app and Socket.IO server.
"""
import os
import logging
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

# Import from our modules
from intervista_assistant.api.routes import register_routes
from intervista_assistant.api.socketio_handlers import register_socketio_handlers

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log'),
        logging.StreamHandler()  # Added console handler
    ]
)
logger = logging.getLogger(__name__)
logger.info("Backend server started")

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Initialize Socket.IO
    socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
    
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