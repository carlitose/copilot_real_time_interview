#!/usr/bin/env python3
import sys
import os
import pyperclip
import tempfile
import time
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
import base64

import pyautogui
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                            QHBoxLayout, QWidget, QTextEdit, QLabel, QSplitter,
                            QMessageBox, QFileDialog, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QPixmap, QIcon

from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

from .utils import ScreenshotManager

# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

# Carica variabili d'ambiente
load_dotenv()

class RealtimeAudioThread(QThread):
    """Thread per catturare audio e trascriverlo usando OpenAI Realtime API."""
    transcription_signal = pyqtSignal(str)
    response_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    connection_status_signal = pyqtSignal(bool)  # Nuovo segnale per lo stato della connessione
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.connected = False  # Flag per tracciare lo stato della connessione
        self.temp_dir = Path(tempfile.gettempdir()) / "intervista_assistant"
        self.temp_dir.mkdir(exist_ok=True)
        self.transcription_buffer = ""
        self.connection_timeout = 15  # Timeout di connessione in secondi
        self.last_event_time = None  # Per tracciare quando è stato ricevuto l'ultimo evento
        self.reconnect_attempts = 0  # Contatore tentativi di riconnessione
        self.max_reconnect_attempts = 3  # Numero massimo di tentativi di riconnessione
        
    async def realtime_session(self):
        """Gestisce una sessione per la registrazione e trascrizione audio usando la Realtime API."""
        # Inizializza PyAudio all'inizio per evitare di ricrearlo in caso di riconnessione
        import pyaudio
        import wave
        
        # Configurazione per la registrazione
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000  # 16kHz come raccomandato nella documentazione
        RECORD_SECONDS = 0.5  # Piccoli chunk per lo streaming continuo
        
        # Crea oggetto PyAudio
        p = pyaudio.PyAudio()
        
        # Apri stream
        stream = None
        
        try:
            stream = p.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
            
            # Notifica all'utente che stiamo iniziando la registrazione
            self.transcription_signal.emit("Connessione alla Realtime API in corso...")
            
            # Loop per riconnessione
            while self.running and self.reconnect_attempts <= self.max_reconnect_attempts:
                try:
                    # Inizializza il client OpenAI
                    client = AsyncOpenAI()
                    events_task = None
                    monitor_task = None
                    
                    try:
                        # Ora connect() restituisce direttamente l'oggetto ConnectionManager
                        logger.info("Tentativo di connessione alla Realtime API...")
                        connection = client.beta.realtime.connect(model="gpt-4o-realtime-preview")
                        
                        if not connection or not hasattr(connection, "session"):
                            raise Exception("Connessione non valida - oggetto session non disponibile")
                        
                        logger.info("Connessione iniziale stabilita, configurazione in corso...")
                        self.connected = True
                        self.connection_status_signal.emit(True)
                        logger.info("Connessione stabilita con la Realtime API")
                        
                        # Resetta il contatore dei tentativi di riconnessione
                        self.reconnect_attempts = 0
                        
                        # Configurazione specifica della sessione - semplificata secondo documentazione
                        await connection.session.update(session={
                            'modalities': ['text'],  # Solo modalità testo
                            'turn_detection': {  # Mantenuto per il rilevamento del parlato
                                'type': 'server_vad',
                                'threshold': 0.5,
                                'silence_duration_ms': 300
                            }
                        })
                        logger.info("Sessione configurata in modalità solo testo")
                        
                        # Impostiamo un timeout per la connessione
                        connection_established = False
                        start_time = time.time()
                        
                        # Verifichiamo che la connessione sia attiva
                        while not connection_established and (time.time() - start_time) < self.connection_timeout:
                            if hasattr(connection, "session") and connection.session:
                                connection_established = True
                                break
                            await asyncio.sleep(0.5)
                        
                        if not connection_established:
                            raise asyncio.TimeoutError("Timeout durante la connessione alla Realtime API")
                        
                        # Imposta un messaggio di sistema per specificare il comportamento dell'assistente
                        system_instructions = """Sei un assistente AI per interviste di lavoro, specializzato in domande per software engineer.
                            Rispondi in modo conciso e strutturato con elenchi puntati dove appropriato.
                            Focalizzati sugli aspetti tecnici, i principi di design, le best practice e gli algoritmi.
                            Non essere prolisso. Fornisci esempi pratici dove utile.
                            Le tue risposte saranno mostrate a schermo durante un'intervista, quindi sii chiaro e diretto.
                            Stai ascoltando un'intervista tecnica. Quando rilevi una domanda tecnica, rispondi con informazioni utili.
                            """
                        
                        await connection.conversation.item.create(
                            item={
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": system_instructions}],
                            }
                        )
                        logger.info("Messaggio di sistema inviato")
                        
                        # Notifica all'utente che la connessione è stabilita
                        self.transcription_signal.emit("Connesso! Registrazione in corso...\nIn attesa del tuo parlato per iniziare.")
                        
                        # Crea un task per gestire gli eventi in arrivo
                        events_task = asyncio.create_task(self.process_events(connection))
                        logger.info("Task di gestione eventi avviato")
                        
                        # Impostare il timestamp iniziale dell'ultimo evento
                        self.last_event_time = time.time()
                        
                        # Task per monitorare se riceviamo eventi dal server
                        monitor_task = asyncio.create_task(self.monitor_connection_activity())
                        
                        # Contatore per il debug
                        audio_chunks_sent = 0
                        
                        # Loop di registrazione e invio audio
                        while self.running and self.connected:
                            try:
                                # Registra audio per RECORD_SECONDS
                                frames = []
                                for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                                    if not self.running or not self.connected:
                                        break
                                    data = stream.read(CHUNK, exception_on_overflow=False)
                                    frames.append(data)
                                
                                if not frames or not self.running or not self.connected:
                                    continue
                                    
                                # Salva l'audio in un file temporaneo
                                temp_file = self.temp_dir / f"audio_{time.time()}.wav"
                                wf = wave.open(str(temp_file), 'wb')
                                wf.setnchannels(CHANNELS)
                                wf.setsampwidth(p.get_sample_size(FORMAT))
                                wf.setframerate(RATE)
                                wf.writeframes(b''.join(frames))
                                wf.close()
                                
                                # Leggi il file audio e invialo alla Realtime API
                                with open(temp_file, "rb") as f:
                                    audio_data = f.read()
                                    # Converti i dati audio in base64 prima di inviarli
                                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                                
                                # Crea un ID univoco per l'evento per il tracciamento degli errori
                                event_id = f"audio_{int(time.time()*1000)}"
                                
                                if not self.running or not self.connected:
                                    break
                                
                                # Prova a inviare l'audio
                                try:
                                    await connection.input_audio_buffer.append(
                                        audio=audio_base64,
                                        event_id=event_id
                                    )
                                    logger.info(f"Audio appeso al buffer con event_id: {event_id}")
                                except Exception as audio_error:
                                    # Se fallisce, prova con il metodo alternativo o gestisci l'errore
                                    logger.warning(f"Fallito append al buffer audio: {str(audio_error)}")
                                    if "Connection closed" in str(audio_error):
                                        # La connessione è stata chiusa
                                        logger.error("Connessione chiusa dal server")
                                        self.connected = False
                                        break
                                    
                                    try:
                                        # Metodo alternativo
                                        await connection.conversation.item.create(
                                            item={
                                                "type": "message",
                                                "role": "user",
                                                "content": [
                                                    {
                                                        "type": "input_audio",
                                                        "audio": audio_base64
                                                    }
                                                ],
                                            },
                                            event_id=event_id
                                        )
                                        logger.info(f"Audio inviato via item.create con event_id: {event_id}")
                                    except Exception as alt_error:
                                        logger.error(f"Fallito anche metodo alternativo: {str(alt_error)}")
                                        if "Connection closed" in str(alt_error):
                                            self.connected = False
                                            break
                                
                                # Incrementa contatore e log periodico
                                audio_chunks_sent += 1
                                if audio_chunks_sent % 10 == 0:
                                    logger.info(f"Stato: inviati {audio_chunks_sent} chunk audio finora, in attesa di risposta...")
                                
                                # Elimina il file temporaneo
                                if temp_file.exists():
                                    temp_file.unlink()
                                    
                            except Exception as e:
                                error_msg = f"Errore durante l'invio audio: {str(e)}"
                                logger.error(error_msg)
                                # Verifica se c'è un errore di connessione
                                if "Connection" in str(e) or "socket" in str(e).lower():
                                    self.connected = False
                                    break
                        
                        # Se siamo usciti dal loop ma l'app è ancora in esecuzione, 
                        # potrebbe essere necessario riconnettersi
                        if self.running and not self.connected:
                            await self.handle_reconnection()
                        
                    except Exception as session_err:
                        error_msg = f"Errore durante la sessione: {str(session_err)}"
                        logger.error(error_msg)
                        self.error_signal.emit(error_msg)
                        self.connected = False
                        await self.handle_reconnection()
                    finally:
                        # Cancella i task attivi
                        if events_task and not events_task.done():
                            events_task.cancel()
                            try:
                                await events_task
                            except asyncio.CancelledError:
                                pass
                        
                        if monitor_task and not monitor_task.done():
                            monitor_task.cancel()
                            try:
                                await monitor_task
                            except asyncio.CancelledError:
                                pass
                
                except Exception as e:
                    error_msg = f"Errore generale: {str(e)}"
                    logger.error(error_msg)
                    self.error_signal.emit(error_msg)
                    await self.handle_reconnection()
                
                # Se non stiamo più eseguendo, esci dal loop di riconnessione
                if not self.running:
                    break
                
                # Se abbiamo esaurito i tentativi di riconnessione
                if self.reconnect_attempts > self.max_reconnect_attempts and self.running:
                    self.error_signal.emit(f"Dopo {self.max_reconnect_attempts} tentativi, non è stato possibile stabilire una connessione stabile. Prova a riavviare l'applicazione.")
                    self.running = False
                
        except Exception as e:
            error_msg = f"Errore critico: {str(e)}"
            self.error_signal.emit(error_msg)
            logger.error(error_msg)
            self.running = False
        finally:
            # Chiudi e termina lo stream e PyAudio
            if stream:
                stream.stop_stream()
                stream.close()
            p.terminate()
            self.connected = False
            self.connection_status_signal.emit(False)
    
    async def handle_reconnection(self):
        """Gestisce la logica di riconnessione."""
        self.connected = False
        self.connection_status_signal.emit(False)
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts <= self.max_reconnect_attempts:
            wait_time = min(5 * self.reconnect_attempts, 15)  # Backoff esponenziale ma limitato a 15 secondi
            reconnect_msg = f"\n[Connessione persa. Tentativo di riconnessione {self.reconnect_attempts}/{self.max_reconnect_attempts} tra {wait_time} secondi...]"
            self.transcription_buffer += reconnect_msg
            self.transcription_signal.emit(self.transcription_buffer)
            logger.info(f"Tentativo di riconnessione {self.reconnect_attempts}/{self.max_reconnect_attempts} tra {wait_time} secondi")
            
            # Pausa prima di riconnettersi
            await asyncio.sleep(wait_time)
        else:
            logger.error(f"Esauriti i tentativi di riconnessione ({self.max_reconnect_attempts})")
            self.transcription_buffer += f"\n[Esauriti i tentativi di riconnessione. Per favore riavvia la registrazione.]"
            self.transcription_signal.emit(self.transcription_buffer)
    
    async def monitor_connection_activity(self):
        """Monitora la connessione e verifica se stiamo ricevendo eventi."""
        no_activity_timeout = 20  # Secondi senza attività prima di considerare la connessione persa
        check_interval = 5  # Controlla ogni 5 secondi
        
        while self.running:
            await asyncio.sleep(check_interval)
            
            if self.last_event_time is not None:
                time_since_last_event = time.time() - self.last_event_time
                
                if time_since_last_event > no_activity_timeout:
                    logger.warning(f"Nessun evento ricevuto negli ultimi {time_since_last_event:.1f} secondi")
                    self.transcription_buffer += f"\n[ATTENZIONE: Nessuna risposta dal server negli ultimi {int(time_since_last_event)} secondi]"
                    self.transcription_signal.emit(self.transcription_buffer)
                    
                    if time_since_last_event > no_activity_timeout * 2:
                        logger.error("Connessione probabilmente persa. Invio errore.")
                        self.error_signal.emit("Connessione persa con il server. Si consiglia di fermare e riavviare la registrazione.")
                        break  # Esci dal loop, ma lascia che il thread continui fino a quando l'utente non preme stop
    
    async def process_events(self, connection):
        """Processa gli eventi in arrivo dalla Realtime API."""
        try:
            current_text = ""
            events_received = 0  # Contatore per debug
            
            # Imposta il timestamp per la prima risposta
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.transcription_buffer += f"\n[Sessione avviata alle {timestamp}]"
            self.transcription_signal.emit(self.transcription_buffer)
            
            # Log che iniziamo ad ascoltare gli eventi
            logger.info("Iniziando ad ascoltare gli eventi dalla Realtime API...")
            
            # Il messaggio di test iniziale verrà inviato come conversazione
            first_message_event_id = f"text_test_{int(time.time()*1000)}"
            try:
                # 1. Prima creiamo l'elemento di conversazione (messaggio utente)
                await connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Ciao, puoi sentirmi? Questo è un test. Rispondi solo con testo per favore."}],
                    },
                    event_id=first_message_event_id
                )
                logger.info(f"Messaggio di test inviato con event_id: {first_message_event_id}")
                
                # 2. Poi richiediamo una risposta testuale
                await connection.response.create(
                    response={
                        "modalities": ["text"],  # Solo testo, come nella documentazione
                    }
                )
                logger.info("Richiesta risposta testuale inviata correttamente")
                
            except Exception as resp_err:
                logger.error(f"Errore durante la sequenza iniziale: {str(resp_err)}")
            
            # Aggiorna il timestamp dell'ultimo evento dopo aver inviato la richiesta
            self.last_event_time = time.time()
            
            async for event in connection:
                try:
                    # Aggiorna il timestamp dell'ultimo evento ricevuto
                    self.last_event_time = time.time()
                    
                    # Incrementa contatore e log
                    events_received += 1
                    event_type = getattr(event, 'type', 'sconosciuto')
                    
                    # Log più dettagliato dell'evento
                    logger.info(f"Evento #{events_received} ricevuto: {event_type}")
                    # DEBUG: Stampa il contenuto completo dell'evento per analisi
                    if hasattr(event, '__dict__'):
                        logger.info(f"Dettagli evento: {str(event.__dict__)}")
                    
                    # Gestione eventi di sessione
                    if event_type == 'session.created' or event_type == 'session.updated':
                        logger.info(f"Evento di sessione ricevuto: {event_type}")
                        session_info = getattr(event, 'session', None)
                        if session_info:
                            logger.info(f"ID sessione: {getattr(session_info, 'id', 'sconosciuto')}")
                            # DEBUG: Stampa configurazione sessione completa
                            if hasattr(session_info, '__dict__'):
                                logger.info(f"Configurazione sessione: {str(session_info.__dict__)}")
                    
                    # Gestione eventi di conversazione
                    elif event_type == 'conversation.created' or event_type == 'conversation.updated':
                        logger.info(f"Evento di conversazione ricevuto: {event_type}")
                    
                    # Gestione eventi di input audio
                    elif event_type == 'input_audio_buffer.speech_started':
                        # Notifica l'utente che l'API ha rilevato il parlato
                        speech_msg = f"\n[Parlato rilevato alle {datetime.now().strftime('%H:%M:%S')}]"
                        self.transcription_buffer += speech_msg
                        self.transcription_signal.emit(self.transcription_buffer)
                        logger.info("Parlato rilevato dalla Realtime API")
                    
                    elif event_type == 'input_audio_buffer.speech_stopped':
                        # Notifica l'utente che l'API ha smesso di rilevare il parlato
                        speech_msg = f"\n[Fine parlato alle {datetime.now().strftime('%H:%M:%S')}]"
                        self.transcription_buffer += speech_msg
                        self.transcription_signal.emit(self.transcription_buffer)
                        logger.info("Fine parlato rilevato dalla Realtime API")
                    
                    # Gestione eventi di risposta
                    elif event_type == 'response.created':
                        logger.info("Risposta creata dal server")
                        self.transcription_buffer += f"\n[Risposta in generazione...]"
                        self.transcription_signal.emit(self.transcription_buffer)
                    
                    elif event_type == 'response.text.delta':
                        # Accumula il testo per mostrarlo in blocchi più grandi
                        delta = getattr(event, 'delta', '')
                        current_text += delta
                        logger.info(f"Delta di testo ricevuto: '{delta}'")
                        
                        # Aggiorna anche la risposta per mostrare il testo mentre viene generato
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        self.response_signal.emit(f"[Generazione in corso {timestamp}] {current_text}")
                    
                    elif event_type == 'response.text.done':
                        # Invia il testo completo quando è finito
                        logger.info(f"Testo completo ricevuto: '{current_text}'")
                        if current_text.strip():
                            self.response_signal.emit(current_text)
                            current_text = ""  # Resetta per la prossima risposta
                    
                    elif event_type == 'response.done':
                        logger.info("Risposta completa ricevuta")
                        # Indica che la risposta è stata completata
                        self.transcription_buffer += f"\n[Risposta completata alle {datetime.now().strftime('%H:%M:%S')}]"
                        self.transcription_signal.emit(self.transcription_buffer)
                    
                    # Gestione eventi di elemento creato nella conversazione
                    elif event_type == 'conversation.item.created' or event_type == 'conversation.item.text.created':
                        # Questo evento contiene la trascrizione dell'audio
                        text_content = None
                        
                        # Estrai il testo in base al tipo di evento
                        if event_type == 'conversation.item.text.created':
                            text_content = getattr(event, 'text', None)
                        elif event_type == 'conversation.item.created':
                            item = getattr(event, 'item', None)
                            if item and hasattr(item, 'content'):
                                for content_part in item.content:
                                    if hasattr(content_part, 'text') and content_part.text:
                                        text_content = content_part.text
                                        break
                        
                        logger.info(f"Trascrizione ricevuta: '{text_content}'")
                        
                        if text_content:
                            # Aggiorna la trascrizione
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.transcription_buffer += f"\n[{timestamp}] {text_content}"
                            self.transcription_signal.emit(self.transcription_buffer)
                            
                            # Dopo aver ricevuto la trascrizione, chiediamo una risposta
                            # seguendo il formato della documentazione
                            try:
                                logger.info("Trascrizione ricevuta, inviando richiesta di risposta testuale...")
                                # Richiedi una risposta testuale usando il formato documentato
                                await connection.response.create(
                                    response={
                                        "modalities": ["text"]
                                    }
                                )
                                logger.info("Richiesta risposta testuale inviata dopo trascrizione")
                            except Exception as post_transcription_err:
                                logger.error(f"Errore durante la richiesta di risposta post-trascrizione: {str(post_transcription_err)}")
                    
                    # Gestione errori
                    elif event_type == 'error':
                        # Gestisci gli errori con più dettagli
                        error_msg = f"Errore Realtime API: {getattr(event.error, 'message', 'Errore sconosciuto')}"
                        error_type = getattr(event.error, 'type', 'sconosciuto')
                        error_code = getattr(event.error, 'code', 'sconosciuto')
                        error_details = f" (Tipo: {error_type}, Codice: {error_code})"
                        
                        event_id = getattr(event, 'event_id', None)
                        if event_id:
                            error_details += f", Event ID: {event_id}"
                        
                        logger.error(f"{error_msg}{error_details}")
                        self.error_signal.emit(f"{error_msg}\n{error_details}")
                        
                        # Aggiorna anche la trascrizione per mostrare l'errore all'utente
                        self.transcription_buffer += f"\n[ERRORE: {getattr(event.error, 'message', 'Errore sconosciuto')}]"
                        self.transcription_signal.emit(self.transcription_buffer)
                    
                    else:
                        # Log per eventi non gestiti
                        logger.info(f"Evento non gestito di tipo: {event_type}")
                        if hasattr(event, '__dict__'):
                            logger.info(f"Contenuto evento: {str(event.__dict__)[:500]}...")
                
                except Exception as e:
                    logger.error(f"Errore durante la gestione dell'evento: {str(e)}")
            
            # Log se il loop degli eventi termina
            logger.warning("Il loop di ascolto degli eventi è terminato inaspettatamente")
            self.transcription_buffer += "\n[ATTENZIONE: La connessione agli eventi è terminata]"
            self.transcription_signal.emit(self.transcription_buffer)
        
        except Exception as e:
            logger.error(f"Errore nel loop di eventi: {str(e)}")
            self.error_signal.emit(f"Errore nel loop di eventi: {str(e)}")
            # Aggiorna la trascrizione con l'errore
            self.transcription_buffer += f"\n[ERRORE CRITICO: {str(e)}]"
            self.transcription_signal.emit(self.transcription_buffer)
    
    def run(self):
        """Avvia il loop asincrono per la sessione audio."""
        self.running = True
        asyncio.run(self.realtime_session())
        logger.info("Thread di registrazione terminato")
            
    def stop(self):
        """Ferma la registrazione."""
        logger.info("Richiesta di stop registrazione ricevuta")
        self.running = False
        # Notifica all'utente che stiamo fermando la registrazione
        self.transcription_signal.emit(self.transcription_buffer + "\n[Fermando la registrazione...]")


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
        self.audio_thread = None
        self.chat_history = []
        self.shutdown_in_progress = False  # Flag per evitare click multipli sul pulsante stop
        
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
        
        # Splitter per dividere area trascrizione e risposta
        splitter = QSplitter(Qt.Vertical)
        
        # Area di trascrizione
        transcription_container = QWidget()
        transcription_layout = QVBoxLayout(transcription_container)
        
        transcription_label = QLabel("Trascrizione Audio:")
        transcription_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.transcription_text = QTextEdit()
        self.transcription_text.setReadOnly(True)
        self.transcription_text.setFont(QFont("Arial", 11))
        self.transcription_text.setMinimumHeight(150)
        
        transcription_layout.addWidget(transcription_label)
        transcription_layout.addWidget(self.transcription_text)
        
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
        splitter.addWidget(transcription_container)
        splitter.addWidget(response_container)
        splitter.setSizes([300, 500])  # Proporzioni iniziali
        
        # Controlli
        controls_layout = QHBoxLayout()
        
        self.record_button = QPushButton("Inizia Registrazione")
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
        """Attiva o disattiva la registrazione audio."""
        if not self.recording:
            # Avvia registrazione
            self.recording = True
            self.record_button.setText("Ferma Registrazione")
            self.record_button.setStyleSheet("background-color: #ff5555;")
            
            # Avvia thread di registrazione con Realtime API
            self.audio_thread = RealtimeAudioThread()
            self.audio_thread.transcription_signal.connect(self.update_transcription)
            self.audio_thread.response_signal.connect(self.update_response)
            self.audio_thread.error_signal.connect(self.show_error)
            self.audio_thread.connection_status_signal.connect(self.update_connection_status)
            self.audio_thread.finished.connect(self.recording_finished)
            self.audio_thread.start()
        else:
            # Previeni click multipli
            if self.shutdown_in_progress:
                return
                
            self.shutdown_in_progress = True
            
            # Cambia il pulsante per mostrare che la chiusura è in corso
            self.record_button.setText("Terminazione in corso...")
            self.record_button.setEnabled(False)
            
            # Ferma registrazione
            self.stop_recording()
    
    def stop_recording(self):
        """Ferma la registrazione e ripristina l'interfaccia."""
        if self.audio_thread:
            self.audio_thread.stop()
            # Non usiamo wait() qui perché potrebbe bloccare l'interfaccia utente
            # Il segnale finished ci notificherà quando il thread è terminato
    
    def recording_finished(self):
        """Chiamato quando il thread di registrazione è terminato."""
        self.recording = False
        self.shutdown_in_progress = False
        self.record_button.setText("Inizia Registrazione")
        self.record_button.setStyleSheet("")
        self.record_button.setEnabled(True)
        
        # Aggiungi un messaggio alla trascrizione
        self.transcription_text.append("\n[Registrazione terminata]")
    
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
        if self.recording and self.audio_thread:
            # Mostra un messaggio che stiamo terminando
            self.transcription_text.append("\n[Chiusura dell'applicazione in corso...]")
            # Ferma la registrazione
            self.audio_thread.stop()
            self.audio_thread.wait(2000)  # Aspetta max 2 secondi
        event.accept()


def main():
    """Funzione principale per avviare l'applicazione."""
    app = QApplication(sys.argv)
    window = IntervistaAssistant()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 