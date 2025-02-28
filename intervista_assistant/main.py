#!/usr/bin/env python3
import sys
import os
import time
import json
import logging
import asyncio
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                            QHBoxLayout, QWidget, QTextEdit, QLabel, QSplitter,
                            QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from openai import OpenAI
from dotenv import load_dotenv

import markdown  # Per convertire markdown in HTML

from .utils import ScreenshotManager

import pyaudio
import threading
import base64
import numpy as np


# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

# Carica variabili d'ambiente
load_dotenv()

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
        self.accumulated_audio = b''  # Accumula l'audio per invio in un unico messaggio
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
        self.buffer_size_to_send = 40   # non più usato
        
        # Variabile per contenere (eventualmente) la trascrizione della voce.
        self.current_text = ""
        
        # Buffer per accumulare i delta della trascrizione audio
        self._response_transcript_buffer = ""
        
        # Buffer per accumulare i delta della risposta
        self._response_buffer = ""

    async def realtime_session(self):
        """Gestisce una sessione per la comunicazione tramite Realtime API."""
        try:
            self.transcription_signal.emit("Connessione alla Realtime API in corso...")
            
            import websocket
            import json
            import threading
            
            # Modifica dell'URL: usa lo stesso modello degli esempi asincroni
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
                
                # Configurazione della sessione aggiornata senza la sezione "tools"
                session_config = {
                    "event_id": "event_123",  # identificatore univoco per l'evento, se necessario
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
                        # Rimosso il blocco 'tools' e correlati
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
                
                # Reinserisci il system prompt per istruire il modello
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
                
                # Invio della richiesta di risposta
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
                        # Gestire altri eventi se necessario
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
            
            # Loop principale della sessione asincrona
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
        self.recording = False  # Assicurati di interrompere il ciclo di registrazione

        # Se la registrazione sta ancora andando, interrompi e chiudi lo stream
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

        # Se il websocket è attivo, chiudilo
        if getattr(self, "websocket", None) and self.connected:
            try:
                logger.info("Chiusura WebSocket in corso...")
                self.websocket.close()
                logger.info("WebSocket chiuso")
            except Exception as e:
                logger.error("Errore nella chiusura del websocket: " + str(e))
        
        logger.info("Terminazione richiesta completata. Attendo la chiusura dei thread pendenti...")

        # Aggiungi un piccolo delay per dare il tempo ai thread di terminare
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
            # Invia il messaggio audio unico con tutto l'audio registrato
            if self.accumulated_audio and self.connected:
                self._send_entire_audio_message()
            
            # Invia il commit finale dell'audio
            commit_message = {"type": "input_audio_buffer.commit"}
            self.websocket.send(json.dumps(commit_message))
            logger.info("Audio input terminato (commit finale)")
            
            # Invia la richiesta per la risposta
            if not self.response_pending:
                response_request = {
                    "type": "response.create",
                    "response": {"modalities": ["text"]}
                }
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
                
                # Calcolo RMS per eventuale logging (opzionale)
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
                                # Invia l'audio accumulato in un unico messaggio parziale
                                self._send_entire_audio_message()
                                
                                # Invia il commit per il messaggio audio parziale
                                commit_message = {"type": "input_audio_buffer.commit"}
                                self.websocket.send(json.dumps(commit_message))
                                logger.info("Commit dell'audio parziale inviato")
                                
                                # Invia la richiesta per la risposta, se non in corso
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
                                # Non aggiornare last_commit_time o resettare il buffer, per continuare ad accumulare
                
                if not self.recording:
                    logger.info("Stop della registrazione rilevato, uscita dal ciclo di acquisizione audio.")
                    break
        except Exception as e:
            logger.error("Errore durante la registrazione: " + str(e))
            self.error_signal.emit("Errore registrazione: " + str(e))
            self.recording = False

    def _calculate_rms(self, data):
        """Calcola il valore RMS (Root Mean Square) per un buffer audio.
        
        Viene usata una conversione in float32 per evitare overflow e NaN.
        """
        try:
            # Converte il buffer in un array di float32
            shorts = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(np.square(shorts)))
            # Se per qualche motivo rms risulta NaN, ritorna 0
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


