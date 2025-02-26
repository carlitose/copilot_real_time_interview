#!/usr/bin/env python3
"""
Script di avvio per Intervista Assistant.
Questo script esegue l'applicazione dalla directory principale.
"""

import os
import sys
import logging

if __name__ == "__main__":
    try:
        # Configura il logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("intervista_assistant.log"),
                logging.StreamHandler()
            ]
        )
        logger = logging.getLogger(__name__)
        
        # Messaggio di avvio
        logger.info("Avvio di Intervista Assistant...")
        
        # Importa ed esegui l'applicazione
        from intervista_assistant.main import main
        main()
        
    except ImportError as e:
        print(f"Errore di importazione: {e}")
        print("Assicurati di aver installato tutte le dipendenze richieste.")
        print("Esegui: pip install -r intervista_assistant/requirements.txt")
        sys.exit(1)
        
    except Exception as e:
        print(f"Errore durante l'avvio: {e}")
        sys.exit(1) 