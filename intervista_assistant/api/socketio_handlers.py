#!/usr/bin/env python3
"""
Socket.IO event handlers for Intervista Assistant API.
Handles all Socket.IO events and callbacks.
"""
import os
import time
import logging
import json
import base64
import traceback
from datetime import datetime
from flask import request, current_app
from flask_socketio import emit
import jwt

from intervista_assistant.core.utils import active_sessions, start_cleanup_task

# Logging configuration
logger = logging.getLogger(__name__)

def register_socketio_handlers(socketio):
    """Register all Socket.IO event handlers."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        sid = request.sid
        logger.info(f"[SOCKET.IO] Client connected: {sid}")
        
        # Avvia il task di pulizia se non è già in esecuzione
        start_cleanup_task()
        
        # Verifica token JWT negli headers
        token = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            logger.warning(f"[SOCKET.IO] Connessione senza token JWT: {sid}")
            return True  # Accetta comunque la connessione, ma non autenticata
        
        try:
            # Ottieni il JWT_SECRET dall'ambiente o dalle variabili d'app
            jwt_secret = os.environ.get('JWT_SECRET') or current_app.config.get('JWT_SECRET')
            if not jwt_secret:
                logger.error("[SOCKET.IO] JWT_SECRET non configurato!")
                return True  # Accetta comunque la connessione in caso di errore di configurazione
                
            # Verifica e decodifica del JWT
            decoded_payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            
            # Memorizza l'utente autenticato nei dati della sessione Socket.IO
            flask_request = request._get_current_object()
            flask_request.user = decoded_payload
            
            logger.info(f"[SOCKET.IO] Client autenticato: {sid}, utente: {decoded_payload.get('sub')}")
        
        except jwt.ExpiredSignatureError:
            logger.warning(f"[SOCKET.IO] Token JWT scaduto: {sid}")
        except jwt.InvalidTokenError:
            logger.warning(f"[SOCKET.IO] Token JWT non valido: {sid}")
        except Exception as e:
            logger.error(f"[SOCKET.IO] Errore verifica token: {e}")
        
        return True
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        sid = request.sid
        logger.info(f"[SOCKET.IO] Client disconnected: {sid}")
    
    @socketio.on('audio_data')
    def handle_audio_data(session_id, audio_data):
        """
        Handle audio data streamed from the client.
        Args:
            session_id: Intervista Assistant session ID
            audio_data: Audio data as base64 string or bytes array
        """
        # Default acknowledgement response
        acknowledgement = {
            'received': True, 
            'timestamp': time.time()
        }
        
        # Verifica dell'autenticazione
        flask_request = request._get_current_object()
        user = getattr(flask_request, 'user', None)
        
        # Se non c'è user nell'oggetto request, l'utente non è autenticato
        if not user:
            logger.warning(f"[SOCKET.IO:AUDIO] Richiesta non autenticata: {request.sid}, sessione: {session_id}")
            acknowledgement['error'] = 'Autenticazione richiesta'
            return acknowledgement
        
        # Check if session exists
        if session_id not in active_sessions:
            logger.warning(f"[SOCKET.IO:AUDIO] Session not found: {session_id}")
            acknowledgement['error'] = 'Session not found'
            return acknowledgement
        
        # Get session
        session = active_sessions[session_id]
        
        # Controlla che la sessione appartiene all'utente autenticato
        # Qui potresti implementare una verifica più specifica, ad esempio verificando che
        # l'ID della sessione sia associato all'utente nel tuo database
        
        # Check if the session is recording
        if not session.recording or not session.text_thread:
            logger.warning(f"[SOCKET.IO:AUDIO] Session {session_id} not recording")
            emit('error', {'message': 'Session not recording'})
            acknowledgement['error'] = 'Session not recording'
            return acknowledgement
        
        # Check if audio_data is not empty
        if not audio_data:
            logger.warning(f"[SOCKET.IO:AUDIO] Empty audio data received for session {session_id}")
            acknowledgement['error'] = 'Empty audio data'
            return acknowledgement
            
        try:
            # Update the last activity timestamp
            session.last_activity = datetime.now()
            
            # Get the text thread
            text_thread = session.text_thread
            
            # Check if websocket is connected
            with text_thread.lock:
                websocket_connected = text_thread.connected
                websocket_reconnect_attempts = text_thread.reconnect_attempts
                
            # Add audio data to the queue
            if text_thread and websocket_connected:
                try:
                    # Se i dati audio sono già in formato binario, usali direttamente
                    # altrimenti decodificali da base64
                    if isinstance(audio_data, str):
                        binary_audio = base64.b64decode(audio_data)
                    else:
                        binary_audio = audio_data
                    
                    # Send the binary audio data to the text thread
                    text_thread.add_audio_data(binary_audio)
                    
                    # Successfully processed
                    return acknowledgement
                except Exception as e:
                    logger.error(f"[SOCKET.IO:AUDIO] Error processing audio data: {str(e)}")
                    acknowledgement['error'] = f"Error processing audio: {str(e)}"
                    return acknowledgement
            else:
                if not websocket_connected:
                    logger.warning(f"[SOCKET.IO:AUDIO] WebSocket not connected for session {session_id}, handling gracefully...")
                    
                    # If the thread exists but the connection is lost, log additional info for debugging
                    if session.text_thread:
                        with session.text_thread.lock:
                            running = session.text_thread.running
                        logger.info(f"[SOCKET.IO:AUDIO] Thread info - running: {running}, reconnect attempts: {websocket_reconnect_attempts}")
                    
                    # Check if we should try to reconnect or notify the frontend of the error
                    if session.text_thread and session.text_thread.reconnect_attempts < session.text_thread.max_reconnect_attempts:
                        logger.info(f"[SOCKET.IO:AUDIO] Forwarding audio to thread for buffering")
                        
                        # Even without a connection, forward the data to the thread
                        # which will buffer it and send it when the connection is restored
                        emit('connection_status', {'connected': False, 'reconnecting': True})
                    else:
                        # Too many reconnection attempts failed, notify the client
                        logger.error(f"[SOCKET.IO:AUDIO] WebSocket reconnection failed after {websocket_reconnect_attempts} attempts")
                        acknowledgement['error'] = 'WebSocket connection failed'
                        emit('error', {'message': 'WebSocket connection failed, please restart the session'})
                        return acknowledgement
        except Exception as e:
            # Log the full stack trace for debugging
            logger.error(f"[SOCKET.IO:AUDIO] Unhandled exception: {str(e)}")
            logger.error(traceback.format_exc())
            acknowledgement['error'] = f"Server error: {str(e)}"
            return acknowledgement 