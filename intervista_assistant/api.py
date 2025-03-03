#!/usr/bin/env python3
import os
import time
import json
import logging
import threading
import asyncio
import base64
from datetime import datetime
from io import BytesIO

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from openai import OpenAI
from dotenv import load_dotenv
import numpy as np
import pyautogui

from websocket_realtime_text_thread import WebSocketRealtimeTextThread
from utils import ScreenshotManager
# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='api.log')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*", 
                               "allow_headers": ["Content-Type", "Authorization"],
                               "allow_methods": ["GET", "POST", "OPTIONS"],
                               "expose_headers": ["Content-Type", "Authorization"],
                               "supports_credentials": True}})

# Configurazione avanzata di CORS per permettere tutte le origini e metodi
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e8,  # 100MB
    engineio_logger=True,     # Abilita il logger di Engine.IO
    logger=True              # Abilita il logger di Socket.IO
)

# Dizionario per gestire le sessioni attive
active_sessions = {}

class SessionManager:
    """Classe per gestire una sessione di conversazione."""
    
    def __init__(self, session_id):
        """Inizializza una nuova sessione."""
        self.session_id = session_id
        self.recording = False
        self.text_thread = None
        self.chat_history = []
        self.screenshot_manager = ScreenshotManager()
        self.client = None
        self.connected = False
        self.last_activity = datetime.now()
        
        # Inizializza il client OpenAI
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API Key not found. Set the environment variable OPENAI_API_KEY.")
        self.client = OpenAI(api_key=api_key)
        
        # Crea un evento per gestire gli aggiornamenti asincroni
        self.update_event = asyncio.Event()
        self.transcription_updates = []
        self.response_updates = []
        self.error_updates = []
        
    def start_session(self):
        """Avvia una nuova sessione e inizia la registrazione."""
        if not self.recording:
            self.recording = True
            
            # Configura i callback per la classe WebSocketRealtimeTextThread
            callbacks = {
                'on_transcription': self.handle_transcription,
                'on_response': self.handle_response,
                'on_error': self.handle_error,
                'on_connection_status': self.handle_connection_status
            }
            
            self.text_thread = WebSocketRealtimeTextThread(callbacks=callbacks)
            self.text_thread.start()
            
            # Attendi la connessione prima di iniziare la registrazione
            max_wait_time = 10  # secondi
            start_time = time.time()
            while not self.text_thread.connected and time.time() - start_time < max_wait_time:
                time.sleep(0.1)
            
            if not self.text_thread.connected:
                logger.error(f"Connection timeout for session {self.session_id}")
                self.recording = False
                return False
            
            self.text_thread.start_recording()
            return True
        return False
    
    def end_session(self):
        """Termina la sessione corrente."""
        logger.info(f"SessionManager.end_session chiamato per sessione {self.session_id}")
        
        try:
            # Verifica se abbiamo già terminato
            if not self.recording and not self.text_thread:
                logger.info(f"Sessione {self.session_id} era già terminata (recording={self.recording}, text_thread={self.text_thread is not None})")
                return True
                
            # Gestione del thread di trascrizione
            if self.text_thread:
                logger.info(f"Fermando la registrazione per la sessione {self.session_id}")
                
                # Ferma la registrazione se attiva
                try:
                    if self.text_thread.recording:
                        logger.info(f"Thread registrazione attivo, chiamata a stop_recording()")
                        self.text_thread.stop_recording()
                except Exception as e:
                    logger.warning(f"Errore fermando la registrazione: {str(e)}")
                
                # Ferma il thread
                try:
                    logger.info(f"Fermando il thread di trascrizione")
                    self.text_thread.stop()
                    # Non abbiamo più wait come in QThread
                    time.sleep(2)  # Attendi 2 secondi per il completamento
                except Exception as e:
                    logger.warning(f"Errore fermando il thread: {str(e)}")
                
                # Pulizia
                self.text_thread = None
                logger.info(f"Thread rimosso")
                
            # Aggiorna lo stato
            self.recording = False
            logger.info(f"Sessione {self.session_id} terminata con successo")
            return True
            
        except Exception as e:
            logger.error(f"Errore durante la terminazione della sessione {self.session_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # Anche in caso di errore, proviamo a ripulire lo stato
            self.recording = False
            self.text_thread = None
            return False
    
    def handle_transcription(self, text):
        """Gestisce gli aggiornamenti di trascrizione."""
        self.last_activity = datetime.now()
        # Non aggiungere messaggi di stato alla cronologia
        if text != "Recording in progress..." and not text.startswith('\n[Audio processed at'):
            if not self.chat_history or self.chat_history[-1]["role"] != "user" or self.chat_history[-1]["content"] != text:
                self.chat_history.append({"role": "user", "content": text})
        
        # Aggiungi l'aggiornamento alla coda
        timestamp = datetime.now().isoformat()
        self.transcription_updates.append({
            "timestamp": timestamp,
            "text": text
        })
        
        logger.info(f"Transcription update: {text[:50]}...")
    
    def handle_response(self, text):
        """Gestisce gli aggiornamenti di risposta."""
        self.last_activity = datetime.now()
        if not text:
            return
            
        # Aggiorna la cronologia della chat
        if (not self.chat_history or self.chat_history[-1]["role"] != "assistant"):
            self.chat_history.append({"role": "assistant", "content": text})
        elif self.chat_history and self.chat_history[-1]["role"] == "assistant":
            current_time = datetime.now().strftime("%H:%M:%S")
            previous_content = self.chat_history[-1]["content"]
            self.chat_history[-1]["content"] = f"{previous_content}\n--- Response at {current_time} ---\n{text}"
        
        # Aggiungi l'aggiornamento alla coda
        timestamp = datetime.now().isoformat()
        self.response_updates.append({
            "timestamp": timestamp,
            "text": text
        })
        
        logger.info(f"Response update: {text[:50]}...")
    
    def handle_error(self, message):
        """Gestisce gli aggiornamenti di errore."""
        # Ignora alcuni errori noti che non richiedono notifica
        if "buffer too small" in message or "Conversation already has an active response" in message:
            logger.warning(f"Ignored error (log only): {message}")
            return
            
        timestamp = datetime.now().isoformat()
        self.error_updates.append({
            "timestamp": timestamp,
            "message": message
        })
        logger.error(f"Error in session {self.session_id}: {message}")
    
    def handle_connection_status(self, connected):
        """Gestisce gli aggiornamenti dello stato di connessione."""
        self.connected = connected
        logger.info(f"Connection status for session {self.session_id}: {connected}")
    
    def get_updates(self, update_type=None):
        """Restituisce gli aggiornamenti in base al tipo."""
        if update_type == "transcription":
            updates = self.transcription_updates.copy()
            self.transcription_updates = []
            return updates
        elif update_type == "response":
            updates = self.response_updates.copy()
            self.response_updates = []
            return updates
        elif update_type == "error":
            updates = self.error_updates.copy()
            self.error_updates = []
            return updates
        else:
            # Restituisci tutti gli aggiornamenti
            all_updates = {
                "transcription": self.transcription_updates.copy(),
                "response": self.response_updates.copy(),
                "error": self.error_updates.copy()
            }
            self.transcription_updates = []
            self.response_updates = []
            self.error_updates = []
            return all_updates
    
    def send_text_message(self, text):
        """Invia un messaggio di testo al modello."""
        if not self.recording or not self.text_thread or not self.text_thread.connected:
            return False, "Not connected. Please start a session first."
        
        # Verifica che ci sia testo da inviare
        if not text or not text.strip():
            return False, "No text to send."
            
        # Aggiorna la cronologia della chat
        self.chat_history.append({"role": "user", "content": text})
        
        # Invia il testo attraverso il thread realtime
        success = self.text_thread.send_text(text)
        
        return success, None if success else "Unable to send message. Please try again."
    
    def take_and_analyze_screenshot(self, monitor_index=None):
        """Acquisisce uno screenshot e lo invia per l'analisi."""
        if not self.recording or not self.text_thread or not self.text_thread.connected:
            return False, "Not connected. Please start a session first."
        
        try:
            # Acquisisci lo screenshot
            logger.info(f"Capturing screenshot for monitor: {monitor_index}")
            screenshot_path = self.screenshot_manager.take_screenshot(monitor_index=monitor_index)
            
            # Preparazione dei messaggi per gpt-4o-mini con la cronologia della chat
            with open(screenshot_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Prepara i messaggi con la cronologia
            messages = self._prepare_messages_with_history(base64_image)
            
            # Avvia un thread separato per l'analisi
            analysis_thread = threading.Thread(
                target=self._analyze_image_async,
                args=(messages, screenshot_path)
            )
            analysis_thread.start()
            
            logger.info(f"Screenshot analysis initiated for session {self.session_id}")
            return True, screenshot_path
            
        except Exception as e:
            error_msg = f"Error during screenshot capture: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def _analyze_image_async(self, messages, screenshot_path):
        """Analizza l'immagine in modo asincrono."""
        try:
            # Notifica che l'analisi è iniziata
            self.handle_transcription("\n[Screenshot sent for analysis]\n")
            
            # Chiamata a GPT-4o-mini per analizzare l'immagine
            logger.info(f"Sending image to gpt-4o-mini for analysis in session {self.session_id}")
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=1000
            )
            
            # Ottieni la risposta dell'assistente
            assistant_response = response.choices[0].message.content
            logger.info(f"Received response from gpt-4o-mini: {assistant_response[:100]}...")
            
            # Aggiorna la risposta
            self.handle_response(assistant_response)
            
            # Invia un messaggio di contesto al thread realtime
            if self.text_thread and self.text_thread.connected:
                context_msg = f"[I've analyzed the screenshot of a coding exercise/technical interview question. Here's what I found: {assistant_response[:500]}... Let me know if you need more specific details or have questions about how to approach this problem.]"
                success = self.text_thread.send_text(context_msg)
                if success:
                    logger.info(f"Image analysis context sent to realtime thread for session {self.session_id}")
                else:
                    logger.error(f"Failed to send image analysis context to realtime thread for session {self.session_id}")
            
        except Exception as e:
            error_msg = f"Error during image analysis: {str(e)}"
            logger.error(error_msg)
            self.handle_error(error_msg)
    
    def _prepare_messages_with_history(self, base64_image=None):
        """Prepara l'array di messaggi per gpt-4o-mini includendo la cronologia e l'immagine."""
        messages = []
        
        # Aggiungi il messaggio di sistema
        messages.append({
            "role": "system", 
            "content": "You are a specialized assistant for technical interviews, analyzing screenshots of coding exercises and technical problems. Help the user understand the content of these screenshots in detail. Your analysis should be particularly useful for a candidate during a technical interview or coding assessment."
        })
        
        # Aggiungi la cronologia della conversazione precedente
        history_to_include = self.chat_history[:-2] if len(self.chat_history) > 2 else []
        messages.extend(history_to_include)
        
        # Aggiungi il messaggio con l'immagine
        image_url = f"data:image/jpeg;base64,{base64_image}" if base64_image else ""
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Please analyze this screenshot of a potential technical interview question or coding exercise. Describe what you see in detail, extract any visible code or problem statement, explain the problem if possible, and suggest approaches or ideas to solve it."},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        })
        
        return messages
    
    def start_think_process(self):
        """Avvia il processo di pensiero avanzato."""
        if not self.chat_history:
            return False, "No conversation to analyze. Please start a conversation first."
        
        if not self.recording or not self.text_thread or not self.text_thread.connected:
            return False, "Session not active. Please start a session first."
        
        try:
            # Notifica che l'analisi è iniziata
            self.handle_transcription("\n[Deep analysis of the conversation in progress...]\n")
            
            # Prepara i messaggi per l'elaborazione
            messages_for_processing = []
            for msg in self.chat_history:
                messages_for_processing.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Avvia un thread separato per l'analisi
            think_thread = threading.Thread(
                target=self._process_thinking_async,
                args=(messages_for_processing,)
            )
            think_thread.start()
            
            logger.info(f"Think process initiated for session {self.session_id}")
            return True, None
            
        except Exception as e:
            error_msg = f"Error during think process initiation: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def _process_thinking_async(self, messages):
        """Esegue il processo di pensiero avanzato in modo asincrono."""
        try:
            # Step 1: Genera il riassunto con GPT-4o-mini
            logger.info(f"Generating summary with GPT-4o-mini for session {self.session_id}")
            summary = self._generate_summary(messages)
            
            # Invia il riassunto
            self.handle_response("**🧠 CONVERSATION SUMMARY (GPT-4o-mini):**\n\n" + summary)
            
            # Step 2: Esegui l'analisi approfondita con o1-preview
            logger.info(f"Performing in-depth analysis with o1-preview for session {self.session_id}")
            solution = self._generate_solution(summary)
            
            # Invia la soluzione
            self.handle_response("**🚀 IN-DEPTH ANALYSIS AND SOLUTION (o1-preview):**\n\n" + solution)
            
            # Invia un messaggio di contesto al thread realtime
            if self.text_thread and self.text_thread.connected:
                context_msg = f"[I've completed an in-depth analysis of our conversation. I've identified the key problems and generated detailed solutions. If you have specific questions about any part of the solution, let me know!]"
                success = self.text_thread.send_text(context_msg)
                if success:
                    logger.info(f"Analysis context sent to realtime thread for session {self.session_id}")
                else:
                    logger.error(f"Unable to send analysis context to realtime thread for session {self.session_id}")
            
        except Exception as e:
            error_msg = f"Error during thinking process: {str(e)}"
            logger.error(error_msg)
            self.handle_error(error_msg)
    
    def _generate_summary(self, messages):
        """Genera un riassunto della conversazione usando GPT-4o-mini."""
        try:
            # Crea un prompt per il riassunto
            summary_prompt = {
                "role": "system",
                "content": """Analyze the conversation history and create a concise summary in English. 
                Focus on:
                1. Key problems or questions discussed
                2. Important context
                3. Any programming challenges mentioned
                4. Current state of the discussion
                
                Your summary should be comprehensive but brief, highlighting the most important aspects 
                that would help another AI model solve any programming or logical problems mentioned."""
            }
            
            # Clona i messaggi e aggiungi il prompt di sistema
            summary_messages = [summary_prompt] + messages
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=summary_messages
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            raise
    
    def _generate_solution(self, summary):
        """Genera una soluzione dettagliata usando o1-preview basandosi sul riassunto."""
        try:
            # Costruisci il prompt
            prompt = """
            I'm working on a programming or logical task. Here's the context and problem:
            
            # CONTEXT
            {}
            
            Please analyze this situation and:
            1. Identify the core problem or challenge
            2. Develop a structured approach to solve it
            3. Provide a detailed solution with code if applicable
            4. Explain your reasoning
            """.format(summary)
            
            response = self.client.chat.completions.create(
                model="o1-preview",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating solution: {e}")
            raise
    
    def save_conversation(self):
        """Restituisce i dati della conversazione per il salvataggio."""
        conversation_data = {
            "timestamp": datetime.now().isoformat(),
            "messages": self.chat_history
        }
        return conversation_data

    def get_status(self):
        """Restituisce lo stato corrente della sessione."""
        return {
            "is_active": True,
            "is_recording": self.recording,
            "has_text_thread": self.text_thread is not None
        }

# Endpoint per creare una nuova sessione
@app.route('/api/sessions', methods=['POST'])
def create_session():
    """Crea una nuova sessione."""
    try:
        session_id = str(int(time.time()))
        active_sessions[session_id] = SessionManager(session_id)
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": "Session created successfully."
        })
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Endpoint per avviare una sessione con parametri di query
@app.route('/api/sessions/start', methods=['POST', 'OPTIONS'])
def start_session():
    """Avvia una sessione esistente."""
    # Gestione esplicita delle richieste OPTIONS per CORS
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    # Ottieni l'ID della sessione dal parametro di query
    session_id = request.args.get('sessionId')
    
    if not session_id:
        logger.warning("Tentativo di avviare sessione senza ID sessione")
        return jsonify({
            "success": False,
            "error": "Session ID is required."
        }), 400
        
    if session_id not in active_sessions:
        logger.warning(f"Tentativo di avviare sessione non esistente: {session_id}")
        # Creiamo la sessione al volo se non esiste
        active_sessions[session_id] = SessionManager(session_id)
        logger.info(f"Creata nuova sessione: {session_id}")
    
    try:
        session = active_sessions[session_id]
        success = session.start_session()
        logger.info(f"Sessione {session_id} avviata con successo: {success}")
        
        response = jsonify({
            "success": True,
            "message": "Session started successfully."
        })
        # Aggiungi CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        logger.error(f"Error starting session {session_id}: {str(e)}")
        response = jsonify({
            "success": False,
            "error": str(e)
        }), 500
        # Aggiungi CORS headers anche in caso di errore
        if isinstance(response, tuple):
            response[0].headers['Access-Control-Allow-Origin'] = '*'
        else:
            response.headers['Access-Control-Allow-Origin'] = '*'
        return response

