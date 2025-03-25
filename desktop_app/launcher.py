#!/usr/bin/env python3
"""
Launcher for Intervista Assistant.
Allows running the application from the main directory.
"""

import os
import sys
from pathlib import Path

# Add the main directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

if __name__ == "__main__":
    # Import and start the application
    from desktop_app.main import main
    
    # Run the application
    main() 