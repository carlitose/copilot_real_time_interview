#!/usr/bin/env python3
"""
Session management for Intervista Assistant.
Handles conversation sessions and communication with OpenAI.
"""
import os
import time
import json
import logging
import threading
import numpy as np
from datetime import datetime

from openai import OpenAI

# Import the thread for real-time API communication with OpenAI
try:
    # Try to import as a module
    from intervista_assistant.models.openai_integration import WebRealtimeTextThread
except ImportError:
    # Local import fallback
    from intervista_assistant.web_realtime_text_thread import WebRealtimeTextThread

# Logging configuration
logger = logging.getLogger(__name__)

# OpenAI client for non-real-time functionalities
client = OpenAI()

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
        self.log_updates = []
        
        # Variables for managing duplicate or frequent responses
        self.last_response_time = None
        self.min_response_interval = 3  # Minimum seconds between responses
        self.last_response_content = ""
    
    def start_session(self):
        """
        Start the session by initializing the communication with the OpenAI API.
        
        Returns:
            tuple: (success, error_message)
        """
        try:
            if self.recording:
                logger.info(f"Session {self.session_id} already started")
                return True, None
                
            logger.info(f"Starting session {self.session_id}")
            
            # Create a new WebRealtimeTextThread instance
            callbacks = {
                'on_transcription': lambda text: self.handle_transcription(text),
                'on_response': lambda text: self.handle_response(text),
                'on_error': lambda message: self.handle_error(message),
                'on_connection_status': lambda connected: self.handle_connection_status(connected)
            }
            
            self.text_thread = WebRealtimeTextThread(callbacks)
            
            # Start the WebSocket communication
            self.text_thread.start()
            
            # Mark the session as recording
            self.recording = True
            self.updates = {
                'transcription': '',
                'response': '',
                'error': '',
                'connection_status': False
            }
            
            # Update the last activity timestamp
            self.last_activity = datetime.now()
            
            # Wait for the WebSocket to initialize (max 2 seconds)
            max_wait = 2  # seconds
            wait_interval = 0.1  # seconds
            waited = 0
            
            while waited < max_wait:
                if self.text_thread.connected:
                    logger.info(f"WebSocket connection established after {waited:.1f} seconds")
                    break
                waited += wait_interval
                time.sleep(wait_interval)
            
            # We continue even if the WebSocket is not yet connected
            # The client will receive updates through the SSE stream
            
            logger.info(f"Session {self.session_id} started successfully")
            return True, None
            
        except Exception as e:
            error_msg = f"Error starting session: {str(e)}"
            logger.error(error_msg)
            self.handle_error(error_msg)
            return False, error_msg
    
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
    
    def handle_response(self, text, final=False):
        """Handles response updates from the real-time API."""
        self.last_activity = datetime.now()
        if not text:
            return
        
        # Apply the filter to avoid too frequent or repetitive responses
        filtered_text = self._filter_response(text)
        if not filtered_text:
            logger.info(f"Response filtered out (too frequent or similar to previous): {text[:30]}...")
            return
            
        # Update chat history
        if (not self.chat_history or self.chat_history[-1]["role"] != "assistant"):
            self.chat_history.append({"role": "assistant", "content": filtered_text})
        elif self.chat_history and self.chat_history[-1]["role"] == "assistant":
            current_time = datetime.now().strftime("%H:%M:%S")
            previous_content = self.chat_history[-1]["content"]
            self.chat_history[-1]["content"] = f"{previous_content}\n--- Response at {current_time} ---\n{filtered_text}"
        
        # Add the update to the queue
        timestamp = datetime.now().isoformat()
        self.response_updates.append({
            "timestamp": timestamp,
            "text": filtered_text,
            "final": final
        })
        
        logger.info(f"Response: {filtered_text[:50]}...")
    
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
    
    def handle_log(self, text):
        """Handles log updates that should not be saved in chat history."""
        self.last_activity = datetime.now()
        if not text:
            return
            
        # Add the update to the queue
        timestamp = datetime.now().isoformat()
        self.log_updates.append({
            "timestamp": timestamp,
            "text": text
        })
        
        logger.info(f"Log: {text[:50]}...")
    
    def get_updates(self, update_type=None):
        """
        Gets all updates of the specified type.
        If update_type is None, returns all updates.
        """
        if update_type == "transcription":
            return self.transcription_updates
        elif update_type == "response":
            return self.response_updates
        elif update_type == "error":
            return self.error_updates
        elif update_type == "connection":
            return self.connection_updates
        elif update_type == "log":
            return self.log_updates
        elif update_type is None:
            # If no type is specified, return all updates as a flat list
            all_updates = []
            
            for update in self.transcription_updates:
                update_copy = update.copy()
                update_copy["type"] = "transcription"
                all_updates.append(update_copy)
                
            for update in self.response_updates:
                update_copy = update.copy()
                update_copy["type"] = "response"
                all_updates.append(update_copy)
                
            for update in self.error_updates:
                update_copy = update.copy()
                update_copy["type"] = "error"
                all_updates.append(update_copy)
                
            for update in self.connection_updates:
                update_copy = update.copy()
                update_copy["type"] = "connection"
                all_updates.append(update_copy)
                
            for update in self.log_updates:
                update_copy = update.copy()
                update_copy["type"] = "log"
                all_updates.append(update_copy)
                
            # Sort updates by timestamp
            all_updates.sort(key=lambda x: x["timestamp"])
            return all_updates
        else:
            return []
    
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
            # Send a processing notification
            self.handle_log("Analyzing the screenshot...")
            
            # Call OpenAI API for image analysis
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
            )
            
            assistant_response = response.choices[0].message.content
            
            # Add to chat history
            self.chat_history.append({
                "role": "assistant", 
                "content": assistant_response
            })
            
            # Log the response
            logger.info(f"Image analysis response: {assistant_response[:100]}...")
            
            # Send the response as an update
            self.handle_response(assistant_response, final=True)
            
            # Also send a message through the real-time thread to maintain context
            if self.text_thread and self.text_thread.connected:
                # Send the complete screenshot analysis to the real-time model
                context_msg = f"[SCREENSHOT ANALYSIS]: {assistant_response}"
                self.text_thread.send_text(context_msg)
            
            logger.info("Image analysis completed successfully")
            
        except Exception as e:
            error_message = f"Error analyzing image: {str(e)}"
            logger.error(error_message)
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
                # Send the complete analysis and solution to the real-time model
                context_msg = f"[THINKING PROCESS RESULTS]:\n\nCONVERSATION ANALYSIS:\n{summary}\n\nDETAILED SOLUTION:\n{solution}"
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
                "content": "Analyze our conversation and create a BRIEF summary that includes: 1) The context of the interview 2) The main challenges/questions discussed 3) The key points of my answers 4) Areas for improvement. Be concise and focused."
            })
            
            # API call
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=summary_messages,
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
                    "content": "You are an expert job interview coach with extensive experience in technical and behavioral interviews. Your task is to provide focused, concise feedback and solutions."
                },
                {
                    "role": "user",
                    "content": f"Here is a summary of my interview:\n\n{summary}\n\nBased on this summary, provide me with a CONCISE solution that includes: 1) Brief feedback on my answers 2) Alternative solutions for key challenges 3) 1-2 practical tips to improve. Focus only on the most important points."
                }
            ]
            
            # API call
            response = client.chat.completions.create(
                model="o3-mini",
                messages=solution_messages,
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
            save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "saved_conversations")
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
    
    def _filter_response(self, text):
        """
        Disabled filter function to allow all messages.
        Always returns the original text without filtering.
        """
        # Still update timestamps to maintain tracking functionality
        current_time = datetime.now()
        self.last_response_time = current_time
        self.last_response_content = text
        
        # Always return the original text
        return text 