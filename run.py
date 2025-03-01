#!/usr/bin/env python3
"""
Startup script for Intervista Assistant.
This script runs the application from the main directory.
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
                logging.FileHandler("intervista_assistant.log"),
                logging.StreamHandler()
            ]
        )
        logger = logging.getLogger(__name__)
        
        # Startup message
        logger.info("Starting Intervista Assistant...")
        
        # Import and run the application
        from intervista_assistant.main import main
        main()
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Ensure all required dependencies are installed.")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)
        
    except Exception as e:
        print(f"Error during startup: {e}")
        sys.exit(1) 