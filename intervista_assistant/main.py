#!/usr/bin/env python3
"""
Modulo di avvio dell'applicazione Intervista Assistant.
Crea e avvia l'interfaccia utente dell'applicazione.
"""

import sys
import logging
from PyQt5.QtWidgets import QApplication
from .intervista_assistant import IntervistaAssistant

# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   filename='app.log')
logger = logging.getLogger(__name__)

def main():
    """Funzione principale per avviare l'applicazione."""
    try:
        app = QApplication(sys.argv)
        window = IntervistaAssistant()
        window.show()
        logger.info("Applicazione Intervista Assistant avviata con successo")
        sys.exit(app.exec_())
    except Exception as e:
        logger.error(f"Errore durante l'avvio dell'applicazione: {e}")
        raise

if __name__ == "__main__":
    main() 