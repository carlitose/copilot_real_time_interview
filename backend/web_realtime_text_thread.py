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
import uuid

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
        
        # Path to the system prompt file
        self.system_prompt_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "system_prompt.json"
        )
        
        # Audio configuration
        self.recording = False
        self.audio_buffer = []
        self.accumulated_audio = b''  # Buffer per l'audio dal microfono
        self.external_audio_buffer = b''  # Buffer per l'audio esterno ricevuto via socket.io
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 24000  # Impostato a 24kHz per compatibilità con OpenAI
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
        self.lock = threading.Lock()  # Per sincronizzare l'accesso alle risorse
        
        # Nuovo: Gestione buffer audio migliorata
        self.audio_accumulation_time = 0  # Tempo accumulato di audio (ms)
        self.min_audio_before_commit = 2000  # Minimo 2s di audio prima di inviare
        self.commit_delay = 0.05  # 50ms di ritardo tra invio audio e commit
        self.last_audio_send_time = 0  # Per tracciare l'ultimo invio di audio
        self.last_commit_send_time = 0  # Per tracciare l'ultimo commit inviato
        
        # Websocket e stato
        self.websocket = None
        self.websocket_app = None
        
        # API token from environment
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            logger.error("OPENAI_API_KEY not found in environment variables")
        
        # System message
        self.system_prompt = self._load_system_prompt()
        
        # Buffer to accumulate audio transcription deltas and response
        self._response_transcript_buffer = ""
        self._response_buffer = ""
        
        # Variable to hold the final transcription
        self.current_text = ""
    
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
                system_message_json = json.load(f)
                # Ora valorizziamo solo il testo del prompt invece dell'intero oggetto
                system_text = system_message_json["item"]["content"][0]["text"]
            logger.info("System prompt loaded from file: %s", self.system_prompt_path)
            return system_text
        except Exception as e:
            logger.error("Error loading system prompt from file: %s", str(e))
            # Fallback to default system prompt
            return "You are an AI assistant for job interviews, specialized in questions for software engineers. Respond concisely and structured."
    
    async def realtime_session(self):
        """
        Establishes and manages the WebSocket connection to the OpenAI Realtime API.
        """
        logger.info("[WEBSOCKET] Starting realtime session")
        
        try:
            url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
            self.headers = [
                f"Authorization: Bearer {self.api_key}",
                "OpenAI-Beta: realtime=v1",
                "Content-Type: application/json"
            ]
            
            # Reset connection state
            self.connected = False
            self.websocket = None
            
            # Define WebSocket callbacks
            def on_open(ws):
                logger.info("[WEBSOCKET] Connection established")
                with self.lock:
                    self.connected = True
                self.emit_connection_status(True)
                
                # Configure session with audio and text capabilities
                session_config = {
                    "type": "session.update",
                    "session": {
                        "modalities": ["text", "audio"],  # Abilita sia testo che audio
                        "input_audio_format": "pcm16",  # Specifica formato audio in ingresso
                        "output_audio_format": "pcm16", # Specifica formato audio in uscita
                        "input_audio_transcription": {
                            "model": "whisper-1"
                        },
                        "tool_choice": "auto"  # Importante per versioni recenti dell'API
                    }
                }
                
                logger.info("[WEBSOCKET] Sending session configuration")
                ws.send(json.dumps(session_config))
                
                # Send system prompt
                if self.system_prompt:
                    system_message = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "input_text", "text": self.system_prompt}]
                        }
                    }
                    logger.info("[WEBSOCKET] Sending system prompt")
                    ws.send(json.dumps(system_message))
                    
                    # Invia un segnale iniziale per ottenere una prima risposta
                    welcome_message = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Please confirm you're ready to assist with the interview."}]
                        }
                    }
                    ws.send(json.dumps(welcome_message))
                    logger.info("[WEBSOCKET] Sent initial prompt to get first response")
                    
                    response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                    ws.send(json.dumps(response_request))
                    with self.lock:
                        self.response_pending = True
            
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
                    prev_reconnect = self.reconnect_attempts
                    self.reconnect_attempts += 1
                    should_reconnect = self.running and self.reconnect_attempts <= self.max_reconnect_attempts
                    reconnect_msg = f"\n[Connection lost. Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}]"
                
                # Notifica l'UI
                self.emit_connection_status(False)
                self.transcription_buffer += reconnect_msg
                self.emit_transcription(self.transcription_buffer)
                
                # Decidere se riconnettersi in base allo stato attuale
                logger.info(f"Reconnection status: should_reconnect={should_reconnect}, running={self.running}, attempts={self.reconnect_attempts}/{self.max_reconnect_attempts}")
                
                if should_reconnect:
                    try:
                        # Evita di avviare due tentativi di riconnessione in parallelo
                        if prev_reconnect < self.reconnect_attempts:
                            logger.info(f"Attempting reconnection ({self.reconnect_attempts}/{self.max_reconnect_attempts})...")
                            
                            # Attesa con backoff esponenziale
                            wait_time = min(2 ** self.reconnect_attempts, 10)  # max 10 secondi di attesa
                            logger.info(f"Waiting {wait_time} seconds before reconnection...")
                            
                            # Segnala la necessità di riconnettersi
                            self.emit_error("Reconnection needed")
                            
                            # Usa un thread separato per non bloccare il thread principale
                            def delayed_reconnect():
                                time.sleep(wait_time)
                                if self.running:
                                    try:
                                        logger.info("Starting reconnection thread")
                                        reconnect_thread = threading.Thread(target=run_websocket)
                                        reconnect_thread.daemon = True
                                        reconnect_thread.start()
                                    except Exception as e:
                                        logger.error(f"Error starting reconnection thread: {str(e)}")
                            
                            # Avvia il thread di riconnessione
                            threading.Thread(target=delayed_reconnect, daemon=True).start()
                    except Exception as e:
                        logger.error(f"Error during reconnection process: {str(e)}")
                else:
                    logger.warning("Maximum reconnection attempts reached or session stopped, giving up")
            
            websocket_app = websocket.WebSocketApp(
                url,
                header=self.headers,
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
            # Assicuriamoci che ci sia abbastanza audio (minimo 100ms)
            min_bytes = int(self.RATE * 0.1) * 2  # 100ms di audio a RATE Hz (2 bytes per sample)
            if audio_size < min_bytes:
                logger.warning(f"[AUDIO] Buffer troppo piccolo ({audio_size}/{min_bytes} bytes), non invio")
                return
            
            logger.info(f"[AUDIO] Preparing to send audio to OpenAI: {audio_size} bytes")
            base64_audio = base64.b64encode(self.accumulated_audio).decode('ascii')
            
            # Inviamo l'audio esattamente come fa la versione desktop - semplice e senza parametri extra
            audio_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_audio", "audio": base64_audio}]
                }
            }
            
            logger.info(f"[AUDIO] Sending audio message to OpenAI ({audio_size} bytes)")
            ws.send(json.dumps(audio_message))
            logger.info(f"[AUDIO] Audio successfully sent to OpenAI")
        except Exception as e:
            logger.error(f"[AUDIO] Error sending audio to OpenAI: {str(e)}")
    
    def send_text(self, text):
        """
        Invia un messaggio testuale al modello via WebSocket.
        
        Args:
            text: The text message to send
            
        Returns:
            bool: True if the message was sent successfully, False otherwise
        """
        with self.lock:
            if not self.connected or not self.websocket:
                return False
            ws = self.websocket
        
        try:
            # Create a text message in the format expected by the API
            text_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}]
                }
            }
            
            # Check if there's already a response pending
            with self.lock:
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
            audio_data: I dati audio da aggiungere (array o bytes)
            
        Returns:
            bool: True se l'aggiunta è riuscita, False altrimenti
        """
        try:
            # Converti i dati in format bytes se necessario
            audio_bytes = None
            if isinstance(audio_data, bytes):
                audio_bytes = audio_data
            elif isinstance(audio_data, np.ndarray):
                audio_bytes = audio_data.tobytes()
            elif isinstance(audio_data, list):
                # Converti liste di numeri in np.ndarray e poi in bytes
                audio_array = np.array(audio_data, dtype=np.int16)
                audio_bytes = audio_array.tobytes()
            else:
                logger.error(f"[AUDIO] Tipo di dati audio non supportato: {type(audio_data)}")
                return False
            
            audio_size = len(audio_bytes)
            # Calcolo durata approssimativa dell'audio (in ms)
            approx_duration_ms = (audio_size / 2) / (self.RATE / 1000)
            logger.info(f"[AUDIO] Ricevuti dati audio esterni: dimensione={audio_size}, durata={approx_duration_ms:.2f}ms")
            
            with self.lock:
                # Aggiungi i dati al buffer accumulato
                self.external_audio_buffer += audio_bytes
                self.audio_accumulation_time += approx_duration_ms
                
                # Se il websocket non è connesso, mantieni in buffer per invio successivo
                if not self.connected or not self.websocket:
                    logger.warning(f"[AUDIO] WebSocket non connesso. Dati audio in buffer per futuro invio (buffer size={len(self.external_audio_buffer)} bytes)")
                    return False
                
                # Se non c'è abbastanza audio accumulato, attendi ancora
                if self.audio_accumulation_time < self.min_audio_before_commit:
                    logger.info(f"[AUDIO] Accumulati {self.audio_accumulation_time:.2f}ms di audio (min. richiesto: {self.min_audio_before_commit}ms)")
                    return True
                
                # Se c'è una risposta pendente, non inviare altro audio ancora
                if self.response_pending:
                    logger.info(f"[AUDIO] Risposta già in attesa. Accumulando audio (buffer={len(self.external_audio_buffer)} bytes).")
                    return True
                
                # Verifica che il buffer contenga abbastanza dati per evitare errori
                if len(self.external_audio_buffer) < 2000:  # Assicurati che ci siano almeno 2KB di dati audio
                    logger.warning(f"[AUDIO] Buffer troppo piccolo ({len(self.external_audio_buffer)} bytes). Continuo ad accumulare.")
                    return True
                
                # Prepariamo una copia locale del buffer audio (per usarla fuori dal lock)
                send_buffer = self.external_audio_buffer
                buffer_duration_ms = self.audio_accumulation_time
                
                # Reset del buffer PRIMA di rilasciare il lock
                self.external_audio_buffer = b''
                self.audio_accumulation_time = 0
                self.last_audio_send_time = time.time()
                
                # Cattura il websocket mentre abbiamo il lock
                ws = self.websocket
            
            # Converti audio in base64
            base64_audio = base64.b64encode(send_buffer).decode('ascii')
            
            # Log dettagliato delle dimensioni e durata
            logger.info(f"[AUDIO] Preparazione messaggio audio: {len(send_buffer)} bytes, {buffer_duration_ms:.2f}ms")
            
            # Usiamo il formato corretto per l'API OpenAI Realtime
            try:
                # Controlla ancora una volta lo stato della connessione
                if not ws or not self.connected:
                    logger.warning("[AUDIO] WebSocket disconnesso durante preparazione messaggio, annullo invio")
                    return False
                
                # 1. Invia il messaggio audio usando il formato corretto per l'API
                # Formato corretto secondo la documentazione: input_audio_buffer.append
                audio_message = {
                    "event_id": f"audio_{int(time.time()*1000)}",
                    "type": "input_audio_buffer.append",
                    "audio": base64_audio
                }
                
                logger.info(f"[AUDIO] Invio messaggio audio: {len(send_buffer)} bytes, durata={buffer_duration_ms:.2f}ms")
                ws.send(json.dumps(audio_message))
                logger.info("[AUDIO] Messaggio audio inviato con successo")
                
                # Breve pausa prima del commit
                time.sleep(self.commit_delay)
                
                # 2. Invia un commit nel formato corretto
                commit_message = {
                    "event_id": f"commit_{int(time.time()*1000)}",
                    "type": "input_audio_buffer.commit"
                }
                ws.send(json.dumps(commit_message))
                logger.info(f"[AUDIO] Commit audio inviato dopo {self.commit_delay*1000:.0f}ms")
                
                # 3. Invia una richiesta di risposta
                with self.lock:
                    is_pending = self.response_pending
                
                if not is_pending:
                    # Richiedi una risposta dopo l'invio dell'audio
                    response_request = {
                        "type": "response.create",
                        "response": {"modalities": ["text"]}
                    }
                    ws.send(json.dumps(response_request))
                    logger.info("[AUDIO] Richiesta risposta inviata")
                    with self.lock:
                        self.response_pending = True
                else:
                    logger.warning("[AUDIO] Risposta già in attesa, nuova richiesta non inviata")
                
                return True
            except Exception as e:
                error_msg = f"[AUDIO] Errore durante invio audio: {str(e)}"
                logger.error(error_msg)
                self.emit_error(error_msg)
                return False
        except Exception as e:
            error_msg = f"Errore durante l'aggiunta dei dati audio: {str(e)}"
            logger.error(error_msg)
            self.emit_error(error_msg)
            return False 