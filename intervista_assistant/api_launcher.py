#!/usr/bin/env python3
"""
Launcher for the Intervista Assistant API Server.
"""

import uvicorn
import sys
import os

# Aggiungi la directory parent al percorso Python per consentire import assoluti
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    """Launch the API server."""
    print("Avvio del server API su http://0.0.0.0:8000")
    uvicorn.run("intervista_assistant.api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main() 