# Endpoint per terminare una sessione con parametri di query
@app.route('/api/sessions/end', methods=['POST', 'OPTIONS'])
def end_session():
    """Termina una sessione."""
    # Gestione esplicita delle richieste OPTIONS per CORS
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    # Ottieni l'ID della sessione dal parametro di query
    session_id = request.args.get('sessionId')
    
    if not session_id:
        logger.warning("Tentativo di terminare sessione senza ID sessione")
        response = jsonify({
            "success": False,
            "error": "Session ID is required."
        }), 400
        if isinstance(response, tuple):
            response[0].headers['Access-Control-Allow-Origin'] = '*'
        else:
            response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    if session_id not in active_sessions:
        logger.warning(f"Tentativo di terminare sessione non esistente: {session_id}")
        # Per maggiore robustezza, consideriamo la chiusura di una sessione non esistente come un'operazione riuscita
        response = jsonify({
            "success": True,
            "message": "Session not found, considered as already ended."
        })
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    try:
        session = active_sessions[session_id]
        # Gestione più robusta degli errori nel metodo end_session
        try:
            session.end_session()
        except Exception as e:
            logger.error(f"Errore durante end_session(), ma continuo con la rimozione: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Rimuoviamo la sessione dalla memoria anche se ci sono stati errori in end_session
        try:
            del active_sessions[session_id]
            logger.info(f"Sessione {session_id} rimossa dalla memoria")
        except Exception as e:
            logger.error(f"Errore rimuovendo la sessione dalla memoria: {str(e)}")
        
        logger.info(f"Procedura di chiusura sessione {session_id} completata")
        
        response = jsonify({
            "success": True,
            "message": "Session ended successfully."
        })
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        logger.error(f"Error ending session {session_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({
            "success": False,
            "error": str(e)
        }), 500
        if isinstance(response, tuple):
            response[0].headers['Access-Control-Allow-Origin'] = '*'
        else:
            response.headers['Access-Control-Allow-Origin'] = '*'
        return response

