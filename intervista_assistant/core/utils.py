#!/usr/bin/env python3
"""
Utility functions for Intervista Assistant.
"""
import os
import json
import logging
import threading
import time
import jwt
from datetime import datetime
from functools import wraps
from flask import request, jsonify

# Dictionary to store active sessions
active_sessions = {}

# Maximum inactivity time for a session (minutes)
SESSION_TIMEOUT_MINUTES = 30

# Supabase authentication configuration
SUPABASE_JWT_SECRET = os.environ.get('SUPABASE_JWT_SECRET', 'super-secret-jwt-token-with-at-least-32-characters-long')
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'http://127.0.0.1:54321')

def verify_token(token):
    """
    Verifies a JWT token from Supabase.
    
    Args:
        token (str): JWT token to verify
        
    Returns:
        dict or None: Decoded token payload if valid, None otherwise
    """
    if not token:
        return None
        
    # # DEVELOPMENT MODE: Accept any token for local development
    # # TODO: Remove in production
    # logging.warning("DEVELOPMENT MODE: Token verification bypassed")
    # return {"sub": "dev-user", "email": "dev@example.com"}
    
    # Production code:
    if not SUPABASE_JWT_SECRET:
        logging.warning("SUPABASE_JWT_SECRET not configured, skipping token verification")
        return {"sub": "anonymous", "email": "anonymous@example.com"}  # Development fallback
    
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
            
        # Verify and decode the token
        decoded = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={
                "verify_signature": True,
                "verify_aud": False,  # Disabilita controllo audience
                "verify_iss": True    # Riabilita controllo issuer
            }
        )
        
        # Check if token is expired
        exp_timestamp = decoded.get('exp', 0)
        if exp_timestamp < time.time():
            logging.warning(f"Token expired at {datetime.fromtimestamp(exp_timestamp)}")
            return None
            
        return decoded
    except jwt.InvalidTokenError as e:
        logging.error(f"Invalid token: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Error verifying token: {str(e)}")
        return None

def require_auth(f):
    """
    Decorator to require authentication for API endpoints.
    Must be applied after @require_session if both are used.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip auth check for OPTIONS requests
        if request.method == 'OPTIONS':
            return jsonify({"success": True}), 200
            
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization')
        
        logging.info(f"Auth header received: {auth_header[:20] if auth_header else 'None'}")
        
        if not auth_header:
            logging.warning("Missing Authorization header")
            return jsonify({"success": False, "error": "Authentication required"}), 401
            
        # Verify the token
        token_payload = verify_token(auth_header)
        
        if not token_payload:
            logging.warning("Invalid or expired token")
            return jsonify({"success": False, "error": "Invalid or expired token"}), 401
            
        # Add user info to request context
        request.user_id = token_payload.get('sub')
        request.user_email = token_payload.get('email')
        
        logging.info(f"Authenticated request from user {request.user_id}")
        
        return f(*args, **kwargs)
    return decorated_function

# Decorator to check if the session exists
def require_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip session check for OPTIONS requests
        if request.method == 'OPTIONS':
            return jsonify({"success": True}), 200
            
        session_id = request.json.get('session_id')
        if not session_id or session_id not in active_sessions:
            return jsonify({"success": False, "error": "Session not found"}), 404
            
        # Store the session in the request context to avoid race conditions
        request.session_manager = active_sessions.get(session_id)
        if not request.session_manager:
            return jsonify({"success": False, "error": "Session disappeared during request processing"}), 404
            
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