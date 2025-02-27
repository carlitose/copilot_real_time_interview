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
    """Thread per comunicazione testuale usando OpenAI Realtime API."""
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
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        self.p = None
        self.stream = None
        
        # Configurazione per il rilevamento delle pause
        self.last_audio_commit_time = 0
        self.silence_threshold = 500  # Valore RMS per definire il silenzio
        self.pause_duration = 0.7  # Secondi di pausa che attivano un commit (ridotto per maggiore reattività)
        self.min_commit_interval = 1.5  # Intervallo minimo in secondi tra commit consecutivi (ridotto)
        self.is_speaking = False
        self.silence_start_time = 0
        self.last_commit_time = 0
        self.response_pending = False
        self.buffer_size_to_send = 40  # Aumentato: invio meno frequente (circa 2.5 secondi di audio)
        
    async def realtime_session(self):
        """Gestisce una sessione per la comunicazione testuale usando la Realtime API."""
        try:
            # Notifica all'utente che stiamo iniziando la connessione
            self.transcription_signal.emit("Connessione alla Realtime API in corso...")
            
            # Usa websocket-client
            import websocket
            import json
            import uuid
            import threading
            
            # URL e header per la connessione
            url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
            headers = [
                "Authorization: Bearer " + os.getenv('OPENAI_API_KEY'),
                "OpenAI-Beta: realtime=v1",
                "Content-Type: application/json"
            ]
            
            # Imposta il flag di connessione
            self.connected = False
            self.websocket = None
            self.websocket_thread = None
            
            # Funzioni di callback per websocket-client
            def on_open(ws):
                logger.info("Connessione WebSocket stabilita")
                self.connected = True
                self.connection_status_signal.emit(True)
                self.last_event_time = time.time()
                self.current_text = ""
                
                # Configura la sessione per input audio e output solo testuale
                session_config = {
                    "type": "session.update",
                    "session": {
                        "modalities": ["audio", "text"],
                        "turn_detection": None,
                        "input_audio_format": "pcm16",  # Per l'input audio
                        "output_audio_format": "pcm16"  # Formato audio richiesto anche se usiamo solo testo
                    }
                }
                ws.send(json.dumps(session_config))
                logger.info("Configurazione sessione inviata (input audio, output solo testo)")
                
                # Invia il messaggio di sistema
                system_instructions = """Sei un assistente AI per interviste di lavoro, specializzato in domande per software engineer.
                    Rispondi in modo conciso e strutturato con elenchi puntati dove appropriato.
                    Focalizzati sugli aspetti tecnici, i principi di design, le best practice e gli algoritmi.
                    Non essere prolisso. Fornisci esempi pratici dove utile.
                    Le tue risposte saranno mostrate a schermo durante un'intervista, quindi sii chiaro e diretto..
                    """
                
                system_message = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_instructions}]
                    }
                }
                ws.send(json.dumps(system_message))
                logger.info("Messaggio di sistema inviato")
                
                # Notifica all'utente che la connessione è stabilita
                self.transcription_signal.emit("Connesso! Pronto per l'intervista. Parla per fare domande.")
            
            def on_message(ws, message):
                self.last_event_time = time.time()
                
                try:
                    event = json.loads(message)
                    event_type = event.get('type', 'sconosciuto')
                    
                    logger.info(f"Evento ricevuto: {event_type}")
                    logger.info(f"Dettagli evento: {str(event)[:500]}...")
                    
                    if event_type == 'response.audio.delta':
                        # Ignoriamo completamente i chunk audio in quanto abbiamo disabilitato l'output audio
                        # Questo evento non dovrebbe essere ricevuto con la configurazione corrente
                        logger.info("Evento audio ricevuto ma ignorato (output audio disabilitato)")
                        
                    elif event_type == 'response.text.delta':
                        delta = event.get('delta', '')
                        if not hasattr(self, 'current_text'):
                            self.current_text = ""
                        self.current_text += delta
                        
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        self.response_signal.emit(f"[Generazione in corso {timestamp}] {self.current_text}")
                        
                    elif event_type == 'response.text.done':
                        if hasattr(self, 'current_text') and self.current_text.strip():
                            self.response_signal.emit(self.current_text)
                            self.current_text = ""
                            
                    elif event_type == 'response.done':
                        # Risposta completata, reset della flag
                        self.response_pending = False
                        
                        # Controlla se la risposta ha avuto successo
                        status = event.get('response', {}).get('status', '')
                        if status == 'failed':
                            status_details = event.get('response', {}).get('status_details', {})
                            error_info = status_details.get('error', {})
                            error_message = error_info.get('message', 'Errore sconosciuto durante la generazione della risposta')
                            logger.error(f"Errore nella risposta: {error_message}")
                            self.error_signal.emit(f"Errore API: {error_message}")
                            
                    elif event_type == 'error':
                        self.response_pending = False
                        error = event.get('error', {})
                        error_msg = error.get('message', 'Errore sconosciuto')
                        self.error_signal.emit(f"Errore API: {error_msg}")
                    
                except Exception as e:
                    logger.error(f"Errore durante l'elaborazione del messaggio WebSocket: {str(e)}")
            
            def on_error(ws, error):
                logger.error(f"Errore WebSocket: {str(error)}")
                self.error_signal.emit(f"Errore di connessione: {str(error)}")
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
            
            # Crea WebSocketApp con le callback
            self.websocket = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Resetta il contatore dei tentativi di riconnessione
            self.reconnect_attempts = 0
            
            # Avvia il WebSocket in un thread separato
            def run_websocket():
                self.websocket.run_forever()
            
            self.websocket_thread = threading.Thread(target=run_websocket)
            self.websocket_thread.daemon = True
            self.websocket_thread.start()
            
            # Loop principale
            try:
                while self.running:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("Loop principale cancellato")
            finally:
                if self.websocket and self.connected:
                    self.websocket.close()
                
                logger.info("Sessione WebSocket terminata")
                
        except Exception as e:
            error_msg = f"Errore critico: {str(e)}"
            self.error_signal.emit(error_msg)
            logger.error(error_msg)
        finally:
            self.connected = False
            self.connection_status_signal.emit(False)
    
    def run(self):
        """Avvia il loop asincrono per la sessione."""
        self.running = True
        asyncio.run(self.realtime_session())
        logger.info("Thread di comunicazione terminato")
            
    def stop(self):
        """Ferma la comunicazione."""
        logger.info("Richiesta di stop comunicazione ricevuta")
        self.running = False
        
        # Se la registrazione è attiva, fermala
        if self.recording:
            self.stop_recording()
        
        # Chiudi esplicitamente il WebSocket se esiste e ancora connesso
        if hasattr(self, 'websocket') and self.websocket and self.connected:
            try:
                logger.info("Chiusura WebSocket in corso...")
                self.websocket.close()
                logger.info("WebSocket chiuso")
            except Exception as e:
                logger.error(f"Errore durante la chiusura del WebSocket: {str(e)}")
        
        self.transcription_signal.emit(self.transcription_buffer + "\n[Terminazione sessione in corso...]")

    def start_recording(self):
        """Inizia la registrazione audio dal microfono."""
        if self.recording:
            return
        
        self.recording = True
        self.audio_buffer = []
        
        # Inizializza PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=self.FORMAT,
                                 channels=self.CHANNELS,
                                 rate=self.RATE,
                                 input=True,
                                 frames_per_buffer=self.CHUNK)
        
        # Avvia un thread per la registrazione
        threading.Thread(target=self._record_audio, daemon=True).start()
        logger.info("Registrazione audio avviata")
        self.transcription_signal.emit("Registrazione in corso... Parla adesso.")

    def stop_recording(self):
        """Ferma la registrazione audio."""
        if not self.recording:
            return
        
        self.recording = False
        
        # Chiudi stream e PyAudio
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        
        # Invia l'audio registrato
        if self.audio_buffer and self.connected:
            self._send_audio_buffer()
        
        # Verifica che il websocket sia ancora disponibile
        if not hasattr(self, 'websocket') or not self.websocket or not self.connected:
            logger.warning("WebSocket non disponibile per inviare commit o richieste")
            return
        
        # Comunica che l'input audio è terminato
        try:
            commit_message = {
                "type": "input_audio_buffer.commit"
            }
            self.websocket.send(json.dumps(commit_message))
            logger.info("Audio input terminato (commit finale)")
            
            # Richiedi una risposta solo se non c'è già una richiesta pendente
            if not self.response_pending:
                response_request = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["text"]  # Solo testo come output
                    }
                }
                self.websocket.send(json.dumps(response_request))
                logger.info("Richiesta risposta finale inviata")
            else:
                logger.info("Risposta già in corso, non inviata nuova richiesta")
        except Exception as e:
            logger.error(f"Errore durante l'invio dei messaggi di terminazione: {str(e)}")
        
        # Reset della flag di risposta pendente
        self.response_pending = False
        logger.info("Registrazione audio fermata")

    def _record_audio(self):
        """Registra audio in loop fino a quando non viene fermato."""
        try:
            self.last_commit_time = time.time()
            while self.recording and self.stream:
                data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                self.audio_buffer.append(data)
                
                # Calcola il valore RMS per rilevare se c'è silenzio
                rms = self._calculate_rms(data)
                current_time = time.time()
                
                # Rileva inizio e fine del parlato
                if rms > self.silence_threshold:
                    # L'utente sta parlando
                    if not self.is_speaking:
                        logger.info(f"Inizio parlato rilevato (RMS: {rms})")
                        self.is_speaking = True
                    self.silence_start_time = 0  # Reset del timer del silenzio
                else:
                    # Silenzio rilevato
                    if self.is_speaking:
                        # Se prima stava parlando, inizia a contare il silenzio
                        if self.silence_start_time == 0:
                            self.silence_start_time = current_time
                        elif (current_time - self.silence_start_time >= self.pause_duration and 
                              current_time - self.last_commit_time >= self.min_commit_interval):
                            # Pausa significativa rilevata, invia commit
                            logger.info(f"Pausa rilevata ({current_time - self.silence_start_time:.2f}s) - Invio audio per elaborazione")
                            self._send_audio_commit()
                            self.audio_buffer = []
                            self.is_speaking = False
                            self.silence_start_time = 0
                            self.last_commit_time = current_time
                
                # Invia l'audio accumulato in blocchi più grandi (circa 2.5 secondi invece di 0.6)
                if len(self.audio_buffer) >= self.buffer_size_to_send and self.connected:
                    self._send_audio_buffer()
                    logger.info(f"Invio buffer audio di {self.buffer_size_to_send} chunk")
                    
                # Anche se non c'è stata una pausa, invia un commit periodico se è passato abbastanza tempo
                if (current_time - self.last_commit_time >= 7.0 and  # Aumentato a 7 secondi massimo senza commit
                    len(self.audio_buffer) > 20 and  # Solo se c'è abbastanza audio
                    not self.response_pending and
                    self.connected):
                    logger.info("Inviando commit periodico dopo 7 secondi di parlato continuo")
                    self._send_audio_commit()
                    self.audio_buffer = []
                    self.last_commit_time = current_time
                
        except Exception as e:
            logger.error(f"Errore durante la registrazione: {str(e)}")
            self.error_signal.emit(f"Errore registrazione: {str(e)}")
            self.recording = False

    def _calculate_rms(self, data):
        """Calcola il valore RMS (Root Mean Square) di un buffer audio."""
        try:
            # Converti i byte in short integers
            shorts = np.frombuffer(data, dtype=np.int16)
            # Calcola RMS
            rms = np.sqrt(np.mean(np.square(shorts)))
            return rms
        except Exception as e:
            logger.error(f"Errore nel calcolo RMS: {str(e)}")
            return 0

    def _send_audio_commit(self):
        """Invia un commit per l'audio raccolto finora e richiede una risposta."""
        if not self.connected or self.response_pending:
            return
            
        try:
            # Invia il buffer audio rimanente
            if self.audio_buffer:
                self._send_audio_buffer()
                self.audio_buffer = []
                
            # Invia il comando di commit
            commit_message = {
                "type": "input_audio_buffer.commit"
            }
            self.websocket.send(json.dumps(commit_message))
            logger.info("Audio input parziale terminato (commit)")
            
            # Richiedi una risposta
            response_request = {
                "type": "response.create",
                "response": {
                    "modalities": ["text"]  # Solo testo come output
                }
            }
            self.websocket.send(json.dumps(response_request))
            logger.info("Richiesta risposta inviata durante la registrazione")
            self.response_pending = True
            
        except Exception as e:
            logger.error(f"Errore durante l'invio del commit: {str(e)}")

    def _send_audio_buffer(self):
        """Converte e invia i dati audio al WebSocket."""
        if not self.audio_buffer or not self.connected:
            return
        
        try:
            # Combina tutti i chunk in un unico buffer
            audio_data = b''.join(self.audio_buffer)
            
            # Converti in base64
            base64_audio = base64.b64encode(audio_data).decode('ascii')
            
            # Invia al WebSocket
            audio_message = {
                "type": "input_audio_buffer.append",
                "audio": base64_audio
            }
            self.websocket.send(json.dumps(audio_message))
            logger.info(f"Inviati {len(base64_audio)} bytes di audio")
            
        except Exception as e:
            logger.error(f"Errore nell'invio dell'audio: {str(e)}")


