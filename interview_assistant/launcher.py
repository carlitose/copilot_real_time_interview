#!/usr/bin/env python3
"""
Launcher for Interview Assistant.
Allows running the application from the main directory.
"""

import os
import sys
from pathlib import Path

# Add main directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

if __name__ == "__main__":
    # Import and start application
    from interview_assistant.main import main
    
    # Run application
    main() 