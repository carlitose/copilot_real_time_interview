#!/usr/bin/env python3
"""
Launcher for the Intervista Assistant API Server.
"""

import os
import sys
import logging
from werkzeug.middleware.proxy_fix import ProxyFix

# Aggiungo la directory corrente al path per importare i moduli locali
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ora importo l'app da intervista_assistant.api
from intervista_assistant.api import app, socketio

def main():
    """Entry point per avviare l'API server."""
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"  # Debug mode abilitato di default
    use_reloader = os.environ.get("FLASK_RELOADER", "1") == "1"  # Reloader abilitato di default
    
    # Configurazione per watchdog
    extra_files = []
    
    # Configurazione per il reloader migliorato con watchdog
    if use_reloader:
        try:
            import watchdog
            reloader_type = "watchdog"
            logging.info("Usando watchdog per il reloader - riavvio automatico ottimizzato")
            
            # Aggiungi qui eventuali file extra da monitorare
            # Per esempio: extra_files.append("config.json")
            
        except ImportError:
            reloader_type = "stat"
            logging.warning("watchdog non disponibile, usando il reloader standard")
    else:
        reloader_type = None
    
    app.wsgi_app = ProxyFix(app.wsgi_app)
    
    # Configura logging per flask
    if debug:
        logging.getLogger('werkzeug').setLevel(logging.INFO)
        print(f"Server in esecuzione in modalità debug con reloader {'abilitato' if use_reloader else 'disabilitato'}")
        if use_reloader:
            print(f"Tipo di reloader: {reloader_type}")
    
    # Usa socketio per eseguire il server invece di app.run()
    socketio.run(
        app,
        debug=debug,
        host="0.0.0.0",
        port=port,
        use_reloader=use_reloader,
        reloader_type=reloader_type,
        extra_files=extra_files,
        allow_unsafe_werkzeug=True
    )

if __name__ == "__main__":
    main()