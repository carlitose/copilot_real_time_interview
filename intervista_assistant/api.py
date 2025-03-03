#!/usr/bin/env python3
"""
Backend API for Intervista Assistant.
Manages communication with OpenAI models and provides endpoints for the frontend.
Audio must always be sent via Socket.IO.
"""
import os
import time
import json
import uuid
import logging
import base64
import threading
import numpy as np
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from openai import OpenAI

# Import the thread for real-time API communication with OpenAI
try:
    # Try to import as a module
    from intervista_assistant.web_realtime_text_thread import WebRealtimeTextThread
except ImportError:
    # Local import fallback
    from web_realtime_text_thread import WebRealtimeTextThread

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log'),
        logging.StreamHandler()  # Aggiunto handler per la console
    ]
)
logger = logging.getLogger(__name__)
logger.info("Backend server started")

# Flask and SocketIO initialization
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)  # Abilitato logging per Socket.IO

# OpenAI client for non-real-time functionalities
client = OpenAI()

# Active sessions - stored as a dictionary session_id -> SessionManager
active_sessions = {}

# Maximum inactivity time for a session (minutes)
SESSION_TIMEOUT_MINUTES = 30

class SessionManager:
    """
    Manages a conversation session, including communication with OpenAI.
    Each session is associated with a frontend client.
    """
    
    def __init__(self, session_id):
        """Initializes a new session."""
        self.session_id = session_id
        self.recording = False
        self.text_thread = None
        self.last_activity = datetime.now()
        self.chat_history = []
        
        # Queues for updates
        self.transcription_updates = []
        self.response_updates = []
        self.error_updates = []
        self.connection_updates = []
    
    def start_session(self):
        """
        Starts a new session and prepares the connection with the OpenAI API.
        Does not start audio recording automatically.
        """
        if not self.recording:
            self.recording = True
            
            # Configure callbacks for real-time API communication
            callbacks = {
                'on_transcription': self.handle_transcription,
                'on_response': self.handle_response,
                'on_error': self.handle_error,
                'on_connection_status': self.handle_connection_status
            }
            
            # Initialize the thread for real-time communication
            self.text_thread = WebRealtimeTextThread(callbacks=callbacks)
            
            # Start the thread and get a reference to it
            thread = self.text_thread.start()
            
            # Wait for the connection before considering the session started
            max_wait_time = 10  # seconds
            start_time = time.time()
            
            # Use a lock when checking the connected status
            while time.time() - start_time < max_wait_time:
                # Safe way to check the connected status
                if hasattr(self.text_thread, 'lock'):
                    with self.text_thread.lock:
                        if self.text_thread.connected:
                            break
                else:
                    # Fallback if no lock attribute
                    if getattr(self.text_thread, 'connected', False):
                        break
                time.sleep(0.1)
            
            # Check if connection was established
            is_connected = False
            if hasattr(self.text_thread, 'lock'):
                with self.text_thread.lock:
                    is_connected = self.text_thread.connected
            else:
                is_connected = getattr(self.text_thread, 'connected', False)
                
            if not is_connected:
                logger.error(f"Connection timeout for session {self.session_id}")
                self.recording = False
                return False
            
            logger.info(f"Session {self.session_id} started successfully")
            return True
        return False
    
    def end_session(self):
        """Ends the current session and frees resources."""
        logger.info(f"Ending session {self.session_id}")
        
        try:
            # Check if the session is already ended
            if not self.recording and not self.text_thread:
                return True
                
            # Handle the real-time communication thread
            if self.text_thread:
                # Stop recording if active
                if self.text_thread.recording:
                    self.text_thread.stop_recording()
                
                # Stop the thread
                self.text_thread.stop()
                time.sleep(1)  # Wait a second for completion
                
                # Cleanup
                self.text_thread = None
                
            # Update the state
            self.recording = False
            logger.info(f"Session {self.session_id} ended successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error ending session {self.session_id}: {str(e)}")
            return False
    
    def handle_transcription(self, text):
        """Handles transcription updates from the real-time API."""
        self.last_activity = datetime.now()
        if not text:
            return
            
        # Update chat history only for complete transcriptions
        if text.endswith("[fine]") or text.endswith("[end]"):
            clean_text = text.replace("[fine]", "").replace("[end]", "").strip()
            if clean_text:
                self.chat_history.append({"role": "user", "content": clean_text})
        
        # Add the update to the queue
        timestamp = datetime.now().isoformat()
        self.transcription_updates.append({
            "timestamp": timestamp,
            "text": text
        })
        
        logger.info(f"Transcription: {text[:50]}...")
    
    def handle_response(self, text):
        """Handles response updates from the real-time API."""
        self.last_activity = datetime.now()
        if not text:
            return
            
        # Update chat history
        if (not self.chat_history or self.chat_history[-1]["role"] != "assistant"):
            self.chat_history.append({"role": "assistant", "content": text})
        elif self.chat_history and self.chat_history[-1]["role"] == "assistant":
            current_time = datetime.now().strftime("%H:%M:%S")
            previous_content = self.chat_history[-1]["content"]
            self.chat_history[-1]["content"] = f"{previous_content}\n--- Response at {current_time} ---\n{text}"
        
        # Add the update to the queue
        timestamp = datetime.now().isoformat()
        self.response_updates.append({
            "timestamp": timestamp,
            "text": text
        })
        
        logger.info(f"Response: {text[:50]}...")
    
    def handle_error(self, message):
        """Handles error updates."""
        # Ignore some known errors that do not require notification
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
        """Handles connection status updates."""
        timestamp = datetime.now().isoformat()
        self.connection_updates.append({
            "timestamp": timestamp,
            "connected": connected
        })
        logger.info(f"Connection status for session {self.session_id}: {'connected' if connected else 'disconnected'}")
    
    def get_updates(self, update_type=None):
        """Returns updates based on the type and removes them from the queue."""
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
        elif update_type == "connection":
            updates = self.connection_updates.copy()
            self.connection_updates = []
            return updates
        else:
            # Return all updates
            all_updates = {
                "transcription": self.transcription_updates.copy(),
                "response": self.response_updates.copy(),
                "error": self.error_updates.copy(),
                "connection": self.connection_updates.copy()
            }
            self.transcription_updates = []
            self.response_updates = []
            self.error_updates = []
            self.connection_updates = []
            return all_updates
    
    def send_text_message(self, text):
        """Sends a text message to the model."""
        self.last_activity = datetime.now()
        
        if not text:
            logger.warning("Empty text message received")
            return False
        
        if not self.text_thread:
            logger.error("No active session for sending text message")
            return False
        
        # Use the WebRealtimeTextThread's send_text method
        try:
            # Make sure the thread is initialized and connected
            if hasattr(self.text_thread, 'send_text'):
                success = self.text_thread.send_text(text)
                if success:
                    logger.info(f"Text message sent to model: {text[:50]}...")
                    return True
                else:
                    logger.error("Failed to send text message")
                    return False
            else:
                logger.error("text_thread does not have the method send_text")
                return False
        except Exception as e:
            logger.error(f"Error sending text message: {str(e)}")
            return False
    
    def process_screenshot(self, image_data):
        """
        Analyzes a screenshot using the OpenAI API.
        
        Args:
            image_data: Image data in base64 format
            
        Returns:
            (success, response_or_error): Tuple with status and response/error
        """
        try:
            # Prepare messages with history and image
            messages = self._prepare_messages_with_history(base64_image=image_data)
            
            # Perform image analysis asynchronously
            threading.Thread(
                target=self._analyze_image_async,
                args=(messages, image_data),
                daemon=True
            ).start()
            
            return True, None
            
        except Exception as e:
            error_message = f"Error processing screenshot: {str(e)}"
            logger.error(error_message)
            return False, error_message
    
    def _analyze_image_async(self, messages, image_data):
        """Performs image analysis asynchronously."""
        try:
            response = client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=messages,
                max_tokens=4000
            )
            
            assistant_response = response.choices[0].message.content
            
            # Add to chat history
            self.chat_history.append({
                "role": "assistant", 
                "content": assistant_response
            })
            
            # Send the response as an update
            self.handle_response(assistant_response)
            
            # Also send a message through the real-time thread to maintain context
            if self.text_thread and self.text_thread.connected:
                context_msg = "[I have analyzed the screenshot you sent me. If you have specific questions, feel free to ask!]"
                self.text_thread.send_text(context_msg)
            
            logger.info("Image analysis completed successfully")
            
        except Exception as e:
            error_message = f"Error analyzing image: {str(e)}"
            self.handle_error(error_message)
    
    def _prepare_messages_with_history(self, base64_image=None):
        """Prepares messages for the API including chat history."""
        messages = [
            {
                "role": "system",
                "content": "You are an expert job interview assistant, specialized in helping candidates in real-time during interviews. Provide useful, clear, and concise advice on both technical and behavioral aspects."
            }
        ]
        
        # Add chat history (last 10 messages)
        for msg in self.chat_history[-10:]:
            messages.append(msg.copy())
        
        # Add the image if present
        if base64_image:
            content = [
                {
                    "type": "text",
                    "text": "Analyze this interview screenshot. Describe what you see, what questions/challenges are present, and provide advice on how to respond or solve the problem."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
            messages.append({"role": "user", "content": content})
        
        return messages
    
    def start_think_process(self):
        """
        Starts an advanced thinking process that generates a summary
        and a detailed solution based on the conversation.
        """
        if not self.chat_history:
            return False, "No conversation to analyze."
        
        # Start the thinking process in a separate thread
        threading.Thread(
            target=self._process_thinking_async,
            args=(self._prepare_messages_with_history(),),
            daemon=True
        ).start()
        
        return True, None
    
    def _process_thinking_async(self, messages):
        """Performs the thinking process asynchronously."""
        try:
            # First generate a summary
            summary = self._generate_summary(messages)
            
            # Notify the user that the summary is ready
            self.handle_response("**🧠 CONVERSATION ANALYSIS:**\n\n" + summary)
            
            # Generate a detailed solution based on the summary
            solution = self._generate_solution(summary)
            
            # Notify the user that the solution is ready
            self.handle_response("**🚀 DETAILED SOLUTION:**\n\n" + solution)
            
            # Also send a message through the real-time thread
            if self.text_thread and self.text_thread.connected:
                context_msg = "[I have completed an in-depth analysis of our conversation, identified key issues, and generated detailed solutions. If you have specific questions, I am here to help!]"
                self.text_thread.send_text(context_msg)
            
            logger.info("Thinking process completed successfully")
            
        except Exception as e:
            error_message = f"Error in the thinking process: {str(e)}"
            self.handle_error(error_message)
    
    def _generate_summary(self, messages):
        """Generates a summary of the conversation."""
        try:
            # Prepare messages for the summary
            summary_messages = messages.copy()
            summary_messages.append({
                "role": "user",
                "content": "Analyze our conversation and create a detailed summary that includes: 1) The context of the interview 2) The main challenges/questions discussed 3) The key points of my answers 4) Areas for improvement. Be specific and detailed."
            })
            
            # API call
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=summary_messages,
                max_tokens=2000
            )
            
            summary = response.choices[0].message.content
            logger.info("Summary generated successfully")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise
    
    def _generate_solution(self, summary):
        """Generates a detailed solution based on the summary."""
        try:
            # Prepare messages for the solution
            solution_messages = [
                {
                    "role": "system",
                    "content": "You are an expert job interview coach with extensive experience in technical and behavioral interviews. Your task is to provide detailed feedback and personalized solutions."
                },
                {
                    "role": "user",
                    "content": f"Here is a summary of my interview:\n\n{summary}\n\nBased on this summary, provide me with a detailed solution that includes: 1) Specific feedback on my answers 2) Alternative or better solutions for the discussed challenges 3) Scripts or phrases I could have used 4) Practical advice to improve in weak areas 5) Strategies for follow-up after the interview. Be specific, practical, and detailed."
                }
            ]
            
            # API call
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=solution_messages,
                max_tokens=4000
            )
            
            solution = response.choices[0].message.content
            logger.info("Solution generated successfully")
            return solution
            
        except Exception as e:
            logger.error(f"Error generating solution: {str(e)}")
            raise
    
    def save_conversation(self):
        """Saves the current conversation to a file."""
        try:
            if not self.chat_history:
                logger.warning(f"No conversation to save for session {self.session_id}")
                return False, None
            
            # Create a timestamp for the filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.json"
            
            # Create the saving directory if it doesn't exist
            save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_conversations")
            os.makedirs(save_dir, exist_ok=True)
            
            # Prepare the data to save
            save_data = {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "messages": self.chat_history
            }
            
            # Save to file
            filepath = os.path.join(save_dir, filename)
            with open(filepath, 'w') as f:
                json.dump(save_data, f, indent=2)
            
            logger.info(f"Conversation saved to {filepath}")
            return True, filename
            
        except Exception as e:
            logger.error(f"Error saving conversation: {str(e)}")
            return False, None
    
    def get_status(self):
        """Returns the current status of the session."""
        return {
            "session_id": self.session_id,
            "recording": self.recording,
            "connected": self.text_thread.connected if self.text_thread else False,
            "last_activity": self.last_activity.isoformat(),
            "message_count": len(self.chat_history)
        }