# Endpoint per ottenere gli aggiornamenti in streaming con parametri di query
@app.route('/api/sessions/stream', methods=['GET'])
def stream_session_updates():
    """Stream degli aggiornamenti della sessione in tempo reale."""
    # Ottieni l'ID della sessione dal parametro di query
    session_id = request.args.get('sessionId')
    
    if not session_id:
        logger.warning("Tentativo di ottenere stream senza ID sessione")
        return jsonify({
            "success": False,
            "error": "Session ID is required."
        }), 400
    
    if session_id not in active_sessions:
        logger.warning(f"Tentativo di ottenere stream per sessione non esistente: {session_id}")
        return jsonify({
            "success": False,
            "error": "Session not found."
        }), 404
    
    try:
        # Usa generator function per SSE
        return Response(
            session_sse_generator(session_id),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',  # Per Nginx
                'Access-Control-Allow-Origin': '*'
            }
        )
    except Exception as e:
        logger.error(f"Error setting up SSE for session {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Endpoint per inviare un messaggio di testo con parametri di query
@app.route('/api/sessions/text', methods=['POST'])
def send_text_message():
    """Invia un messaggio di testo."""
    # Ottieni l'ID della sessione dal parametro di query
    session_id = request.args.get('sessionId')
    
    if not session_id:
        logger.warning("Tentativo di inviare messaggio senza ID sessione")
        return jsonify({
            "success": False,
            "error": "Session ID is required."
        }), 400
    
    if session_id not in active_sessions:
        logger.warning(f"Tentativo di inviare messaggio a sessione non esistente: {session_id}")
        return jsonify({
            "success": False,
            "error": "Session not found."
        }), 404
    
    try:
        session = active_sessions[session_id]
        data = request.get_json()
        
        if not data or 'text' not in data:
            logger.warning(f"Messaggio di testo mancante per la sessione {session_id}")
            return jsonify({
                "success": False,
                "error": "Text message is required."
            }), 400
        
        logger.info(f"Invio messaggio di testo alla sessione {session_id}: '{data['text']}'")
        success, error = session.send_text_message(data['text'])
        
        if not success:
            logger.error(f"Errore nell'invio del messaggio per la sessione {session_id}: {error}")
            return jsonify({
                "success": False,
                "error": error
            }), 500
        
        logger.info(f"Messaggio inviato con successo alla sessione {session_id}")
        return jsonify({
            "success": success,
            "message": "Message sent successfully." if success else error
        })
    except Exception as e:
        logger.error(f"Error sending text message for session {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Endpoint per verificare lo stato di una sessione con parametri di query
@app.route('/api/sessions/status', methods=['GET', 'OPTIONS'])
def get_session_status():
    """Verifica lo stato di una sessione."""
    # Gestione esplicita delle richieste OPTIONS per CORS
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    # Ottieni l'ID della sessione dal parametro di query
    session_id = request.args.get('sessionId')
    
    if not session_id:
        logger.warning("Tentativo di verificare stato sessione senza ID sessione")
        return jsonify({
            "success": False,
            "error": "Session ID is required."
        }), 400
    
    if session_id not in active_sessions:
        logger.warning(f"Tentativo di verificare stato sessione non esistente: {session_id}")
        return jsonify({
            "success": False,
            "error": "Session not found."
        }), 404
    
    try:
        session = active_sessions[session_id]
        status = session.get_status()
        
        return jsonify({
            "success": True,
            "status": status
        })
    except Exception as e:
        logger.error(f"Error getting session status for {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@socketio.on('connect')
def handle_connect():
    """Gestisce la connessione di un client Socket.IO"""
    logger.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Gestisce la disconnessione di un client Socket.IO"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('audio_data')
def handle_audio_data(session_id, audio_data):
    """Gestisce i dati audio ricevuti dal client"""
    try:
        data_type = type(audio_data).__name__
        data_size = len(audio_data) if isinstance(audio_data, (bytes, list)) else 'non bytes/list'
        logger.info(f"Ricevuti dati audio per la sessione {session_id}: {data_size} bytes, tipo {data_type}")
    
        if session_id not in active_sessions:
            logger.error(f"SocketIO: Session {session_id} not found")
            # Creiamo una nuova sessione al volo
            active_sessions[session_id] = SessionManager(session_id)
            # E avviamo la sessione
            success = active_sessions[session_id].start_session()
            if success:
                logger.info(f"Creata e avviata nuova sessione {session_id} al volo")
                emit('status', {'message': 'New session created and started'})
            else:
                logger.error(f"Impossibile avviare la sessione {session_id}")
                emit('error', {'message': 'Failed to start new session'})
                return
        
        session = active_sessions[session_id]
        # Se la sessione non è in registrazione, proviamo ad avviarla
        if not session.recording or not session.text_thread:
            logger.warning(f"SocketIO: Session {session_id} not recording, trying to start it")
            success = session.start_session()
            if not success:
                logger.error(f"SocketIO: Failed to start recording for session {session_id}")
                emit('error', {'message': 'Session not recording'})
                return
            else:
                logger.info(f"SocketIO: Successfully started recording for session {session_id}")
                emit('status', {'message': 'Session recording started'})
        
        try:
            # Gestisci i dati audio in base al formato
            if isinstance(audio_data, bytes):
                # Usa direttamente i dati binari
                processed_audio = audio_data
                logger.debug(f"Received binary audio data: size={len(processed_audio)} bytes")
            else:
                # Prova a interpretare come array di samples
                try:
                    samples = np.array(audio_data, dtype=np.int16)
                    processed_audio = samples.tobytes()
                    logger.debug(f"Processed audio data: samples={len(audio_data)}")
                except Exception as e:
                    logger.error(f"Error processing audio data: {e}")
                    emit('error', {'message': 'Invalid audio data format'})
                    return
            
            # Invia i dati audio al thread
            if hasattr(session.text_thread, 'add_audio_data'):
                success = session.text_thread.add_audio_data(processed_audio)
                if not success:
                    logger.warning("Failed to add audio data to thread")
            else:
                logger.error("text_thread doesn't have add_audio_data method")
                emit('error', {'message': 'Internal server error - missing add_audio_data method'})
        except Exception as e:
            logger.error(f"Error handling audio data: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            emit('error', {'message': f'Internal server error: {str(e)}'})
    except Exception as outer_e:
        logger.error(f"Critical error in handle_audio_data: {str(outer_e)}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            emit('error', {'message': 'Critical server error'})
        except:
            pass

# Task periodico per ripulire le sessioni inattive
def cleanup_inactive_sessions():
    """Rimuove le sessioni inattive."""
    while True:
        try:
            current_time = datetime.now()
            sessions_to_remove = []
            
            for session_id, session in active_sessions.items():
                # Considera inattiva una sessione dopo 30 minuti
                inactivity_period = (current_time - session.last_activity).total_seconds() / 60
                if inactivity_period > 30:
                    sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                try:
                    if active_sessions[session_id].recording:
                        active_sessions[session_id].end_session()
                    del active_sessions[session_id]
                    logger.info(f"Removed inactive session {session_id}")
                except Exception as e:
                    logger.error(f"Error removing inactive session {session_id}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
        
        # Controlla ogni 5 minuti
        time.sleep(300)

# Avvia il task di pulizia in un thread separato
cleanup_thread = threading.Thread(target=cleanup_inactive_sessions, daemon=True)
cleanup_thread.start()

def session_sse_generator(session_id):
    """Generator per lo streaming SSE di una sessione."""
    try:
        session = active_sessions[session_id]
        logger.info(f"Avvio streaming SSE per sessione {session_id}")
        
        while True:
            # Verifichiamo che la sessione esista ancora e sia attiva
            if session_id not in active_sessions:
                logger.info(f"Sessione {session_id} non più esistente, terminazione stream SSE")
                break
                
            session = active_sessions[session_id]
            if not session.recording:
                logger.info(f"Sessione {session_id} non più in registrazione, terminazione stream SSE")
                break
            
            # Controlla se ci sono aggiornamenti ogni 100ms
            all_updates = session.get_updates()
            
            if all_updates['transcription']:
                for update in all_updates['transcription']:
                    yield f"event: transcription\ndata: {json.dumps(update)}\n\n"
            
            if all_updates['response']:
                for update in all_updates['response']:
                    yield f"event: response\ndata: {json.dumps(update)}\n\n"
            
            if all_updates['error']:
                for update in all_updates['error']:
                    yield f"event: error\ndata: {json.dumps(update)}\n\n"
            
            time.sleep(0.1)
            
        logger.info(f"Stream SSE terminato per sessione {session_id}")
        
    except Exception as e:
        logger.error(f"Errore durante lo streaming SSE per sessione {session_id}: {str(e)}")
        yield f"event: error\ndata: {json.dumps({'timestamp': datetime.now().isoformat(), 'message': 'Server stream error'})}\n\n"

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)
