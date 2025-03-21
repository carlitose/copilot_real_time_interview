#!/usr/bin/env python3
"""
Utility functions for Intervista Assistant.
"""
import os
import json
import logging
import threading
import time
from datetime import datetime
from functools import wraps
from flask import request, jsonify, current_app

import jwt

# Dictionary to store active sessions
active_sessions = {}

# Maximum inactivity time for a session (minutes)
SESSION_TIMEOUT_MINUTES = 30

# Decorator to check if the session exists and verify JWT token
def require_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip session check for OPTIONS requests
        if request.method == 'OPTIONS':
            return jsonify({"success": True}), 200
        
        # Verifica del token JWT
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Token mancante o malformato"}), 401
        
        token = auth_header.split(" ")[1]  # Prende il token dopo "Bearer"
        try:
            # Ottieni il JWT_SECRET dall'ambiente o dalle variabili d'app
            jwt_secret = os.environ.get('JWT_SECRET') or current_app.config.get('JWT_SECRET')
            if not jwt_secret:
                return jsonify({"success": False, "error": "JWT_SECRET non configurato sul server"}), 500
                
            # Verifica e decodifica del JWT
            decoded_payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            
            # Verifica che il ruolo sia 'authenticated'
            if decoded_payload.get('role') != 'authenticated':
                return jsonify({"success": False, "error": "Permessi insufficienti"}), 403
                
            # Memorizza le informazioni utente decodificate dal token
            request.user = decoded_payload
            
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "error": "Token JWT scaduto"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "error": "Token JWT non valido"}), 401
            
        # Verifica la sessione
        session_id = request.json.get('session_id')
        if not session_id or session_id not in active_sessions:
            return jsonify({"success": False, "error": "Session not found"}), 404
            
        # Store the session in the request context to avoid race conditions
        request.session_manager = active_sessions.get(session_id)
        if not request.session_manager:
            return jsonify({"success": False, "error": "Session disappeared during request processing"}), 404
            
        return f(*args, **kwargs)
    return decorated_function

# Decorator per verificare il token JWT nelle richieste GET
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip auth check for OPTIONS requests
        if request.method == 'OPTIONS':
            return jsonify({"success": True}), 200
        
        # Verifica del token JWT
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Token mancante o malformato"}), 401
        
        token = auth_header.split(" ")[1]  # Prende il token dopo "Bearer"
        try:
            # Ottieni il JWT_SECRET dall'ambiente o dalle variabili d'app
            jwt_secret = os.environ.get('JWT_SECRET') or current_app.config.get('JWT_SECRET')
            if not jwt_secret:
                return jsonify({"success": False, "error": "JWT_SECRET non configurato sul server"}), 500
                
            # Verifica e decodifica del JWT
            decoded_payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            
            # Verifica che il ruolo sia 'authenticated'
            if decoded_payload.get('role') != 'authenticated':
                return jsonify({"success": False, "error": "Permessi insufficienti"}), 403
                
            # Memorizza le informazioni utente decodificate dal token
            request.user = decoded_payload
            
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "error": "Token JWT scaduto"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "error": "Token JWT non valido"}), 401
            
        return f(*args, **kwargs)
    return decorated_function

def format_sse(data):
    """Format data as SSE event."""
    return f"data: {data}\n\n"

def cleanup_inactive_sessions():
    """Removes inactive sessions."""
    logger = logging.getLogger(__name__)
    now = datetime.now()
    inactive_sessions = []
    
    # Create a copy of the keys to avoid modification during iteration
    session_ids = list(active_sessions.keys())
    
    for session_id in session_ids:
        # Check if session still exists (might have been removed by other processes)
        if session_id not in active_sessions:
            continue
            
        session = active_sessions[session_id]
        inactivity_time = (now - session.last_activity).total_seconds() / 60
        
        if inactivity_time > SESSION_TIMEOUT_MINUTES:
            inactive_sessions.append(session_id)
            logger.info(f"Session {session_id} inactive for {inactivity_time:.1f} minutes, will be removed")
    
    for session_id in inactive_sessions:
        try:
            # Check if session still exists
            if session_id not in active_sessions:
                logger.info(f"Session {session_id} already removed, skipping cleanup")
                continue
                
            # End the session and save the conversation
            session = active_sessions[session_id]
            session.end_session()
            session.save_conversation()
            
            # Safely remove the session
            if session_id in active_sessions:
                del active_sessions[session_id]
                logger.info(f"Inactive session {session_id} successfully removed")
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {str(e)}")
            # Continue with other sessions even if one fails
            continue

def start_cleanup_task():
    """Start a background thread to clean up inactive sessions."""
    if not hasattr(start_cleanup_task, 'started'):
        def run_cleanup():
            while True:
                time.sleep(60)  # 1 minute
                cleanup_inactive_sessions()
                
        cleanup_thread = threading.Thread(target=run_cleanup, daemon=True)
        cleanup_thread.start()
        start_cleanup_task.started = True 