# Decorator to check if the session exists
def require_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip session check for OPTIONS requests
        if request.method == 'OPTIONS':
            return jsonify({"success": True}), 200
            
        session_id = request.json.get('session_id')
        if not session_id or session_id not in active_sessions:
            return jsonify({"success": False, "error": "Session not found"}), 404
            
        # Store the session in the request context to avoid race conditions
        request.session_manager = active_sessions.get(session_id)
        if not request.session_manager:
            return jsonify({"success": False, "error": "Session disappeared during request processing"}), 404
            
        return f(*args, **kwargs)
    return decorated_function

#
# API Endpoints
#

@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """Handle OPTIONS requests for all API endpoints."""
    response = jsonify({"success": True})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    return response, 200

@app.route('/api/sessions', methods=['POST', 'OPTIONS'])
def create_session():
    """Creates a new session."""
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200
        
    # Generate a new session ID if not provided
    session_id = request.json.get('session_id', str(uuid.uuid4()))
    
    # Check if the session already exists
    if session_id in active_sessions:
        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": "Existing session reused"
        }), 200
    
    # Create a new session
    active_sessions[session_id] = SessionManager(session_id)
    
    return jsonify({
        "success": True,
        "session_id": session_id,
        "message": "New session created"
    }), 201

@app.route('/api/sessions/start', methods=['POST', 'OPTIONS'])
@require_session
def start_session():
    """Starts an existing session."""
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200
        
    session_id = request.json.get('session_id')
    session = active_sessions[session_id]
    
    # Check if the session is already started
    if session.recording:
        return jsonify({
            "success": True,
            "message": "Session already started"
        }), 200
    
    # Start the session
    success = session.start_session()
    
    if success:
        return jsonify({
            "success": True,
            "message": "Session started successfully"
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Unable to start the session"
        }), 500

