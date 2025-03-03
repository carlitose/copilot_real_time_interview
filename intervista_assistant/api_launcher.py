#!/usr/bin/env python3
"""
Launcher for the Intervista Assistant API Server.
"""

import os
import sys
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
    
    app.wsgi_app = ProxyFix(app.wsgi_app)
    
    # Usa socketio per eseguire il server invece di app.run()
    socketio.run(
        app,
        debug=debug,
        host="0.0.0.0",
        port=port,
        use_reloader=use_reloader,
        allow_unsafe_werkzeug=True
    )

if __name__ == "__main__":
    main()