#!/usr/bin/env python3
"""
Launcher for the Intervista Assistant API Server.
"""

import os
import sys
import logging
from werkzeug.middleware.proxy_fix import ProxyFix

# Add current directory to path to import local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log'),
        logging.StreamHandler()  # Add console handler
    ]
)

# Now import the app from intervista_assistant.api
from intervista_assistant.api import app, socketio

def main():
    """Entry point to start the API server."""
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"  # Debug mode enabled by default
    use_reloader = os.environ.get("FLASK_RELOADER", "1") == "1"  # Reloader enabled by default
    
    # Configuration for watchdog
    extra_files = []
    
    # Configuration for improved reloader with watchdog
    if use_reloader:
        try:
            import watchdog
            reloader_type = "watchdog"
            logging.info("Using watchdog for reloader - optimized automatic restart")
            
            # Add extra files to monitor here
            # For example: extra_files.append("config.json")
            
        except ImportError:
            reloader_type = "stat"
            logging.warning("watchdog not available, using standard reloader")
    else:
        reloader_type = None
    
    app.wsgi_app = ProxyFix(app.wsgi_app)
    
    # Configure logging for flask
    if debug:
        logging.getLogger('werkzeug').setLevel(logging.INFO)
        # Modifichiamo il livello di logging per engineio e socketio
        # da INFO a WARNING per evitare log troppo verbosi
        logging.getLogger('engineio').setLevel(logging.WARNING)
        logging.getLogger('socketio').setLevel(logging.WARNING)
        
        print(f"Server running in debug mode with reloader {'enabled' if use_reloader else 'disabled'}")
        if use_reloader:
            print(f"Reloader type: {reloader_type}")
    
    # Use socketio to run the server instead of app.run()
    socketio.run(
        app,
        debug=debug,
        host="0.0.0.0",
        port=port,
        use_reloader=use_reloader,
        reloader_type=reloader_type,
        extra_files=extra_files,
        allow_unsafe_werkzeug=True,
        log_output=False  # Disabilitiamo il logging di tutti gli eventi Socket.IO
    )

if __name__ == "__main__":
    main()