#!/usr/bin/env python3
"""
Startup script for Intervista Assistant Desktop App.
This script runs the desktop application from the main directory.
"""

import os
import sys
import logging

if __name__ == "__main__":
    try:
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("desktop_app.log"),
                logging.StreamHandler()
            ]
        )
        logger = logging.getLogger(__name__)
        
        # Startup message
        logger.info("Starting Intervista Assistant Desktop App...")
        
        # Import and run the application
        from desktop_app.main import main
        main()
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Ensure all required dependencies are installed.")
        print("Run: cd desktop_app && poetry install")
        sys.exit(1)
        
    except Exception as e:
        print(f"Error during startup: {e}")
        sys.exit(1) 