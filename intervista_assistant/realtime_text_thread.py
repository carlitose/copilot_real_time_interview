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

# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

class RealtimeTextThread(QThread):
    """Thread per comunicazione testuale (e audio) usando la Realtime API."""
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
        
        # Configurazione audio
        self.recording = False
        self.audio_buffer = []
        self.accumulated_audio = b''
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        self.p = None
        self.stream = None
        
        # Configurazione per il rilevamento delle pause
        self.last_audio_commit_time = 0
        self.silence_threshold = 500  # valore RMS per definire il silenzio
        self.pause_duration = 0.7       # secondi di pausa per attivare il commit
        self.min_commit_interval = 1.5  # minimo intervallo tra commit
        self.is_speaking = False
        self.silence_start_time = 0
        self.last_commit_time = 0
        self.response_pending = False
        
        # Buffer per accumulare i delta della trascrizione audio e della risposta
        self._response_transcript_buffer = ""
        self._response_buffer = ""
        
        # Variabile per contenere la trascrizione finale
        self.current_text = ""

    async def realtime_session(self):
        """Gestisce una sessione per la comunicazione tramite Realtime API."""
        try:
            self.transcription_signal.emit("Connessione alla Realtime API in corso...")
            
            import websocket
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
                    logger.info("Configurazione sessione inviata (audio e text)")
                except Exception as e:
                    logger.error("Errore invio configurazione: " + str(e))
                
                system_message = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "system",
                        "content": [{
                            "type": "input_text",
                            "text": "Sei un assistente AI per interviste di lavoro, specializzato in domande per software engineer. Rispondi in modo conciso e strutturato."
                        }]
                    }
                }
                try:
                    ws.send(json.dumps(system_message))
                    logger.info("Messaggio di system prompt inviato")
                except Exception as e:
                    logger.error("Errore invio messaggio di system prompt: " + str(e))
                
                response_request = {
                    "type": "response.create",
                    "response": {"modalities": ["text"]}
                }
                try:
                    ws.send(json.dumps(response_request))
                    logger.info("Richiesta di risposta inviata")
                except Exception as e:
                    logger.error("Errore invio richiesta di risposta: " + str(e))
                
                self.transcription_signal.emit("Connesso! Pronto per l'intervista. Parla per fare domande.")
            
            def on_message(ws, message):
                try:
                    event = json.loads(message)
                    event_type = event.get('type', 'sconosciuto')
                    logger.debug(f"Evento ricevuto: {event_type}")
                    
                    if event_type == 'response.audio_transcript.delta':
                        delta = event.get('delta', '')
                        self._response_transcript_buffer += delta
                        logger.debug("Trascrizione delta accumulata: %s", delta)
                    elif event_type == 'response.audio_transcript.done':
                        transcribed_text = self._response_transcript_buffer.strip()
                        self.current_text = transcribed_text
                        self.response_signal.emit(transcribed_text)
                        logger.info("Trascrizione audio finale: %s", transcribed_text)
                        self._response_transcript_buffer = ""
                    elif event_type == 'response.text.delta':
                        delta = event.get('delta', '')
                        self._response_buffer += delta
                        logger.debug("Accumulated delta: %s", delta)
                    elif event_type in ('response.text.done', 'response.done'):
                        if self._response_buffer.strip():
                            self.response_signal.emit(self._response_buffer)
                            logger.info("Response completata: %s", self._response_buffer)
                            self._response_buffer = ""
                    elif event_type == 'error':
                        self.response_pending = False
                        error = event.get('error', {})
                        error_msg = error.get('message', 'Errore sconosciuto')
                        self.error_signal.emit(f"Errore API: {error_msg}")
                        logger.error("Errore ricevuto: %s", error_msg)
                    else:
                        logger.debug("Messaggio ricevuto di tipo %s", event_type)
                except Exception as e:
                    logger.error("Eccezione in on_message: " + str(e))
            
            def on_error(ws, error):
                logger.error("Errore WebSocket: " + str(error))
                self.error_signal.emit(f"Errore di connessione: {error}")
                self.connected = False
                self.connection_status_signal.emit(False)
            
            def on_close(ws, close_status_code, close_msg):
                logger.info(f"Connessione WebSocket chiusa: {close_status_code} - {close_msg}")
                self.connected = False
                self.connection_status_signal.emit(False)
                
                self.reconnect_attempts += 1
                reconnect_msg = f"\n[Connessione persa. Tentativo di riconnessione {self.reconnect_attempts}/{self.max_reconnect_attempts}]"
                self.transcription_buffer += reconnect_msg
                self.transcription_signal.emit(self.transcription_buffer)
                
                if self.running and self.reconnect_attempts <= self.max_reconnect_attempts:
                    self.error_signal.emit("Riconnessione necessaria")
            
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
        """Avvia la registrazione audio dal microfono."""
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
            logger.error("Errore nell'inizializzazione di PyAudio: " + str(e))
            self.error_signal.emit("Errore inizializzazione audio")
            return
        threading.Thread(target=self._record_audio, daemon=True).start()
        logger.info("Registrazione audio avviata")
        self.transcription_signal.emit("Registrazione in corso... Parla adesso.")
    
    def stop_recording(self):
        """Ferma la registrazione audio."""
        if not self.recording:
            return
        self.recording = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error("Errore nella chiusura dello stream: " + str(e))
        if self.p:
            try:
                self.p.terminate()
            except Exception as e:
                logger.error("Errore nella terminazione di PyAudio: " + str(e))
        if not (hasattr(self, 'websocket') and self.websocket and self.connected):
            logger.warning("WebSocket non disponibile per inviare richieste")
            return
        try:
            if self.accumulated_audio and self.connected:
                self._send_entire_audio_message()
            commit_message = {"type": "input_audio_buffer.commit"}
            self.websocket.send(json.dumps(commit_message))
            logger.info("Audio input terminato (commit finale)")
            if not self.response_pending:
                response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                self.websocket.send(json.dumps(response_request))
                logger.info("Richiesta risposta finale inviata")
            else:
                logger.info("Risposta già in corso, non inviata nuova richiesta")
        except Exception as e:
            logger.error("Errore durante l'invio dei messaggi di terminazione: " + str(e))
        self.response_pending = False
        logger.info("Registrazione audio fermata")
    
    def _record_audio(self):
        """Registra audio in loop fino a quando non viene fermato."""
        try:
            self.last_commit_time = time.time()
            while self.recording and self.stream:
                data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                self.audio_buffer.append(data)
                self.accumulated_audio += data
                rms = self._calculate_rms(data)
                current_time = time.time()
                if rms > self.silence_threshold:
                    if not self.is_speaking:
                        logger.info(f"Inizio parlato rilevato (RMS: {rms})")
                        self.is_speaking = True
                    self.silence_start_time = 0
                else:
                    if self.is_speaking:
                        if self.silence_start_time == 0:
                            self.silence_start_time = current_time
                        elif (current_time - self.silence_start_time >= self.pause_duration and 
                              current_time - self.last_commit_time >= self.min_commit_interval):
                            if len(self.accumulated_audio) >= 3200:
                                logger.info(f"Pausa rilevata ({current_time - self.silence_start_time:.2f}s) - invio audio parziale")
                                self._send_entire_audio_message()
                                commit_message = {"type": "input_audio_buffer.commit"}
                                self.websocket.send(json.dumps(commit_message))
                                logger.info("Commit dell'audio parziale inviato")
                                if not self.response_pending:
                                    response_request = {"type": "response.create", "response": {"modalities": ["text"]}}
                                    self.websocket.send(json.dumps(response_request))
                                    logger.info("Richiesta di risposta inviata dopo audio parziale")
                                    self.response_pending = True
                                self.last_commit_time = current_time
                                self.silence_start_time = 0
                                self.accumulated_audio = b''
                                self.audio_buffer = []
                                self.is_speaking = False
                            else:
                                logger.info(f"Pausa rilevata ma buffer troppo piccolo ({len(self.accumulated_audio)} bytes), continuo ad accumulare")
                if not self.recording:
                    logger.info("Stop della registrazione rilevato, uscita dal ciclo di acquisizione audio.")
                    break
        except Exception as e:
            logger.error("Errore durante la registrazione: " + str(e))
            self.error_signal.emit("Errore registrazione: " + str(e))
            self.recording = False
    
    def _calculate_rms(self, data):
        """Calcola il valore RMS per un buffer audio."""
        try:
            shorts = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(np.square(shorts)))
            if np.isnan(rms):
                logger.warning("Il calcolo dell'RMS ha prodotto NaN, ritorno 0")
                return 0
            return rms
        except Exception as e:
            logger.error("Errore nel calcolo RMS: " + str(e))
            return 0
    
    def _send_entire_audio_message(self):
        """Invia l'intero audio accumulato come un singolo messaggio."""
        if not self.accumulated_audio or not self.connected:
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
            logger.info("Messaggio audio unico inviato")
        except Exception as e:
            logger.error("Errore nell'invio del messaggio audio unico: " + str(e)) 