#!/usr/bin/env python3
"""
Startup script for Interview Assistant.
This is the main entry point for the application.
"""

import sys
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("interview_assistant.log"),
    ]
)
logger = logging.getLogger(__name__)

# Main execution
try:
    logger.info("Starting Interview Assistant...")
    # Add project directory to path
    sys.path.insert(0, str(Path(__file__).parent))
    from interview_assistant.main import main
    main()
except ImportError as e:
    logger.error(f"Import error: {e}")
    print(f"Import error: {e}")
    print("Make sure all dependencies are installed.")
    sys.exit(1)
except Exception as e:
    logger.error(f"Startup error: {e}")
    print(f"Startup error: {e}")
    sys.exit(1) 