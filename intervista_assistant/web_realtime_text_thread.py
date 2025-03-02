#!/usr/bin/env python3
import sys
import os
import time
import json
import logging
import asyncio
import threading
import base64
import numpy as np
import pathlib

import pyaudio
import websocket

# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='api.log')
logger = logging.getLogger(__name__)

class WebRealtimeTextThread:
    """
    Versione web-compatibile di RealtimeTextThread per l'uso in ambiente API.
    Usa callback invece dei segnali PyQt, ma mantiene la stessa funzionalità.
    """
    
    def __init__(self, callbacks=None):
        """
        Inizializza l'istanza con callback opzionali.
        
        Args:
            callbacks: dizionario di funzioni di callback:
                - on_transcription(text)
                - on_response(text)
                - on_error(message)
                - on_connection_status(connected)
        """
        self.callbacks = callbacks or {}
        self.running = False
        self.connected = False
        self.transcription_buffer = ""
        self.last_event_time = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.main_thread = None
        
        # Audio configuration
        self.recording = False
        self.audio_buffer = []
        self.accumulated_audio = b''
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        self.p = None
        self.stream = None
        
        # Configuration for pause detection
        self.last_audio_commit_time = 0
        self.silence_threshold = 500  # RMS value to define silence
        self.pause_duration = 0.7     # seconds of pause to trigger commit
        self.min_commit_interval = 1.5  # minimum interval between commits
        self.is_speaking = False
        self.silence_start_time = 0
        self.last_commit_time = 0
        self.response_pending = False
        
        # Buffer to accumulate audio transcription deltas and response
        self._response_transcript_buffer = ""
        self._response_buffer = ""
        
        # Variable to hold the final transcription
        self.current_text = ""
        
        # Lock per operazioni thread-safe
        self.lock = threading.Lock()
        
        # Path to the system prompt file
        self.system_prompt_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "system_prompt.json"
        )
    
    def emit_transcription(self, text):
        """Emette un evento di trascrizione."""
        callback = self.callbacks.get('on_transcription')
        if callback:
            callback(text)
    
    def emit_response(self, text):
        """Emette un evento di risposta."""
        callback = self.callbacks.get('on_response')
        if callback:
            callback(text)
    
    def emit_error(self, message):
        """Emette un evento di errore."""
        callback = self.callbacks.get('on_error')
        if callback:
            callback(message)
    
    def emit_connection_status(self, connected):
        """Emette un evento di stato della connessione."""
        with self.lock:
            self.connected = connected
        callback = self.callbacks.get('on_connection_status')
        if callback:
            callback(connected)
    
    def _load_system_prompt(self):
        """Carica il prompt di sistema dal file JSON esterno."""
        try:
            with open(self.system_prompt_path, 'r', encoding='utf-8') as f:
                system_message = json.load(f)
            logger.info("System prompt loaded from file: %s", self.system_prompt_path)
            return system_message
        except Exception as e:
            logger.error("Error loading system prompt from file: %s", str(e))
            # Fallback to default system prompt
            return {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "system",
                    "content": [{
                        "type": "input_text",
                        "text": "You are an AI assistant for job interviews, specialized in questions for software engineers. Respond concisely and structured."
                    }]
                }
            }
    
    async def realtime_session(self):
        """Gestisce una sessione di comunicazione tramite Realtime API."""
        try:
            self.emit_transcription("Connecting to Realtime API...")
            
            url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
            headers = [
                "Authorization: Bearer " + os.getenv('OPENAI_API_KEY'),
                "OpenAI-Beta: realtime=v1",
                "Content-Type: application/json"
            ]
            
            with self.lock:
                self.connected = False
            self.websocket = None
            self.websocket_thread = None
            
            def on_open(ws):
                logger.info("WebSocket connection established")
                self.emit_connection_status(True)
                self.last_event_time = time.time()
                self.current_text = ""
                
                session_config = {
                    "event_id": "event_123",
                    "type": "session.update",
                    "session": {
                        "modalities": ["text", "audio"],
                        "instructions": "You are a helpful assistant.",
                        "voice": "sage",
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "input_audio_transcription": {
                            "model": "whisper-1"
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500,
                            "create_response": True
                        },
                        "tool_choice": "auto",
                        "temperature": 0.8,
                        "max_response_output_tokens": "inf"
                    }
                }
                
                try:
                    ws.send(json.dumps(session_config))
                    logger.info("Session configuration sent (audio and text)")
                except Exception as e:
                    logger.error("Error sending configuration: " + str(e))
                
                # Load system prompt from external file
                system_message = self._load_system_prompt()
                
                try:
                    ws.send(json.dumps(system_message))
                    logger.info("System prompt message sent")
                except Exception as e:
                    logger.error("Error sending system prompt message: " + str(e))
                
                response_request = {
                    "type": "response.create",
                    "response": {"modalities": ["text"]}
                }
                try:
                    ws.send(json.dumps(response_request))
                    logger.info("Response request sent")
                except Exception as e:
                    logger.error("Error sending response request: " + str(e))
                
                self.emit_transcription("Connected! Ready for the interview. Speak to ask questions.")
            
            def on_message(ws, message):
                try:
                    event = json.loads(message)
                    event_type = event.get('type', 'unknown')
                    logger.debug(f"Event received: {event_type}")
                    
                    if event_type == 'response.audio_transcript.delta':
                        delta = event.get('delta', '')
                        self._response_transcript_buffer += delta
                        logger.debug("Accumulated transcript delta: %s", delta)
                    elif event_type == 'response.audio_transcript.done':
                        transcribed_text = self._response_transcript_buffer.strip()
                        self.current_text = transcribed_text
                        self.emit_response(transcribed_text)
                        logger.info("Final audio transcription: %s", transcribed_text)
                        self._response_transcript_buffer = ""
                    elif event_type == 'response.text.delta':
                        delta = event.get('delta', '')
                        self._response_buffer += delta
                        logger.debug("Accumulated delta: %s", delta)
                    elif event_type in ('response.text.done', 'response.done'):
                        if self._response_buffer.strip():
                            self.emit_response(self._response_buffer)
                            logger.info("Response completed: %s", self._response_buffer)
                            self._response_buffer = ""
                    elif event_type == 'error':
                        self.response_pending = False
                        error = event.get('error', {})
                        error_msg = error.get('message', 'Unknown error')
                        self.emit_error(f"API Error: {error_msg}")
                        logger.error("Error received: %s", error_msg)
                    else:
                        logger.debug("Message received of type %s", event_type)
                except Exception as e:
                    logger.error("Exception in on_message: " + str(e))
            
            def on_error(ws, error):
                logger.error("WebSocket Error: " + str(error))
                self.emit_error(f"Connection error: {error}")
                self.emit_connection_status(False)
            
            def on_close(ws, close_status_code, close_msg):
                logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
                self.emit_connection_status(False)
                
                self.reconnect_attempts += 1
                reconnect_msg = f"\n[Connection lost. Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}]"
                self.transcription_buffer += reconnect_msg
                self.emit_transcription(self.transcription_buffer)
                
                with self.lock:
                    should_reconnect = self.running and self.reconnect_attempts <= self.max_reconnect_attempts
                
                if should_reconnect:
                    self.emit_error("Reconnection needed")
            
            self.websocket = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            self.reconnect_attempts = 0
            
            def run_websocket():
                self.websocket.run_forever()
            
            self.websocket_thread = threading.Thread(target=run_websocket)
            self.websocket_thread.daemon = True
            self.websocket_thread.start()
            
            try:
                with self.lock:
                    should_continue = self.running
                
                while should_continue:
                    await asyncio.sleep(1)
                    with self.lock:
                        should_continue = self.running
            except asyncio.CancelledError:
                logger.info("Main loop cancelled")
            finally:
                with self.lock:
                    is_connected = self.connected
                
                if self.websocket and is_connected:
                    try:
                        self.websocket.close()
                    except Exception as e:
                        logger.error("Error closing websocket: " + str(e))
                logger.info("WebSocket session ended")
        except Exception as e:
            error_msg = f"Critical error: {e}"
            self.emit_error(error_msg)
            logger.error(error_msg)
        finally:
            self.emit_connection_status(False)
    
    def start(self):
        """Avvia il thread di comunicazione."""
        with self.lock:
            self.running = True
        
        async def run_session():
            await self.realtime_session()
        
        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_session())
            except Exception as e:
                logger.error("Error in asynchronous thread: " + str(e))
            finally:
                loop.close()
                logger.info("Communication thread ended")
        
        self.main_thread = threading.Thread(target=run_async_loop)
        self.main_thread.daemon = True
        self.main_thread.start()
        
        return self.main_thread
    
    def stop(self):
        """Interrompe la comunicazione e termina tutti i processi in sospeso."""
        logger.info("Stop communication request received")
        
        with self.lock:
            self.running = False
            self.recording = False
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error("Error stopping stream: " + str(e))
        
        if self.p:
            try:
                self.p.terminate()
            except Exception as e:
                logger.error("Error terminating PyAudio: " + str(e))
        
        with self.lock:
            is_connected = self.connected
            ws = getattr(self, "websocket", None)
        
        if ws and is_connected:
            try:
                logger.info("Closing WebSocket...")
                ws.close()
                logger.info("WebSocket closed")
            except Exception as e:
                logger.error("Error closing websocket: " + str(e))
        
        logger.info("Termination request completed. Waiting for pending threads to close...")
        time.sleep(0.5)
    
    def wait(self, timeout=None):
        """
        Attende che il thread principale termini.
        
        Args:
            timeout: Timeout in millisecondi
        """
        if self.main_thread and self.main_thread.is_alive():
            timeout_sec = timeout / 1000 if timeout else None
            self.main_thread.join(timeout=timeout_sec)
    
    def start_recording(self):
        """Avvia la registrazione audio dal microfono."""
        with self.lock:
            if self.recording:
                return
            self.recording = True
        
        self.audio_buffer = []
        self.accumulated_audio = b''
        
        try:
            self.p = pyaudio.PyAudio()
            self.stream = self.p.open(format=self.FORMAT,
                                      channels=self.CHANNELS,
                                      rate=self.RATE,
                                      input=True,
                                      frames_per_buffer=self.CHUNK)
        except Exception as e:
            logger.error("Error initializing PyAudio: " + str(e))
            self.emit_error("Audio initialization error")
            return
        
        threading.Thread(target=self._record_audio, daemon=True).start()
        logger.info("Audio recording started")
        self.emit_transcription("Recording... Speak now.")
    
    def stop_recording(self):
        """Interrompe la registrazione audio."""
        with self.lock:
            if not self.recording:
                return
            self.recording = False
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error("Error closing stream: " + str(e))
        
        if self.p:
            try:
                self.p.terminate()
            except Exception as e:
                logger.error("Error terminating PyAudio: " + str(e))
        
        with self.lock:
            has_connection = hasattr(self, 'websocket') and self.websocket and self.connected
        
        if not has_connection:
            logger.warning("WebSocket not available to send requests")
            return
        
        try:
            if self.accumulated_audio and has_connection:
                self._send_entire_audio_message()
            
            commit_message = {"type": "input_audio_buffer.commit"}
            self.websocket.send(json.dumps(commit_message))
            logger.info("Audio input ended (final commit)")
            
            with self.lock:
                is_response_pending = self.response_pending
            
            if not is_response_pending:
                response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                self.websocket.send(json.dumps(response_request))
                logger.info("Final response request sent")
            else:
                logger.info("Response already in progress, no new request sent")
        except Exception as e:
            logger.error("Error sending termination messages: " + str(e))
        
        with self.lock:
            self.response_pending = False
            
        logger.info("Audio recording stopped")
    
    def _record_audio(self):
        """Registra audio in un ciclo fino all'arresto."""
        try:
            self.last_commit_time = time.time()
            
            while True:
                with self.lock:
                    if not self.recording or not self.stream:
                        break
                
                data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                self.audio_buffer.append(data)
                self.accumulated_audio += data
                rms = self._calculate_rms(data)
                current_time = time.time()
                
                if rms > self.silence_threshold:
                    if not self.is_speaking:
                        logger.info(f"Speech start detected (RMS: {rms})")
                        self.is_speaking = True
                    self.silence_start_time = 0
                else:
                    if self.is_speaking:
                        if self.silence_start_time == 0:
                            self.silence_start_time = current_time
                        elif (current_time - self.silence_start_time >= self.pause_duration and 
                              current_time - self.last_commit_time >= self.min_commit_interval):
                            if len(self.accumulated_audio) >= 3200:
                                logger.info(f"Pause detected ({current_time - self.silence_start_time:.2f}s) - sending partial audio")
                                self._send_entire_audio_message()
                                
                                with self.lock:
                                    has_connection = self.connected and self.websocket
                                
                                if has_connection:
                                    commit_message = {"type": "input_audio_buffer.commit"}
                                    self.websocket.send(json.dumps(commit_message))
                                    logger.info("Partial audio commit sent")
                                    
                                    with self.lock:
                                        is_response_pending = self.response_pending
                                    
                                    if not is_response_pending:
                                        response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                                        self.websocket.send(json.dumps(response_request))
                                        logger.info("Response request sent after partial audio")
                                        with self.lock:
                                            self.response_pending = True
                                
                                self.last_commit_time = current_time
                                self.silence_start_time = 0
                                self.accumulated_audio = b''
                                self.audio_buffer = []
                                self.is_speaking = False
                            else:
                                logger.info(f"Pause detected but buffer too small ({len(self.accumulated_audio)} bytes), continuing to accumulate")
                
                with self.lock:
                    if not self.recording:
                        logger.info("Recording stop detected, exiting audio capture loop.")
                        break
                        
        except Exception as e:
            logger.error("Error during recording: " + str(e))
            self.emit_error("Recording error: " + str(e))
            with self.lock:
                self.recording = False
    
    def _calculate_rms(self, data):
        """Calcola il valore RMS per un buffer audio."""
        try:
            shorts = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(np.square(shorts)))
            if np.isnan(rms):
                logger.warning("RMS calculation produced NaN, returning 0")
                return 0
            return rms
        except Exception as e:
            logger.error("Error calculating RMS: " + str(e))
            return 0
    
    def _send_entire_audio_message(self):
        """Invia l'audio accumulato come un singolo messaggio."""
        with self.lock:
            has_audio = bool(self.accumulated_audio)
            has_connection = self.connected
        
        if not has_audio or not has_connection:
            return
            
        try:
            base64_audio = base64.b64encode(self.accumulated_audio).decode('ascii')
            audio_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_audio", "audio": base64_audio}]
                }
            }
            self.websocket.send(json.dumps(audio_message))
            logger.info("Single audio message sent")
        except Exception as e:
            logger.error("Error sending single audio message: " + str(e))
    
    def send_text(self, text):
        """
        Invia un messaggio di testo al modello attraverso la connessione websocket.
        
        Args:
            text: Il messaggio di testo da inviare
            
        Returns:
            bool: True se l'invio è riuscito, False altrimenti
        """
        with self.lock:
            has_connection = self.connected and self.websocket
        
        if not has_connection:
            logger.error("Cannot send text: WebSocket not connected")
            return False
            
        try:
            # Crea il messaggio di testo
            text_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}]
                }
            }
            
            # Invia il messaggio attraverso il websocket
            self.websocket.send(json.dumps(text_message))
            logger.info(f"Text message sent through websocket: {text[:50]}...")
            
            # Richiedi una risposta
            with self.lock:
                is_response_pending = self.response_pending
            
            if not is_response_pending:
                response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                self.websocket.send(json.dumps(response_request))
                logger.info("Response request sent after text message")
                with self.lock:
                    self.response_pending = True
                
            # Resetta i buffer
            self._response_buffer = ""
            
            return True
        except Exception as e:
            error_msg = f"Error sending text message: {str(e)}"
            logger.error(error_msg)
            return False 