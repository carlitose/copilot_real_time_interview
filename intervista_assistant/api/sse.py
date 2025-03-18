#!/usr/bin/env python3
"""
Server-Sent Events (SSE) functionality for Intervista Assistant.
Handles real-time streaming of updates to the frontend.
"""
import json
import time
import logging
from datetime import datetime
from flask import request

from intervista_assistant.core.utils import active_sessions, format_sse

# Logging configuration
logger = logging.getLogger(__name__)

def session_sse_generator(session_id):
    """
    Generator for SSE events for a specific session.
    Args:
        session_id: The ID of the session to stream events for
    Returns:
        A generator that yields SSE events
    """
    try:
        # Controlla che l'utente sia autenticato e abbia accesso alla sessione
        if hasattr(request, 'user'):
            # In futuro, qui puoi aggiungere controlli aggiuntivi specifici
            # per verificare che l'utente abbia accesso alla sessione indicata
            # Ad esempio, verificando che il session_id appartenga all'utente nel tuo database
            user_id = request.user.get('sub')
            logger.info(f"SSE stream richiesto da utente autenticato: {user_id}, session: {session_id}")
        else:
            logger.warning(f"SSE stream richiesto senza autenticazione per session: {session_id}")
            # Se non utilizziamo require_auth nel router, questa verifica può essere utile
        
        if session_id not in active_sessions:
            logger.error(f"SSE stream requested for invalid session: {session_id}")
            yield format_sse(json.dumps({
                "type": "error",
                "data": {"message": "Session not found"}
            }))
            return
        
        # Get session
        session = active_sessions[session_id]
        
        # Send initial session state
        yield format_sse(json.dumps({
            "type": "status",
            "data": session.get_status()
        }))
        
        # Initialize last message index
        last_message_idx = 0
        activity_count = 0
        
        # Stream updates
        while session_id in active_sessions:
            session = active_sessions[session_id]
            
            # Check for new messages
            current_messages = session.get_messages()
            if len(current_messages) > last_message_idx:
                # Send all new messages
                for idx in range(last_message_idx, len(current_messages)):
                    message = current_messages[idx]
                    yield format_sse(json.dumps({
                        "type": "message",
                        "data": message
                    }))
                last_message_idx = len(current_messages)
                
                # Reset activity counter on new messages
                activity_count = 0
            
            # Send status update occasionally
            if activity_count % 10 == 0:
                status = session.get_status()
                yield format_sse(json.dumps({
                    "type": "status",
                    "data": status
                }))
            
            # Send heartbeat every 30 seconds or so
            if activity_count % 30 == 0 and activity_count > 0:
                yield format_sse(json.dumps({
                    "type": "heartbeat",
                    "data": {"timestamp": time.time()}
                }))
            
            # Sleep to avoid busy waiting
            time.sleep(1)
            activity_count += 1
            
        # Send final closure message
        yield format_sse(json.dumps({
            "type": "close",
            "data": {"message": "Session closed or not found"}
        }))
        
    except GeneratorExit:
        logger.info(f"SSE connection closed for session {session_id}")
        # Client disconnected, clean up if needed
    except Exception as e:
        logger.error(f"Error in SSE generator for session {session_id}: {str(e)}")
        # Send error message
        yield format_sse(json.dumps({
            "type": "error",
            "data": {"message": f"Server error: {str(e)}"}
        })) 