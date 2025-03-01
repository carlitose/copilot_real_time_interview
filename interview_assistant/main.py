#!/usr/bin/env python3
"""
Startup module for the Interview Assistant application.
Creates and launches the application user interface.
"""

import sys
import logging
from PyQt5.QtWidgets import QApplication
from .intervista_assistant import InterviewAssistant

# Logging configuration
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   filename='app.log')
logger = logging.getLogger(__name__)

def main():
    """Main function to start the application."""
    try:
        app = QApplication(sys.argv)
        window = InterviewAssistant()
        window.show()
        logger.info("Interview Assistant application started successfully")
        sys.exit(app.exec_())
    except Exception as e:
        logger.error(f"Error during application startup: {e}")
        raise

if __name__ == "__main__":
    main() 