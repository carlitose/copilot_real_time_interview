#!/usr/bin/env python3
"""
API routes for Intervista Assistant.
Defines all the Flask endpoints for the backend API.
"""
import os
import uuid
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, Response, stream_with_context

# Import from core modules
from intervista_assistant.core.utils import require_session, require_auth, active_sessions
from intervista_assistant.core.session_manager import SessionManager
from intervista_assistant.api.sse import session_sse_generator

# Logging configuration
logger = logging.getLogger(__name__)

def register_routes(app):
    """Register all API routes with the Flask app."""
    
    @app.route('/api/<path:path>', methods=['OPTIONS'])
    def handle_options(path):
        """Handle OPTIONS requests for all API endpoints."""
        response = jsonify({"success": True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
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
    @require_auth
    @require_session
    def start_session():
        """Starts a session with the specified session_id."""
        if request.method == 'OPTIONS':
            return jsonify({"success": True}), 200
            
        session_id = request.json.get('session_id')
        
        if not session_id or session_id not in active_sessions:
            return jsonify({
                "success": False,
                "error": "Session not found"
            }), 404
        
        session = active_sessions[session_id]
        success, error = session.start_session()
        
        if success:
            # Add a small delay to give the WebSocket time to connect
            # before returning the response
            import time
            max_wait = 3  # maximum seconds to wait
            wait_interval = 0.1  # check interval in seconds
            waited = 0
            
            # Wait for the WebSocket to actually connect
            while waited < max_wait:
                if session.text_thread and session.text_thread.connected:
                    logger.info(f"WebSocket connected after {waited:.1f} seconds")
                    break
                time.sleep(wait_interval)
                waited += wait_interval
                
            if not (session.text_thread and session.text_thread.connected):
                logger.warning(f"WebSocket connection timeout after {max_wait} seconds")
                # We continue anyway, the connection might establish later
            
            return jsonify({
                "success": True,
                "message": "Session started successfully",
                "websocket_connected": session.text_thread and session.text_thread.connected
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": error
            }), 500

    @app.route('/api/sessions/end', methods=['POST', 'OPTIONS'])
    @require_auth
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
        
        logger.info(f"Starting SSE stream for session {session_id}")
        
        # Set necessary CORS headers
        headers = {
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
            'Content-Type': 'text/event-stream',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Allow-Methods': 'GET'
        }
        
        return Response(
            stream_with_context(session_sse_generator(session_id)),
            mimetype='text/event-stream',
            headers=headers
        )

    @app.route('/api/sessions/text', methods=['POST'])
    @require_auth
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

    @app.route('/api/sessions/analyze-screenshot', methods=['POST'])
    @require_auth
    @require_session
    def analyze_screenshot():
        """Analyzes a screenshot captured by the frontend."""
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
        
        try:
            # Validate the base64 image data
            import base64
            base64.b64decode(image_data)
            
            session = active_sessions[session_id]
            logger.info(f"Processing screenshot for session {session_id} (size: {len(image_data) // 1024}KB)")
            
            # Add immediate feedback through the SSE channel
            session.handle_log("Screenshot received. Analyzing the image...")
            
            success, error = session.process_screenshot(image_data)
            
            if success:
                logger.info(f"Screenshot successfully processed for session {session_id}")
                return jsonify({
                    "success": True,
                    "message": "Screenshot analyzed successfully"
                }), 200
            else:
                logger.error(f"Error processing screenshot for session {session_id}: {error}")
                return jsonify({
                    "success": False,
                    "error": error
                }), 500
        except Exception as e:
            logger.error(f"Exception processing screenshot for session {session_id}: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Invalid image data: {str(e)}"
            }), 400

    @app.route('/api/sessions/think', methods=['POST'])
    @require_auth
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
    @require_auth
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
    @require_auth
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

    @app.route('/api/test-auth', methods=['GET', 'OPTIONS'])
    @require_auth
    def test_auth():
        """Test endpoint to verify authentication."""
        if request.method == 'OPTIONS':
            return jsonify({"success": True}), 200
            
        return jsonify({
            "success": True,
            "message": "Authentication successful",
            "user_id": request.user_id,
            "user_email": request.user_email
        }), 200 