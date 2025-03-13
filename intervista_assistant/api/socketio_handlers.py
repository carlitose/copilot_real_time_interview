#!/usr/bin/env python3
"""
Socket.IO handlers for Intervista Assistant.
Manages real-time communication with the frontend.
"""
import time
import logging
import numpy as np
from datetime import datetime
from flask_socketio import emit
from flask import request

from intervista_assistant.core.utils import active_sessions, start_cleanup_task

# Logging configuration
logger = logging.getLogger(__name__)

def register_socketio_handlers(socketio):
    """Register all Socket.IO event handlers."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handles a Socket.IO client connection."""
        logger.info(f"New Socket.IO client connected: {request.sid}")
        # Start the cleanup task if not already started
        start_cleanup_task()

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handles a Socket.IO client disconnection."""
        logger.info(f"Socket.IO client disconnected: {request.sid}")

    @socketio.on('audio_data')
    def handle_audio_data(session_id, audio_data):
        """
        Handles audio data received from the client.
        This is the ONLY way to send audio data to the backend.
        """
        acknowledgement = {
            'received': False, 
            'error': None,
            'timestamp': time.time(),
            'session_active': session_id in active_sessions
        }
        
        try:
            # Log only essential metadata about the audio data
            audio_type = type(audio_data).__name__
            if isinstance(audio_data, list):
                audio_length = len(audio_data)
                logger.info(f"[SOCKET.IO:AUDIO] Received audio data for session {session_id}: {audio_length} samples, type={audio_type}")
                acknowledgement['samples'] = audio_length
            elif isinstance(audio_data, bytes):
                logger.info(f"[SOCKET.IO:AUDIO] Received audio data for session {session_id}: {len(audio_data)} bytes, type={audio_type}")
                acknowledgement['bytes'] = len(audio_data)
            else:
                logger.info(f"[SOCKET.IO:AUDIO] Received audio data for session {session_id}: type={audio_type}")
                acknowledgement['type'] = audio_type
            
            if session_id not in active_sessions:
                logger.error(f"[SOCKET.IO:AUDIO] Session {session_id} not found")
                emit('error', {'message': 'Session not found'})
                acknowledgement['error'] = 'Session not found'
                return acknowledgement
            
            session = active_sessions[session_id]
            acknowledgement['session_recording'] = session.recording
            
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
                
                # Verify and convert the audio to the correct format
                if isinstance(audio_data, list):
                    # Check for valid values based on 16-bit PCM requirements
                    if any(not isinstance(sample, (int, float)) for sample in audio_data):
                        logger.error(f"[SOCKET.IO:AUDIO] Invalid audio data format: non-numeric samples")
                        acknowledgement['error'] = 'Invalid audio data format'
                        emit('error', {'message': 'Invalid audio data format: non-numeric samples'})
                        return acknowledgement
                    
                    # Ensure there are enough samples (at least 10ms of audio at 24kHz = 240 samples)
                    if len(audio_data) < 240:
                        logger.warning(f"[SOCKET.IO:AUDIO] Audio clip too short: {len(audio_data)} samples")
                        acknowledgement['warning'] = 'Audio clip too short'
                    
                    # Normalize values to ensure compatibility with 16-bit PCM (-32768 to 32767)
                    max_value = max(abs(sample) if isinstance(sample, int) else abs(float(sample)) for sample in audio_data)
                    
                    # If values are too large or too small, normalize them
                    if max_value > 32767 or max_value < 1:
                        logger.info(f"[SOCKET.IO:AUDIO] Normalizing audio samples: max value = {max_value}")
                        if max_value > 0:  # Avoid division by zero
                            scaling_factor = 32767.0 / max_value
                            audio_data = [int(sample * scaling_factor) for sample in audio_data]
                    
                    # Ensure it is of the correct type for OpenAI (16-bit PCM)
                    audio_data = np.array(audio_data, dtype=np.int16)
                    logger.info(f"[SOCKET.IO:AUDIO] Converted list to numpy array for session {session_id}: {len(audio_data)} samples")
                    
                    # Calculate the duration of the received audio (assuming 24kHz)
                    audio_duration_ms = (len(audio_data) / 24000) * 1000
                    logger.info(f"[SOCKET.IO:AUDIO] Approximate audio duration: {audio_duration_ms:.2f}ms at 24kHz")
                    acknowledgement['duration_ms'] = audio_duration_ms
                
                # Check websocket connection status
                websocket_connected = False
                websocket_reconnect_attempts = 0
                if session.text_thread:
                    websocket_connected = session.text_thread.connected
                    websocket_reconnect_attempts = session.text_thread.reconnect_attempts
                
                acknowledgement['websocket_connected'] = websocket_connected
                acknowledgement['websocket_reconnect_attempts'] = websocket_reconnect_attempts
                
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
                
                # Add the audio data to the text thread buffer
                if session.text_thread:
                    # Now we can send the data to the text thread
                    success = session.text_thread.add_audio_data(audio_data)
                    acknowledgement['received'] = success
                    
                    # Add info about the data size
                    if isinstance(audio_data, np.ndarray):
                        acknowledgement['bytes_processed'] = audio_data.nbytes
                    elif isinstance(audio_data, bytes):
                        acknowledgement['bytes_processed'] = len(audio_data)
                    else:
                        acknowledgement['bytes_processed'] = 'unknown'
                    
                    # Update the status for the frontend
                    if success:
                        emit('audio_processed', {'success': True, 'bytes': acknowledgement.get('bytes_processed', 0)})
                
            except Exception as e:
                logger.error(f"[SOCKET.IO:AUDIO] Error processing audio in text thread: {str(e)}")
                acknowledgement['error'] = f"Audio processing error: {str(e)}"
                emit('error', {'message': f'Audio processing error: {str(e)}'})
            
            return acknowledgement
            
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"[SOCKET.IO:AUDIO] Unexpected error: {str(e)}")
            acknowledgement['error'] = f"Unexpected error: {str(e)}"
            return acknowledgement 