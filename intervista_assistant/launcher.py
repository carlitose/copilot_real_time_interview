#!/usr/bin/env python3
"""
Launcher per Intervista Assistant.
Consente l'esecuzione dell'applicazione dalla directory principale.
"""

import os
import sys
from pathlib import Path

# Aggiungi la directory principale al path
sys.path.insert(0, str(Path(__file__).parent.parent))

if __name__ == "__main__":
    # Importa e avvia l'applicazione
    from intervista_assistant.main import main
    
    # Esegui l'applicazione
    main() 