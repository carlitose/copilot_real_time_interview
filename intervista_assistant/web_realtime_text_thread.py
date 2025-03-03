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

import websocket
import pyaudio

# Logging configuration
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='api.log')
logger = logging.getLogger(__name__)

class WebRealtimeTextThread:
    """
    Web-compatible version of RealtimeTextThread for use in API environment.
    Uses callbacks instead of PyQt signals, but maintains the same functionality.
    """
    
    def __init__(self, callbacks=None):
        """
        Initializes the instance with optional callbacks.
        
        Args:
            callbacks: dictionary of callback functions:
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
        
        # Lock for thread-safe operations
        self.lock = threading.Lock()
        
        # Path to the system prompt file
        self.system_prompt_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "system_prompt.json"
        )
    
    def emit_transcription(self, text):
        """Emits a transcription event."""
        callback = self.callbacks.get('on_transcription')
        if callback:
            callback(text)
    
    def emit_response(self, text):
        """Emits a response event."""
        callback = self.callbacks.get('on_response')
        if callback:
            callback(text)
    
    def emit_error(self, message):
        """Emits an error event."""
        callback = self.callbacks.get('on_error')
        if callback:
            callback(message)
    
    def emit_connection_status(self, connected):
        """Emits a connection status event."""
        with self.lock:
            self.connected = connected
        callback = self.callbacks.get('on_connection_status')
        if callback:
            callback(connected)
    
    def _load_system_prompt(self):
        """Loads the system prompt from the external JSON file."""
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
        """Manages a communication session via Realtime API."""
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
            
            def on_open(ws):
                logger.info("WebSocket connection established")
                with self.lock:
                    self.connected = True
                self.emit_connection_status(True)
                self.last_event_time = time.time()
                self.current_text = ""
                
                session_config = {
                    "event_id": "event_123",
                    "type": "session.update",
                    "session": {
                        "modalities": ["text", "audio"],
                        "instructions": "You are a helpful assistant for job interview coaching.",
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
                
                # Load the system prompt from external file
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
                    logger.debug(f"[OpenAI] Evento ricevuto: {event_type}")
                    
                    if event_type == 'response.audio_transcript.delta':
                        delta = event.get('delta', '')
                        self._response_transcript_buffer += delta
                        logger.debug(f"[OpenAI] Delta trascrizione audio: {delta}")
                    elif event_type == 'response.audio_transcript.done':
                        transcribed_text = self._response_transcript_buffer.strip()
                        self.current_text = transcribed_text
                        self.emit_response(transcribed_text)
                        logger.info(f"[OpenAI] Trascrizione audio completata: {transcribed_text[:50]}...")
                        self._response_transcript_buffer = ""
                    elif event_type == 'response.text.delta':
                        delta = event.get('delta', '')
                        self._response_buffer += delta
                        logger.debug(f"[OpenAI] Delta testo: {delta}")
                    elif event_type in ('response.text.done', 'response.done'):
                        if self._response_buffer.strip():
                            self.emit_response(self._response_buffer)
                            logger.info(f"[OpenAI] Risposta completata: {self._response_buffer[:50]}...")
                            with self.lock:
                                self.response_pending = False
                            self._response_buffer = ""
                    elif event_type == 'error':
                        with self.lock:
                            self.response_pending = False
                        error = event.get('error', {})
                        error_msg = error.get('message', 'Unknown error')
                        self.emit_error(f"API Error: {error_msg}")
                        logger.error(f"[OpenAI] Errore ricevuto: {error_msg}")
                    else:
                        logger.debug(f"[OpenAI] Messaggio ricevuto di tipo {event_type}")
                except Exception as e:
                    logger.error(f"[OpenAI] Eccezione in on_message: {str(e)}")
            
            def on_error(ws, error):
                logger.error("WebSocket Error: " + str(error))
                self.emit_error(f"Connection error: {error}")
                with self.lock:
                    self.connected = False
                self.emit_connection_status(False)
            
            def on_close(ws, close_status_code, close_msg):
                logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
                with self.lock:
                    self.connected = False
                self.emit_connection_status(False)
                
                with self.lock:
                    self.reconnect_attempts += 1
                    reconnect_msg = f"\n[Connection lost. Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}]"
                
                self.transcription_buffer += reconnect_msg
                self.emit_transcription(self.transcription_buffer)
                
                with self.lock:
                    should_reconnect = self.running and self.reconnect_attempts <= self.max_reconnect_attempts
                
                if should_reconnect:
                    self.emit_error("Reconnection needed")
            
            websocket_app = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            with self.lock:
                self.websocket = websocket_app
                self.reconnect_attempts = 0
            
            def run_websocket():
                with self.lock:
                    ws = self.websocket
                if ws:
                    ws.run_forever()
            
            websocket_thread = threading.Thread(target=run_websocket)
            websocket_thread.daemon = True
            websocket_thread.start()
            
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
        """Starts the communication thread."""
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
        """Stops communication and terminates all pending processes."""
        logger.info("Stop communication request received")
        with self.lock:
            self.running = False
            self.recording = False
            ws = self.websocket
        
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
        
        if ws and self.connected:
            try:
                logger.info("Closing WebSocket...")
                ws.close()
                logger.info("WebSocket closed")
            except Exception as e:
                logger.error("Error closing websocket: " + str(e))
        
        logger.info("Termination request completed")
    
    def start_recording(self):
        """Starts audio recording from the microphone."""
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
        """Stops audio recording."""
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            ws = self.websocket
            is_connected = self.connected
        
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
        
        if not (ws and is_connected):
            logger.warning("WebSocket not available to send requests")
            return
        
        try:
            if self.accumulated_audio and is_connected:
                self._send_entire_audio_message()
            
            with self.lock:
                ws = self.websocket
                is_pending = self.response_pending
            
            commit_message = {"type": "input_audio_buffer.commit"}
            ws.send(json.dumps(commit_message))
            logger.info("Audio input ended (final commit)")
            
            if not is_pending:
                response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                ws.send(json.dumps(response_request))
                logger.info("Final response request sent")
                with self.lock:
                    self.response_pending = True
            else:
                logger.info("Response already in progress, no new request sent")
        except Exception as e:
            logger.error("Error sending termination messages: " + str(e))
        
        with self.lock:
            self.response_pending = False
        
        logger.info("Audio recording stopped")
    
    def _record_audio(self):
        """Records audio in a loop until stopped."""
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
                            if len(self.accumulated_audio) >= 3200:  # Minimum audio required
                                logger.info(f"Pause detected ({current_time - self.silence_start_time:.2f}s) - sending partial audio")
                                self._send_entire_audio_message()
                                
                                with self.lock:
                                    ws = self.websocket
                                    is_connected = self.connected
                                    is_pending = self.response_pending
                                
                                if ws and is_connected:
                                    commit_message = {"type": "input_audio_buffer.commit"}
                                    ws.send(json.dumps(commit_message))
                                    logger.info("Partial audio commit sent")
                                    
                                    if not is_pending:
                                        response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                                        ws.send(json.dumps(response_request))
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
        """Calculates the RMS value for an audio buffer."""
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
        """Sends the entire accumulated audio as a single message."""
        with self.lock:
            if not self.accumulated_audio or not self.connected or not self.websocket:
                logger.warning("[AUDIO] Unable to send audio to OpenAI: websocket not connected or buffer empty")
                return
            ws = self.websocket
            audio_size = len(self.accumulated_audio)
        
        try:
            logger.info(f"[AUDIO] Preparing to send audio to OpenAI: {audio_size} bytes")
            base64_audio = base64.b64encode(self.accumulated_audio).decode('ascii')
            logger.info(f"[AUDIO] Audio encoded in base64: {len(base64_audio)} characters")
            
            audio_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_audio", "audio": base64_audio}]
                }
            }
            logger.info(f"[AUDIO] Sending audio message to OpenAI (WebSocket)")
            ws.send(json.dumps(audio_message))
            logger.info(f"[AUDIO] Audio successfully sent to OpenAI: {audio_size} bytes")
        except Exception as e:
            logger.error(f"[AUDIO] Error sending audio to OpenAI: {str(e)}")
    def send_text(self, text):
        """
        Sends a text message to the model through the websocket connection.
        
        Args:
            text: The text message to send
            
        Returns:
            bool: True if the send was successful, False otherwise
        """
        with self.lock:
            has_connection = self.connected and self.websocket
        
        if not has_connection:
            logger.error("Cannot send text: WebSocket not connected")
            return False
            
        try:
            # Create the text message
            text_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}]
                }
            }
            
            with self.lock:
                ws = self.websocket
                is_pending = self.response_pending
            
            # Send the message through the websocket
            ws.send(json.dumps(text_message))
            logger.info(f"Text message sent through websocket: {text[:50]}...")
            
            # Request a response
            if not is_pending:
                response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                ws.send(json.dumps(response_request))
                logger.info("Response request sent after text message")
                with self.lock:
                    self.response_pending = True
                
            # Reset the buffers
            self._response_buffer = ""
            
            return True
        except Exception as e:
            error_msg = f"Error sending text message: {str(e)}"
            logger.error(error_msg)
            return False
    
    def add_audio_data(self, audio_data):
        """
        Aggiunge dati audio esterni (dalla socket.io) al buffer audio.
        
        Args:
            audio_data: I dati audio da aggiungere (bytes)
            
        Returns:
            bool: True se l'aggiunta è riuscita, False altrimenti
        """
        audio_size = len(audio_data) if isinstance(audio_data, bytes) else 'non-binary'
        # Manteniamo un log essenziale senza dettagli specifici
        logger.info(f"[AUDIO] Ricevuti dati audio esterni: dimensione={audio_size}")
        
        with self.lock:
            if not self.connected or not self.websocket:
                logger.error("[AUDIO] Impossibile aggiungere dati audio: WebSocket non connesso")
                return False
            
            ws = self.websocket
        
        try:
            # Se i dati audio sono sufficienti, inviali direttamente
            if len(audio_data) >= 3200:  # Minimo di audio necessario
                # Invia audio come messaggio base64
                # Rimuoviamo log verbosi sulla codifica
                base64_audio = base64.b64encode(audio_data).decode('ascii')
                
                audio_message = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_audio", "audio": base64_audio}]
                    }
                }
                logger.info("[AUDIO] Invio messaggio audio a OpenAI...")
                ws.send(json.dumps(audio_message))
                logger.info("[AUDIO] Messaggio audio inviato con successo")
                
                # Invia commit per elaborare l'audio
                commit_message = {"type": "input_audio_buffer.commit"}
                ws.send(json.dumps(commit_message))
                logger.info("[AUDIO] Commit audio inviato")
                
                # Richiedi una risposta se non ce n'è già una in corso
                with self.lock:
                    is_pending = self.response_pending
                
                if not is_pending:
                    response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                    ws.send(json.dumps(response_request))
                    logger.info("[AUDIO] Richiesta risposta inviata")
                    with self.lock:
                        self.response_pending = True
                else:
                    logger.info("[AUDIO] Risposta già in corso, nessuna nuova richiesta inviata")
            else:
                logger.warning(f"[AUDIO] Buffer audio troppo piccolo ({len(audio_data)} bytes), non invio")
            
            return True
            
        except Exception as e:
            error_msg = f"[AUDIO] Errore elaborazione dati audio esterni: {str(e)}"
            logger.error(error_msg)
            return False 