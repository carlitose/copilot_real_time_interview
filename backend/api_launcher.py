#!/usr/bin/env python3
"""
API launcher for Intervista Assistant.
Provides a simple way to start the API server with robust configuration options.
"""
import os
import sys
import logging
import argparse
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Add current directory to path to import local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log'),
        logging.StreamHandler()  # Add console handler
    ]
)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Intervista Assistant API Server')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)), 
                        help='Port to run the server on')
    parser.add_argument('--host', type=str, default=os.environ.get('HOST', '0.0.0.0'), 
                        help='Host to bind the server to')
    parser.add_argument('--debug', action='store_true', default=os.environ.get('DEBUG', 'false').lower() == 'true',
                        help='Run in debug mode')
    parser.add_argument('--no-reloader', action='store_true', 
                        help='Disable the automatic reloader')
    return parser.parse_args()

def main():
    """Main entry point for the API server."""
    # Parse command line arguments
    args = parse_arguments()
    
    port = args.port
    host = args.host
    debug = args.debug
    use_reloader = not args.no_reloader and debug
    
    # Environment variables will override defaults if not explicitly set in args
    if not sys.argv[1:]:  # No command line args provided
        port = int(os.environ.get("PORT", 8000))
        debug = os.environ.get("DEBUG", "false").lower() == "true"
        use_reloader = os.environ.get("FLASK_RELOADER", "1" if debug else "0") == "1"
    
    # Configuration for watchdog
    extra_files = []
    
    # Configuration for improved reloader with watchdog
    if use_reloader:
        try:
            import watchdog
            reloader_type = "watchdog"
            logger.info("Using watchdog for reloader - optimized automatic restart")
        except ImportError:
            reloader_type = "stat"
            logger.warning("watchdog not available, using standard reloader")
    else:
        reloader_type = None
    
    try:
        # Import the flask application
        from backend.flask_app import create_app
        
        # Create the application
        app, socketio = create_app()
        
        # Apply ProxyFix middleware
        app.wsgi_app = ProxyFix(app.wsgi_app)
        
        # Configure logging for flask components
        if debug:
            logging.getLogger('werkzeug').setLevel(logging.INFO)
            # Reduce verbosity of engineio and socketio loggers
            logging.getLogger('engineio').setLevel(logging.WARNING)
            logging.getLogger('socketio').setLevel(logging.WARNING)
            
            print(f"Server running in debug mode with reloader {'enabled' if use_reloader else 'disabled'}")
            if use_reloader:
                print(f"Reloader type: {reloader_type}")
        
        # Start the server
        logger.info(f"Starting API server on {host}:{port}")
        
        # Use socketio to run the server
        socketio.run(
            app,
            debug=debug,
            host=host,
            port=port,
            use_reloader=use_reloader,
            reloader_type=reloader_type,
            extra_files=extra_files,
            allow_unsafe_werkzeug=True,
            log_output=False  # Disable logging of all Socket.IO events
        )
        
    except Exception as e:
        logger.error(f"Error starting API server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()