@app.route('/api/sessions/end', methods=['POST', 'OPTIONS'])
@require_session
def end_session():
    """Ends an existing session."""
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200
        
    session_id = request.json.get('session_id')
    
    # Use the session from the request context
    session = request.session_manager
    
    # End the session
    success = session.end_session()
    
    if success:
        # Save the conversation and remove the session
        save_success, filename = session.save_conversation()
        
        # Safely remove the session from active_sessions
        if session_id in active_sessions:
            del active_sessions[session_id]
        
        return jsonify({
            "success": True,
            "message": "Session ended successfully",
            "conversation_saved": save_success,
            "filename": filename if save_success else None
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Unable to end the session"
        }), 500

@app.route('/api/sessions/stream', methods=['GET'])
def stream_session_updates():
    """SSE stream for session updates."""
    session_id = request.args.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({"success": False, "error": "Session not found"}), 404
    
    return Response(
        stream_with_context(session_sse_generator(session_id)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

@app.route('/api/sessions/text', methods=['POST'])
@require_session
def send_text_message():
    """Sends a text message to the model."""
    session_id = request.json.get('session_id')
    text = request.json.get('text')
    
    if not text:
        return jsonify({
            "success": False,
            "error": "No text provided"
        }), 400
    
    session = active_sessions[session_id]
    success = session.send_text_message(text)
    
    if success:
        return jsonify({
            "success": True,
            "message": "Message sent successfully"
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Failed to send message to the model"
        }), 400

@app.route('/api/sessions/screenshot', methods=['POST'])
@require_session
def process_screenshot():
    """Processes a screenshot sent from the frontend."""
    session_id = request.json.get('session_id')
    image_data = request.json.get('image_data')
    
    if not image_data:
        return jsonify({
            "success": False,
            "error": "No image provided"
        }), 400
    
    # Remove the prefix "data:image/png;base64," if present
    if image_data.startswith('data:'):
        image_data = image_data.split(',')[1]
    
    session = active_sessions[session_id]
    success, error = session.process_screenshot(image_data)
    
    if success:
        return jsonify({
            "success": True,
            "message": "Screenshot processed successfully"
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": error
        }), 500

@app.route('/api/sessions/think', methods=['POST'])
@require_session
def start_think_process():
    """Starts the advanced thinking process."""
    session_id = request.json.get('session_id')
    session = active_sessions[session_id]
    
    success, error = session.start_think_process()
    
    if success:
        return jsonify({
            "success": True,
            "message": "Thinking process started successfully"
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": error
        }), 400

@app.route('/api/sessions/status', methods=['GET', 'OPTIONS'])
def get_session_status():
    """Gets the status of a session."""
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200
        
    session_id = request.args.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({
            "success": False,
            "error": "Session not found"
        }), 404
    
    session = active_sessions[session_id]
    return jsonify({
        "success": True,
        "status": session.get_status()
    }), 200

@app.route('/api/sessions/save', methods=['POST'])
@require_session
def save_conversation():
    """Saves the conversation to a JSON file."""
    session_id = request.json.get('session_id')
    session = active_sessions[session_id]
    
    success, result = session.save_conversation()
    
    if success:
        return jsonify({
            "success": True,
            "message": "Conversation saved successfully",
            "filename": result
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": f"Unable to save the conversation: {result}"
        }), 500

#
# Socket.IO handlers
#

@socketio.on('connect')
def handle_connect():
    """Handles a Socket.IO client connection."""
    logger.info(f"New Socket.IO client connected: {request.sid}")

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
    acknowledgement = {'received': False, 'error': None}
    
    try:
        # Log only essential metadata about the audio data
        audio_type = type(audio_data).__name__
        if isinstance(audio_data, list):
            audio_length = len(audio_data)
            # Rimuoviamo il logging dei sample values che crea log enormi
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
        
        # Check if the session is recording
        if not session.recording or not session.text_thread:
            logger.warning(f"[SOCKET.IO:AUDIO] Session {session_id} not recording")
            emit('error', {'message': 'Session not recording'})
            acknowledgement['error'] = 'Session not recording'
            return acknowledgement
        
        # Process the audio data and send it to the WebRealtimeTextThread
        # Rimuoviamo questo log per ridurre la verbosità
        
        # Check if audio_data is not empty
        if not audio_data:
            logger.warning(f"[SOCKET.IO:AUDIO] Empty audio data received for session {session_id}")
            acknowledgement['error'] = 'Empty audio data'
            return acknowledgement
            
        try:
            # Convert to numpy array if it's a list
            if isinstance(audio_data, list):
                audio_data = np.array(audio_data, dtype=np.int16)
                # Riduciamo i dettagli nel log
                logger.info(f"[SOCKET.IO:AUDIO] Converted list to numpy array for session {session_id}")
            
            # Process the audio data with the text thread
            if session.text_thread:
                session.text_thread.add_audio_data(audio_data)
        except Exception as e:
            logger.error(f"[SOCKET.IO:AUDIO] Error processing audio in text thread: {str(e)}")
            acknowledgement['error'] = f'Error in text thread: {str(e)}'
            return acknowledgement
        
        # Add success acknowledgement at the end of the function
        acknowledgement['received'] = True
        logger.info(f"[SOCKET.IO:AUDIO] Successfully processed audio data for session {session_id}")
        return acknowledgement
        
    except Exception as e:
        logger.error(f"[SOCKET.IO:AUDIO] Error processing audio data: {str(e)}")
        acknowledgement['error'] = str(e)
        return acknowledgement

# Periodic task to clean up inactive sessions
def cleanup_inactive_sessions():
    """Removes inactive sessions."""
    now = datetime.now()
    inactive_sessions = []
    
    # Create a copy of the keys to avoid modification during iteration
    session_ids = list(active_sessions.keys())
    
    for session_id in session_ids:
        # Check if session still exists (might have been removed by other processes)
        if session_id not in active_sessions:
            continue
            
        session = active_sessions[session_id]
        inactivity_time = (now - session.last_activity).total_seconds() / 60
        
        if inactivity_time > SESSION_TIMEOUT_MINUTES:
            inactive_sessions.append(session_id)
            logger.info(f"Session {session_id} inactive for {inactivity_time:.1f} minutes, will be removed")
    
    for session_id in inactive_sessions:
        try:
            # Check if session still exists
            if session_id not in active_sessions:
                logger.info(f"Session {session_id} already removed, skipping cleanup")
                continue
                
            # End the session and save the conversation
            session = active_sessions[session_id]
            session.end_session()
            session.save_conversation()
            
            # Safely remove the session
            if session_id in active_sessions:
                del active_sessions[session_id]
                logger.info(f"Inactive session {session_id} successfully removed")
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {str(e)}")
            # Continue with other sessions even if one fails
            continue

# Generatore SSE per gli aggiornamenti della sessione
def session_sse_generator(session_id):
    """Genera eventi SSE per gli aggiornamenti della sessione."""
    try:
        yield "data: {\"event\": \"connected\", \"message\": \"Stream connected\"}\n\n"
        
        while session_id in active_sessions:
            session = active_sessions[session_id]
            updates = session.get_updates()
            
            # Invia solo se ci sono aggiornamenti
            has_updates = any(updates[key] for key in updates)
            
            if has_updates:
                yield f"data: {json.dumps(updates)}\n\n"
            
            # Aggiorna l'attività se il client è ancora connesso
            session.last_activity = datetime.now()
            
            # Pausa breve per evitare carico eccessivo
            time.sleep(0.1)
            
    except GeneratorExit:
        logger.info(f"Client disconnesso dallo stream SSE per la sessione {session_id}")
    except Exception as e:
        logger.error(f"Errore nello stream SSE per la sessione {session_id}: {str(e)}")
        yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

# Avvia il task di pulizia ogni minuto
@socketio.on('connect')
def start_cleanup_task():
    if not hasattr(start_cleanup_task, 'started'):
        def run_cleanup():
            while True:
                time.sleep(60)  # 1 minuto
                cleanup_inactive_sessions()
                
        cleanup_thread = threading.Thread(target=run_cleanup, daemon=True)
        cleanup_thread.start()
        start_cleanup_task.started = True

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