class IntervistaAssistant(QMainWindow):
    """Applicazione principale per l'assistente di interviste."""
    
    def __init__(self):
        super().__init__()
        
        # OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            QMessageBox.critical(self, "Errore API Key", 
                                "API Key OpenAI non trovata. Imposta la variabile d'ambiente OPENAI_API_KEY.")
            sys.exit(1)
            
        self.client = OpenAI(api_key=api_key)
        
        # Stato dell'applicazione
        self.recording = False
        self.text_thread = None  # Rinominato da audio_thread a text_thread
        self.chat_history = []
        self.shutdown_in_progress = False
        
        # Inizializza utility
        self.screenshot_manager = ScreenshotManager()
        
        # Configura l'interfaccia
        self.init_ui()
        
    def init_ui(self):
        """Inizializza l'interfaccia utente."""
        self.setWindowTitle("Assistente Intervista Software Engineer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Layout principale
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Splitter per dividere area input e risposta
        splitter = QSplitter(Qt.Vertical)
        
        # Area di input utente (audio)
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        
        input_label = QLabel("Input dell'utente (audio):")  
        input_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.transcription_text = QTextEdit()
        self.transcription_text.setReadOnly(True)
        self.transcription_text.setFont(QFont("Arial", 11))
        self.transcription_text.setMinimumHeight(150)
        
        # Pulsante per parlare
        self.speak_button = QPushButton("Parla")
        self.speak_button.setFont(QFont("Arial", 11))
        self.speak_button.clicked.connect(self.toggle_speaking)
        self.speak_button.setEnabled(False)  # Disabilitato finché la sessione non è attiva
        
        input_layout.addWidget(input_label)
        input_layout.addWidget(self.transcription_text)
        input_layout.addWidget(self.speak_button)
        
        # Area di risposta
        response_container = QWidget()
        response_layout = QVBoxLayout(response_container)
        
        response_label = QLabel("Risposta:")
        response_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setFont(QFont("Arial", 11))
        
        response_layout.addWidget(response_label)
        response_layout.addWidget(self.response_text)
        
        # Aggiungi widget al splitter
        splitter.addWidget(input_container)
        splitter.addWidget(response_container)
        splitter.setSizes([300, 500])
        
        # Controlli
        controls_layout = QHBoxLayout()
        
        self.record_button = QPushButton("Inizia Sessione")  # Cambiato da "Inizia Registrazione"
        self.record_button.setFont(QFont("Arial", 11))
        self.record_button.clicked.connect(self.toggle_recording)
        
        self.clear_button = QPushButton("Pulisci")
        self.clear_button.setFont(QFont("Arial", 11))
        self.clear_button.clicked.connect(self.clear_text)
        
        self.screenshot_button = QPushButton("Screenshot")
        self.screenshot_button.setFont(QFont("Arial", 11))
        self.screenshot_button.clicked.connect(self.take_screenshot)
        
        self.share_button = QPushButton("Condividi Screenshot")
        self.share_button.setFont(QFont("Arial", 11))
        self.share_button.clicked.connect(self.share_screenshot)
        
        self.save_button = QPushButton("Salva Conversazione")
        self.save_button.setFont(QFont("Arial", 11))
        self.save_button.clicked.connect(self.save_conversation)
        
        controls_layout.addWidget(self.record_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.screenshot_button)
        controls_layout.addWidget(self.share_button)
        controls_layout.addWidget(self.save_button)
        
        # Assembla il layout principale
        main_layout.addWidget(splitter)
        main_layout.addLayout(controls_layout)
        
        self.setCentralWidget(central_widget)
        
    def toggle_recording(self):
        """Attiva o disattiva la connessione al modello."""
        if not self.recording:
            # Avvia la connessione
            self.recording = True
            self.record_button.setText("Termina Sessione")
            self.record_button.setStyleSheet("background-color: #ff5555;")
            
            # Avvia thread di comunicazione con Realtime API
            self.text_thread = RealtimeTextThread()
            self.text_thread.transcription_signal.connect(self.update_transcription)
            self.text_thread.response_signal.connect(self.update_response)
            self.text_thread.error_signal.connect(self.show_error)
            self.text_thread.connection_status_signal.connect(self.update_connection_status)
            self.text_thread.finished.connect(self.recording_finished)
            self.text_thread.start()
            
            # Abilita il pulsante per parlare
            self.speak_button.setEnabled(True)
        else:
            # Previeni click multipli
            if self.shutdown_in_progress:
                return
                
            self.shutdown_in_progress = True
            
            # Cambia il pulsante per mostrare che la chiusura è in corso
            self.record_button.setText("Terminazione in corso...")
            self.record_button.setEnabled(False)
            
            # Ferma la registrazione audio se attiva
            if hasattr(self.text_thread, 'recording') and self.text_thread.recording:
                try:
                    self.text_thread.stop_recording()
                except Exception as e:
                    logger.error(f"Errore durante l'arresto della registrazione: {str(e)}")
                
                self.speak_button.setText("Parla")
                self.speak_button.setStyleSheet("")
                
                # Disabilita il pulsante per parlare
                self.speak_button.setEnabled(False)
            
            # Ferma la connessione in modo controllato
            try:
                if self.text_thread:
                    self.text_thread.stop()
                    # Attendi max 2 secondi per la terminazione pulita
                    self.text_thread.wait(2000)
            except Exception as e:
                logger.error(f"Errore durante la terminazione della sessione: {str(e)}")
                # Anche in caso di errore, aggiorna l'UI
                self.recording_finished()
    
    def recording_finished(self):
        """Chiamato quando il thread è terminato."""
        self.recording = False
        self.shutdown_in_progress = False
        self.record_button.setText("Inizia Sessione")  # Cambiato da "Inizia Registrazione"
        self.record_button.setStyleSheet("")
        self.record_button.setEnabled(True)
        
        # Aggiungi un messaggio alla trascrizione
        self.transcription_text.append("\n[Sessione terminata]")  # Cambiato da "Registrazione terminata"
    
    def update_connection_status(self, connected):
        """Aggiorna l'interfaccia in base allo stato della connessione."""
        if connected:
            self.record_button.setStyleSheet("background-color: #55aa55;")  # Verde per connesso
        else:
            if self.recording:
                self.record_button.setStyleSheet("background-color: #ff5555;")  # Rosso per disconnesso
    
    def update_transcription(self, text):
        """Aggiorna il testo della trascrizione."""
        # Se è un nuovo messaggio di registrazione, resettiamo il campo
        if text == "Registrazione in corso...":
            self.transcription_text.setText(text)
            return
            
        # Se è un timestamp di audio processato
        if text.startswith('\n[Audio processato alle'):
            # Formattazione per il timestamp
            formatted_timestamp = f"\n--- {text.strip()} ---\n"
            
            # Ottieni il testo corrente e aggiungi il nuovo messaggio
            current_text = self.transcription_text.toPlainText()
            
            # Se stiamo iniziando con il primo messaggio dopo "Registrazione in corso..."
            if current_text == "Registrazione in corso...":
                self.transcription_text.setText(formatted_timestamp)
            else:
                self.transcription_text.append(formatted_timestamp)
        else:
            # Per altri messaggi, come gli errori o trascrizioni, li appendiamo
            self.transcription_text.append(text)
        
        # Assicuriamo che lo scroll sia sempre in fondo per vedere i messaggi più recenti
        self.transcription_text.verticalScrollBar().setValue(
            self.transcription_text.verticalScrollBar().maximum()
        )
        
        # Aggiungi alla cronologia se è una nuova trascrizione
        if text != "Registrazione in corso...":
            # Verifica se è già presente nella cronologia
            if not self.chat_history or self.chat_history[-1]["role"] != "user" or self.chat_history[-1]["content"] != text:
                self.chat_history.append({"role": "user", "content": text})
    
    def update_response(self, text):
        """Aggiorna il testo della risposta."""
        if not text:
            return
            
        # Formattazione: aggiungiamo un timestamp e separatore per ogni nuova risposta
        current_time = datetime.now().strftime("%H:%M:%S")
        formatted_response = f"\n--- Risposta alle {current_time} ---\n{text}\n"
        
        # Ottieni il testo corrente
        current_text = self.response_text.toPlainText()
        
        # Se il campo è vuoto, impostiamo il testo, altrimenti appendiamo
        if not current_text:
            self.response_text.setText(formatted_response)
        else:
            # Aggiungiamo un separatore e la nuova risposta
            self.response_text.append(formatted_response)
            
        # Assicuriamo che lo scroll sia sempre in fondo per vedere la risposta più recente
        self.response_text.verticalScrollBar().setValue(
            self.response_text.verticalScrollBar().maximum()
        )
        
        # Aggiorna la cronologia
        if (not self.chat_history or self.chat_history[-1]["role"] != "assistant"):
            self.chat_history.append({"role": "assistant", "content": text})
        elif self.chat_history and self.chat_history[-1]["role"] == "assistant":
            # Invece di sovrascrivere, appendiamo alla risposta precedente con un separatore
            previous_content = self.chat_history[-1]["content"]
            self.chat_history[-1]["content"] = f"{previous_content}\n--- Risposta alle {current_time} ---\n{text}"
    
    def take_screenshot(self):
        """Cattura e salva uno screenshot."""
        try:
            # Minimizza brevemente l'applicazione
            self.showMinimized()
            time.sleep(0.5)  # Breve pausa per assicurarsi che l'app sia minimizzata
            
            # Cattura screenshot
            screenshot_path = self.screenshot_manager.take_screenshot()
            
            # Ripristina l'applicazione
            self.showNormal()
            
            # Notifica all'utente
            QMessageBox.information(self, "Screenshot", 
                                  f"Screenshot salvato in: {screenshot_path}")
            
        except Exception as e:
            error_msg = f"Errore durante la cattura dello screenshot: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def share_screenshot(self):
        """Cattura uno screenshot e mostra opzioni per condividerlo."""
        try:
            # Minimizza brevemente l'applicazione
            self.showMinimized()
            time.sleep(0.5)  # Breve pausa per assicurarsi che l'app sia minimizzata
            
            # Cattura screenshot
            screenshot_path = self.screenshot_manager.take_screenshot()
            
            # Ripristina l'applicazione
            self.showNormal()
            
            # Copia percorso negli appunti
            self.screenshot_manager.copy_to_clipboard(screenshot_path)
            
            # Notifica all'utente
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
        # Reset anche della storia della chat quando si pulisce l'interfaccia
        self.chat_history = []
    
    def save_conversation(self):
        """Salva la conversazione in un file JSON."""
        try:
            # Apri finestra di dialogo per salvare
            options = QFileDialog.Options()
            filename, _ = QFileDialog.getSaveFileName(
                self, "Salva Conversazione", "", 
                "JSON Files (*.json);;Text Files (*.txt);;All Files (*)", 
                options=options)
                
            if filename:
                # Assicurati che abbia l'estensione .json
                if not filename.endswith('.json'):
                    filename += '.json'
                    
                # Prepara i dati della conversazione
                conversation_data = {
                    "timestamp": datetime.now().isoformat(),
                    "messages": self.chat_history
                }
                
                # Salva nel file
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
        QMessageBox.critical(self, "Errore", message)
        
    def closeEvent(self, event):
        """Gestisce l'evento di chiusura dell'applicazione."""
        if self.recording and self.text_thread:
            # Mostra un messaggio che stiamo terminando
            self.transcription_text.append("\n[Chiusura dell'applicazione in corso...]")
            
            try:
                # Ferma la comunicazione
                self.text_thread.stop()
                # Aspetta max 2 secondi
                self.text_thread.wait(2000)
            except Exception as e:
                logger.error(f"Errore durante la chiusura dell'applicazione: {str(e)}")
        
        event.accept()

    def toggle_speaking(self):
        """Attiva o disattiva la registrazione della voce."""
        if not self.recording or not self.text_thread or not self.text_thread.connected:
            self.show_error("Non sei connesso. Inizia prima una sessione.")
            return
        
        if not hasattr(self.text_thread, 'recording') or not self.text_thread.recording:
            # Inizia a registrare
            self.speak_button.setText("Stop")
            self.speak_button.setStyleSheet("background-color: #ff5555;")
            self.text_thread.start_recording()
        else:
            # Ferma la registrazione
            self.speak_button.setText("Parla")
            self.speak_button.setStyleSheet("")
            self.text_thread.stop_recording()

    def stop_recording(self):
        """Ferma la registrazione e chiude la connessione al server."""
        logger.info("IntervistaAssistant: Fermando la registrazione")
        # Non fa nulla, metodo mantenuto per compatibilità con vecchio codice
        # La chiusura viene gestita direttamente in toggle_recording
        pass


def main():
    """Funzione principale per avviare l'applicazione."""
    app = QApplication(sys.argv)
    window = IntervistaAssistant()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 