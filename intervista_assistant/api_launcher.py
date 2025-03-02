#!/usr/bin/env python3
"""
Launcher for the Intervista Assistant API Server.
"""

import os
from .api import app

def main():
    """Entry point per avviare l'API server."""
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main() 