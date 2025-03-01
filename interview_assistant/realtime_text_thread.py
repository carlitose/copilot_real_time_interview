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

import pyaudio
from PyQt5.QtCore import QThread, pyqtSignal

# Logging configuration
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

class RealtimeTextThread(QThread):
    """Thread for text (and audio) communication using the Realtime API."""
    transcription_signal = pyqtSignal(str)
    response_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    connection_status_signal = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.connected = False
        self.transcription_buffer = ""
        self.last_event_time = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        
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
        self.pause_duration = 0.7       # seconds of pause to activate commit
        self.min_commit_interval = 1.5  # minimum interval between commit
        self.is_speaking = False
        self.silence_start_time = 0
        self.last_commit_time = 0
        self.response_pending = False
        
        # Buffer for accumulating audio delta and response
        self._response_transcript_buffer = ""
        self._response_buffer = ""
        
        # Variable for containing final transcription
        self.current_text = ""

    async def realtime_session(self):
        """Manages a session for communication via the Realtime API."""
        try:
            self.transcription_signal.emit("Connessione alla Realtime API in corso...")
            
            import websockets
            import json
            import threading
            
            url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
            headers = [
                "Authorization: Bearer " + os.getenv('OPENAI_API_KEY'),
                "OpenAI-Beta: realtime=v1",
                "Content-Type: application/json"
            ]
            
            self.connected = False
            self.websocket = None
            self.websocket_thread = None
            
            def on_open(ws):
                logger.info("Connessione WebSocket stabilita")
                self.connected = True
                self.connection_status_signal.emit(True)
                self.last_event_time = time.time()
                self.current_text = ""
                
                session_config = {
                    "type": "update_session",
                    "capabilities": {
                        "audio": True,
                        "text": True
                    },
                    "use_model": "openai-gpt-4o"
                }
                
                try:
                    ws.send(json.dumps(session_config))
                    logger.info("Configurazione sessione inviata (audio e text)")
                except Exception as e:
                    logger.error("Errore invio configurazione: " + str(e))
                
                system_message = {
                    "type": "message",
                    "message": {
                        "role": "system",
                        "content": "You are a helpful AI assistant for technical interviews. Your responses will be shown on screen during an interview, so be clear and direct."
                    }
                }
                try:
                    ws.send(json.dumps(system_message))
                    logger.info("Messaggio di system prompt inviato")
                except Exception as e:
                    logger.error("Errore invio messaggio di system prompt: " + str(e))
                
                response_request = {
                    "type": "request_response"
                }
                try:
                    ws.send(json.dumps(response_request))
                    logger.info("Richiesta di risposta inviata")
                except Exception as e:
                    logger.error("Errore invio richiesta di risposta: " + str(e))
                
                self.transcription_signal.emit("Connesso! Pronto per l'intervista. Parla per fare domande.")
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    event_type = data.get("type")
                    
                    if event_type == "transcript":
                        # Handle audio transcription
                        delta = data.get("delta", "")
                        final = data.get("final", False)
                        
                        if delta or final:
                            self._response_transcript_buffer += delta
                            
                            logger.debug("Accumulated transcription delta: %s", delta)
                            
                            if final:
                                transcribed_text = self._response_transcript_buffer.strip()
                                self._response_transcript_buffer = ""
                                logger.info("Final audio transcription: %s", transcribed_text)
                                
                                if transcribed_text:
                                    self.current_text = transcribed_text
                                    self.transcription_signal.emit(transcribed_text)
                                    
                                    # If a delta arrived, wait for a bit to process any additional deltas
                                    if delta:
                                        self.last_event_time = time.time()
                                    
                    elif event_type == "assistant_response":
                        self._response_buffer += data.get("delta", "")
                        self.response_signal.emit(self._response_buffer)
                        
                    elif event_type == "error":
                        error = data.get('error', {})
                        error_msg = error.get('message', 'Unknown error')
                        self.error_signal.emit(f"API Error: {error_msg}")
                        logger.error("Error received: %s", error_msg)
                        
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
            
            def on_error(ws, error):
                logger.error("WebSocket Error: " + str(error))
                self.error_signal.emit(f"Connection error: {error}")
                self.connected = False
                self.connection_status_signal.emit(False)
            
            def on_close(ws, close_status_code, close_msg):
                logger.info(f"Connessione WebSocket chiusa: {close_status_code} - {close_msg}")
                self.connected = False
                self.connection_status_signal.emit(False)
                
                if self.running:
                    logger.warning("Connection closed. Attempt to reconnect...")
                    
                    # Try to reconnect if needed
                    if self.reconnect_attempts < self.max_reconnect_attempts:
                        self.reconnect_attempts += 1
                        logger.info(f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}...")
                        
                        # Wait a bit before reconnecting
                        time.sleep(2)
                        # Don't create a new WebSocketApp here to avoid recursion issues
                        # Instead, set a flag for the main thread to handle
                    else:
                        logger.error("Maximum reconnection attempts reached.")
                        self.error_signal.emit("Connection lost. Too many reconnection attempts.")
                        self.running = False
                else:
                    logger.info("Connection closed normally.")
            
            self.websocket = websockets.WebSocketApp(
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
                while self.running:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("Loop principale cancellato")
            finally:
                if self.websocket and self.connected:
                    try:
                        self.websocket.close()
                    except Exception as e:
                        logger.error("Errore nella chiusura del websocket: " + str(e))
                logger.info("Sessione WebSocket terminata")
        except Exception as e:
            error_msg = f"Errore critico: {e}"
            self.error_signal.emit(error_msg)
            logger.error(error_msg)
        finally:
            self.connected = False
            self.connection_status_signal.emit(False)
    
    def run(self):
        """Avvia il loop asincrono per la sessione."""
        self.running = True
        try:
            asyncio.run(self.realtime_session())
        except Exception as e:
            logger.error("Errore nel thread asincrono: " + str(e))
        logger.info("Thread di comunicazione terminato")
            
    def stop(self):
        """Ferma la comunicazione e termina tutti i processi pendenti."""
        logger.info("Richiesta di stop comunicazione ricevuta")
        self.running = False
        self.recording = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error("Errore nello stop dello stream: " + str(e))
        if self.p:
            try:
                self.p.terminate()
            except Exception as e:
                logger.error("Errore terminazione di PyAudio: " + str(e))
        if getattr(self, "websocket", None) and self.connected:
            try:
                logger.info("Chiusura WebSocket in corso...")
                self.websocket.close()
                logger.info("WebSocket chiuso")
            except Exception as e:
                logger.error("Errore nella chiusura del websocket: " + str(e))
        logger.info("Terminazione richiesta completata. Attendo la chiusura dei thread pendenti...")
        time.sleep(0.5)
    
    def start_recording(self):
        """Starts audio recording from the microphone."""
        if not self.p:
            try:
                self.p = pyaudio.PyAudio()
                self.stream = self.p.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK
                )
                self.recording = True
                
                # Start recording in a separate thread
                self.audio_thread = threading.Thread(target=self._record_audio)
                self.audio_thread.daemon = True
                self.audio_thread.start()
            except Exception as e:
                logger.error("Error initializing PyAudio: " + str(e))
                self.error_signal.emit("Audio initialization error")
                return
                
        logger.info("Audio recording started")
        self.transcription_signal.emit("Recording in progress... Speak now.")
    
    def stop_recording(self):
        """Stops audio recording."""
        if not self.recording:
            return
            
        # First set the flag so the recording thread can exit
        self.recording = False
        
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
        except Exception as e:
            logger.error("Error closing stream: " + str(e))
            
        try:
            if self.p:
                self.p.terminate()
                self.p = None
        except Exception as e:
            logger.error("Error terminating PyAudio: " + str(e))
            
        # Wait for audio thread to finish
        if hasattr(self, "audio_thread") and self.audio_thread:
            self.audio_thread.join(timeout=2.0)
        
        try:
            # Send commit message if needed to indicate end of audio input
            if self.websocket and self.websocket.sock:
                self.websocket.send(json.dumps({
                    "type": "end_audio"
                }))
        except Exception as e:
            logger.error("Error during termination message sending: " + str(e))
            
        logger.info("Audio recording stopped")
    
    def _record_audio(self):
        """Records audio from the microphone and sends it to the server."""
        try:
            last_rms_check_time = time.time()
            
            while self.recording and self.stream:
                try:
                    # Read audio data
                    data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                    
                    # Check for silence to detect end of speech
                    current_time = time.time()
                    if current_time - last_rms_check_time > 0.1:  # Check RMS every 100ms
                        rms = self._calculate_rms(data)
                        last_rms_check_time = current_time
                        
                        if rms < self.silence_threshold:
                            if not self.is_speaking:
                                pass  # Still silent
                            else:
                                # Was speaking, now silent - start measuring silence duration
                                if self.silence_start_time == 0:
                                    self.silence_start_time = current_time
                                elif current_time - self.silence_start_time > self.pause_duration:
                                    # Silence long enough, send accumulated audio
                                    if current_time - self.last_commit_time > self.min_commit_interval:
                                        self.last_commit_time = current_time
                                        # Logic for sending accumulated audio
                                        logger.info("Partial audio commit sent")
                        else:
                            # Not silent - speaking
                            self.is_speaking = True
                            self.silence_start_time = 0
                    
                    # If the websocket exists and is connected, send the audio data
                    if self.websocket and self.connected:
                        # Convert to base64 for sending over websocket
                        audio_base64 = base64.b64encode(data).decode('utf-8')
                        
                        # Send audio data to server
                        self.websocket.send(json.dumps({
                            "type": "audio_data",
                            "data": audio_base64,
                            "sample_rate": self.RATE
                        }))
                except Exception as inner_e:
                    logger.error(f"Error in audio processing loop: {inner_e}")
                    break
                    
            logger.info("Recording stop detected, exiting audio acquisition loop.")
                
        except Exception as e:
            logger.error("Error during recording: " + str(e))
            self.error_signal.emit("Recording error: " + str(e))
    
    def _calculate_rms(self, data):
        """Calculate Root Mean Square of audio data to detect silence."""
        try:
            # Convert binary data to numpy array
            data_np = np.frombuffer(data, dtype=np.int16)
            
            # Calculate RMS
            if len(data_np) > 0:
                rms = np.sqrt(np.mean(np.square(data_np.astype(np.float32))))
                if np.isnan(rms):
                    logger.warning("RMS calculation produced NaN, returning 0")
                    return 0
                return rms
            return 0
        except Exception as e:
            logger.error("Error in RMS calculation: " + str(e))
            return 0
    
    def _send_entire_audio_message(self):
        """Sends the entire accumulated audio data to the server."""
        try:
            if not self.accumulated_audio:
                return
                
            # Convert to base64 for sending over websocket
            audio_b64 = base64.b64encode(self.accumulated_audio).decode('utf-8')
            
            # Send audio data to server
            self.websocket.send(json.dumps({
                "type": "audio_data",
                "data": audio_b64,
                "sample_rate": self.RATE,
                "is_final": True
            }))
            
            # Clear accumulated audio
            self.accumulated_audio = b''
        except Exception as e:
            logger.error("Error sending single audio message: " + str(e)) 