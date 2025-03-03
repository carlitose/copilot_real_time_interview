#!/usr/bin/env python3
"""
Launcher for the Intervista Assistant API Server.
"""

import os
from api import app
from werkzeug.middleware.proxy_fix import ProxyFix

def main():
    """Entry point per avviare l'API server."""
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"  # Debug mode abilitato di default
    use_reloader = os.environ.get("FLASK_RELOADER", "1") == "1"  # Reloader abilitato di default
    
    app.wsgi_app = ProxyFix(app.wsgi_app)
    app.run(
        debug=debug,
        host="0.0.0.0",
        port=port,
        use_reloader=use_reloader
    )

if __name__ == "__main__":
    main()