class IntervistaAssistant(QMainWindow):
    """Applicazione principale per l'assistente di interviste."""
    
    def __init__(self):
        super().__init__()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            QMessageBox.critical(self, "Errore API Key", 
                                "API Key OpenAI non trovata. Imposta la variabile d'ambiente OPENAI_API_KEY.")
            sys.exit(1)
        self.client = OpenAI(api_key=api_key)
        self.recording = False
        self.text_thread = None
        self.chat_history = []
        self.shutdown_in_progress = False
        self.screenshot_manager = ScreenshotManager()
        self.init_ui()
        
    def init_ui(self):
        """Inizializza l'interfaccia utente."""
        self.setWindowTitle("Assistente Intervista Software Engineer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Impostazione del font predefinito più grande per tutta l'app
        app_font = QFont("Arial", 12)
        QApplication.setFont(app_font)
        
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        splitter = QSplitter(Qt.Vertical)
        
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        
        input_label = QLabel("Input dell'utente (audio):")
        input_label.setFont(QFont("Arial", 14, QFont.Bold))
        
        self.transcription_text = QTextEdit()
        self.transcription_text.setReadOnly(True)
        self.transcription_text.setFont(QFont("Arial", 13))
        self.transcription_text.setMinimumHeight(150)
        
        # Tasto "Parla" rimosso perché l'app inizierà ad ascoltare subito dopo il "Inizia Sessione".
        # self.speak_button = QPushButton("Parla")
        # self.speak_button.setFont(QFont("Arial", 11))
        # self.speak_button.clicked.connect(self.toggle_speaking)
        # self.speak_button.setEnabled(False)
        
        input_layout.addWidget(input_label)
        input_layout.addWidget(self.transcription_text)
        # Il tasto "Parla" non viene più aggiunto all'interfaccia.
        # input_layout.addWidget(self.speak_button)
        
        response_container = QWidget()
        response_layout = QVBoxLayout(response_container)
        
        response_label = QLabel("Risposta:")
        response_label.setFont(QFont("Arial", 14, QFont.Bold))
        
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setFont(QFont("Arial", 13))
        # Configura il QTextEdit per interpretare HTML
        self.response_text.setAcceptRichText(True)
        
        response_layout.addWidget(response_label)
        response_layout.addWidget(self.response_text)
        
        splitter.addWidget(input_container)
        splitter.addWidget(response_container)
        splitter.setSizes([300, 500])
        
        controls_layout = QHBoxLayout()
        
        self.record_button = QPushButton("Inizia Sessione")
        self.record_button.setFont(QFont("Arial", 13))
        self.record_button.clicked.connect(self.toggle_recording)
        
        self.clear_button = QPushButton("Pulisci")
        self.clear_button.setFont(QFont("Arial", 13))
        self.clear_button.clicked.connect(self.clear_text)
        
        self.screenshot_button = QPushButton("Screenshot")
        self.screenshot_button.setFont(QFont("Arial", 13))
        self.screenshot_button.clicked.connect(self.take_screenshot)
        
        self.share_button = QPushButton("Condividi Screenshot")
        self.share_button.setFont(QFont("Arial", 13))
        self.share_button.clicked.connect(self.share_screenshot)
        
        self.save_button = QPushButton("Salva Conversazione")
        self.save_button.setFont(QFont("Arial", 13))
        self.save_button.clicked.connect(self.save_conversation)
        
        controls_layout.addWidget(self.record_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.screenshot_button)
        controls_layout.addWidget(self.share_button)
        controls_layout.addWidget(self.save_button)
        
        main_layout.addWidget(splitter)
        main_layout.addLayout(controls_layout)
        
        self.setCentralWidget(central_widget)
        
    def toggle_recording(self):
        """Attiva o disattiva la connessione al modello e inizia immediatamente la registrazione."""
        if not self.recording:
            self.recording = True
            self.record_button.setText("Termina Sessione")
            self.record_button.setStyleSheet("background-color: #ff5555;")
            
            self.text_thread = RealtimeTextThread()
            self.text_thread.transcription_signal.connect(self.update_transcription)
            self.text_thread.response_signal.connect(self.update_response)
            self.text_thread.error_signal.connect(self.show_error)
            self.text_thread.connection_status_signal.connect(self.update_connection_status)
            self.text_thread.finished.connect(self.recording_finished)
            self.text_thread.start()
            
            # Avvio automatico della registrazione subito dopo inizializzazione della sessione
            while not self.text_thread.connected:
                time.sleep(0.1)
            self.text_thread.start_recording()
        else:
            if self.shutdown_in_progress:
                return
                
            self.shutdown_in_progress = True
            self.record_button.setText("Terminazione in corso...")
            self.record_button.setEnabled(False)
            
            if hasattr(self.text_thread, 'recording') and self.text_thread.recording:
                try:
                    self.text_thread.stop_recording()
                except Exception as e:
                    logger.error("Errore durante lo stop_recording: " + str(e))
            
            try:
                if self.text_thread:
                    self.text_thread.stop()
                    self.text_thread.wait(2000)
            except Exception as e:
                logger.error("Errore durante la terminazione della sessione: " + str(e))
                self.recording_finished()
    
    def recording_finished(self):
        """Chiamato quando il thread è terminato."""
        self.recording = False
        self.shutdown_in_progress = False
        self.record_button.setText("Inizia Sessione")
        self.record_button.setStyleSheet("")
        self.record_button.setEnabled(True)
        self.transcription_text.append("\n[Sessione terminata]")
    
    def update_connection_status(self, connected):
        """Aggiorna l'interfaccia in base allo stato della connessione."""
        if connected:
            self.record_button.setStyleSheet("background-color: #55aa55;")
        else:
            if self.recording:
                self.record_button.setStyleSheet("background-color: #ff5555;")
    
    def update_transcription(self, text):
        """Aggiorna il campo della trascrizione."""
        if text == "Registrazione in corso...":
            self.transcription_text.setText(text)
            return
            
        if text.startswith('\n[Audio processato alle'):
            formatted_timestamp = f"\n--- {text.strip()} ---\n"
            current_text = self.transcription_text.toPlainText()
            if current_text == "Registrazione in corso...":
                self.transcription_text.setText(formatted_timestamp)
            else:
                self.transcription_text.append(formatted_timestamp)
        else:
            self.transcription_text.append(text)
        
        self.transcription_text.verticalScrollBar().setValue(
            self.transcription_text.verticalScrollBar().maximum()
        )
        
        if text != "Registrazione in corso...":
            if not self.chat_history or self.chat_history[-1]["role"] != "user" or self.chat_history[-1]["content"] != text:
                self.chat_history.append({"role": "user", "content": text})
    
    def update_response(self, text):
        """Aggiorna il campo della risposta con formattazione markdown."""
        if not text:
            return
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Stile CSS completamente rivisto per uniformità
        html_style = """
        <style>
            /* Stili base uniformi */
            body, p, div, span, li, td, th {
                font-family: 'Arial', sans-serif !important;
                font-size: 14px !important;
                line-height: 1.6 !important;
                color: #333333 !important;
            }
            
            /* Titoli con dimensioni proporzionali */
            h1 { font-size: 20px !important; margin: 20px 0 10px 0 !important; font-weight: bold !important; }
            h2 { font-size: 18px !important; margin: 18px 0 9px 0 !important; font-weight: bold !important; }
            h3 { font-size: 16px !important; margin: 16px 0 8px 0 !important; font-weight: bold !important; }
            h4 { font-size: 15px !important; margin: 14px 0 7px 0 !important; font-weight: bold !important; }
            
            /* Blocchi di codice */
            pre {
                background-color: #f5f5f5 !important;
                border: 1px solid #cccccc !important;
                border-radius: 4px !important;
                padding: 10px !important;
                margin: 10px 0 !important;
                overflow-x: auto !important;
                font-family: Consolas, 'Courier New', monospace !important;
                font-size: 14px !important;
                line-height: 1.45 !important;
                tab-size: 4 !important;
                white-space: pre !important;
            }
            
            /* Codice inline */
            code {
                font-family: Consolas, 'Courier New', monospace !important;
                font-size: 14px !important;
                background-color: #f5f5f5 !important;
                padding: 2px 4px !important;
                border-radius: 3px !important;
                border: 1px solid #cccccc !important;
                color: #333333 !important;
                white-space: pre !important;
            }
            
            /* Liste uniformi */
            ul, ol { 
                margin: 10px 0 10px 20px !important; 
                padding-left: 20px !important; 
            }
            li { 
                margin-bottom: 6px !important; 
            }
            
            /* Paragrafi con spaziatura uniforme */
            p { 
                margin: 10px 0 !important;
            }
            
            /* Enfasi del testo */
            strong { font-weight: bold !important; }
            em { font-style: italic !important; }
            
            /* Tabelle */
            table {
                border-collapse: collapse !important;
                width: 100% !important;
                margin: 15px 0 !important;
                font-size: 14px !important;
            }
            th, td {
                border: 1px solid #dddddd !important;
                padding: 8px !important;
                text-align: left !important;
            }
            th {
                background-color: #f2f2f2 !important;
                font-weight: bold !important;
            }
            
            /* Intestazione risposta */
            .response-header {
                color: #666666 !important;
                font-size: 13px !important;
                margin: 15px 0 10px 0 !important;
                border-bottom: 1px solid #eeeeee !important;
                padding-bottom: 5px !important;
                font-weight: bold !important;
            }
        </style>
        """
        
        # Intestazione con timestamp
        header = f'<div class="response-header">--- Risposta alle {current_time} ---</div>'
        
        # Processo manuale del testo per garantire uniformità
        def process_code_blocks(text):
            """Processa i blocchi di codice preservando spazi e formattazione"""
            import re
            
            # Funzione per sostituire blocchi di codice con HTML corretto
            def replace_code_block(match):
                language = match.group(1).strip() if match.group(1) else ""
                code = match.group(2)
                # Preserva tutti gli spazi e formattazione originale
                code_html = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                # Mantieni la struttura esatta dell'indentazione
                return f'<pre><code class="language-{language}">{code_html}</code></pre>'
            
            # Funzione per sostituire codice inline
            def replace_inline_code(match):
                code = match.group(1)
                code_html = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                return f'<code>{code_html}</code>'
            
            # Prima sostituisci i blocchi di codice con triple backtick
            # Usiamo un pattern migliorato che cattura correttamente tutto il contenuto
            processed = re.sub(r'```([^\n]*)\n([\s\S]*?)\n```', replace_code_block, text)
            
            # Poi sostituisci il codice inline con singolo backtick
            processed = re.sub(r'`([^`\n]+?)`', replace_inline_code, processed)
            
            return processed
        
        # Elaborazione completamente personalizzata del markdown
        def custom_markdown(text):
            import re
            
            # Prima processa i blocchi di codice per preservare la loro formattazione
            text = process_code_blocks(text)
            
            # Titoli
            text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
            text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
            text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
            text = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
            
            # Liste puntate - pattern migliorato per catturare l'indentazione
            text = re.sub(r'^(\s*)-\s+(.+)$', r'\1<li>\2</li>', text, flags=re.MULTILINE)
            # Raggruppa elementi di lista in tag <ul>
            pattern_ul = r'(<li>.*?</li>)(\n<li>.*?</li>)*'
            text = re.sub(pattern_ul, r'<ul>\g<0></ul>', text)
            
            # Liste numerate
            text = re.sub(r'^(\s*)\d+\.\s+(.+)$', r'\1<li>\2</li>', text, flags=re.MULTILINE)
            # Raggruppa elementi di lista numerata in tag <ol>
            pattern_ol = r'(<li>.*?</li>)(\n<li>.*?</li>)*'
            text = re.sub(pattern_ol, r'<ol>\g<0></ol>', text)
            
            # Enfasi - grassetto e corsivo
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
            text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
            text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
            
            # Paragrafi: converti le linee di testo in paragrafi
            # Evita di avvolgere in <p> il contenuto già in tag HTML
            lines = text.split('\n')
            in_html_block = False
            for i, line in enumerate(lines):
                # Salta linee vuote e linee che iniziano con HTML
                if not line.strip() or line.strip().startswith('<'):
                    continue
                # Controlla se stiamo entrando/uscendo da un blocco HTML
                if '<pre>' in line or '<ul>' in line or '<ol>' in line or '<h' in line:
                    in_html_block = True
                elif '</pre>' in line or '</ul>' in line or '</ol>' in line or '</h' in line:
                    in_html_block = False
                    continue
                # Se non siamo in un blocco HTML, avvolgi la linea in <p>
                if not in_html_block:
                    lines[i] = f'<p>{line}</p>'
            text = '\n'.join(lines)
            
            # Rimuovi paragrafi vuoti
            text = re.sub(r'<p>\s*</p>', '', text)
            
            # Link
            text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
            
            return text
        
        # Elabora il testo completamente con il nostro parser personalizzato
        html_content = custom_markdown(text)
        
        # Assembla il messaggio HTML completo
        formatted_html = f"{html_style}{header}{html_content}"
        
        # Configura il QTextEdit per interpretare HTML
        self.response_text.setAcceptRichText(True)
        
        # Imposta o appende il testo formattato
        current_html = self.response_text.toHtml()
        if not self.response_text.toPlainText():
            self.response_text.setHtml(formatted_html)
        else:
            # Appendi il nuovo contenuto mantenendo la formattazione precedente
            closing_index = current_html.rfind("</body>")
            if closing_index > 0:
                new_html = current_html[:closing_index] + f"{header}{html_content}" + current_html[closing_index:]
                self.response_text.setHtml(new_html)
            else:
                # Fallback se non troviamo i tag di chiusura
                self.response_text.setHtml(current_html + formatted_html)
        
        # Scorri alla fine
        self.response_text.verticalScrollBar().setValue(
            self.response_text.verticalScrollBar().maximum()
        )
        
        if (not self.chat_history or self.chat_history[-1]["role"] != "assistant"):
            self.chat_history.append({"role": "assistant", "content": text})
        elif self.chat_history and self.chat_history[-1]["role"] == "assistant":
            previous_content = self.chat_history[-1]["content"]
            self.chat_history[-1]["content"] = f"{previous_content}\n--- Risposta alle {current_time} ---\n{text}"
    
    def take_screenshot(self):
        """Cattura e salva uno screenshot."""
        try:
            self.showMinimized()
            time.sleep(0.5)
            screenshot_path = self.screenshot_manager.take_screenshot()
            self.showNormal()
            QMessageBox.information(self, "Screenshot", 
                                  f"Screenshot salvato in: {screenshot_path}")
        except Exception as e:
            error_msg = f"Errore durante la cattura dello screenshot: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def share_screenshot(self):
        """Cattura uno screenshot e offre opzioni per condividerlo."""
        try:
            self.showMinimized()
            time.sleep(0.5)
            screenshot_path = self.screenshot_manager.take_screenshot()
            self.showNormal()
            self.screenshot_manager.copy_to_clipboard(screenshot_path)
            QMessageBox.information(self, "Screenshot Condiviso", 
                                  f"Screenshot salvato in: {screenshot_path}\n\n" +
                                  "Il percorso è stato copiato negli appunti.")
        except Exception as e:
            error_msg = f"Errore durante la condivisione dello screenshot: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def clear_text(self):
        """Pulisce i campi di testo."""
        self.transcription_text.clear()
        self.response_text.clear()
        self.chat_history = []
    
    def save_conversation(self):
        """Salva la conversazione in un file JSON."""
        try:
            options = QFileDialog.Options()
            filename, _ = QFileDialog.getSaveFileName(
                self, "Salva Conversazione", "", 
                "JSON Files (*.json);;Text Files (*.txt);;All Files (*)", 
                options=options)
                
            if filename:
                if not filename.endswith('.json'):
                    filename += '.json'
                    
                conversation_data = {
                    "timestamp": datetime.now().isoformat(),
                    "messages": self.chat_history
                }
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(conversation_data, f, ensure_ascii=False, indent=4)
                    
                QMessageBox.information(self, "Salvataggio Completato", 
                                      f"Conversazione salvata in: {filename}")
        
        except Exception as e:
            error_msg = f"Errore durante il salvataggio: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def show_error(self, message):
        """Mostra un messaggio di errore."""
        if "buffer too small" in message or "Conversation already has an active response" in message:
            # Se il messaggio contiene uno degli errori specifici, logga solo senza mostrare il popup
            logger.warning(f"Errore ignorato (solo log): {message}")
        else:
            # Per tutti gli altri errori, mostra il popup come prima
            QMessageBox.critical(self, "Errore", message)
        
    def closeEvent(self, event):
        """Gestisce la chiusura dell'applicazione."""
        if self.recording and self.text_thread:
            self.transcription_text.append("\n[Chiusura dell'applicazione in corso...]")
            try:
                self.text_thread.stop()
                self.text_thread.wait(2000)
            except Exception as e:
                logger.error("Errore durante la chiusura dell'applicazione: " + str(e))
        event.accept()

    def toggle_speaking(self):
        """Attiva o disattiva la registrazione vocale."""
        if not self.recording or not self.text_thread or not self.text_thread.connected:
            self.show_error("Non sei connesso. Inizia prima una sessione.")
            return
        if not hasattr(self.text_thread, 'recording') or not self.text_thread.recording:
            self.text_thread.start_recording()
        else:
            self.text_thread.stop_recording()

    def stop_recording(self):
        """Metodo preservato per compatibilità (la gestione della stop avviene in toggle_recording)."""
        logger.info("IntervistaAssistant: Fermando la registrazione")
        pass


def main():
    """Funzione principale per avviare l'applicazione."""
    app = QApplication(sys.argv)
    window = IntervistaAssistant()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 