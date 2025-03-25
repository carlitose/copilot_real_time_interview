#!/usr/bin/env python3
"""
Server-Sent Events (SSE) functionality for Intervista Assistant.
Handles real-time streaming of updates to the frontend.
"""
import json
import time
import logging
from datetime import datetime

from intervista_assistant.core.utils import active_sessions, format_sse

# Logging configuration
logger = logging.getLogger(__name__)

def session_sse_generator(session_id):
    """
    Generator for SSE events from a session.
    This stays open and continues to yield events.
    """
    session = active_sessions.get(session_id)
    
    if not session:
        logger.error(f"SSE generator: Session {session_id} not found")
        yield format_sse(json.dumps({
            "type": "error",
            "message": "Session not found",
            "session_id": session_id
        }))
        return
    
    # Send initial connection status
    session.handle_connection_status(True)
    
    # Keep track of the last update processed
    last_update_index = 0
    
    try:
        # Initial heartbeat
        yield format_sse(json.dumps({
            "type": "heartbeat",
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id
        }))
        
        # Main loop for sending updates
        while session_id in active_sessions:
            # Get all updates of any type
            all_updates = session.get_updates()
            new_updates = all_updates[last_update_index:]
            
            # Send any new updates
            for update in new_updates:
                # Convert the update to an SSE event
                event_data = {}
                
                if "text" in update:
                    if "transcription" in update["type"]:
                        event_data = {
                            "type": "transcription",
                            "text": update["text"],
                            "session_id": session_id
                        }
                    elif "response" in update["type"]:
                        final = update.get("final", True)  # Default to True for backward compatibility
                        event_data = {
                            "type": "response",
                            "text": update["text"],
                            "session_id": session_id,
                            "final": final
                        }
                elif "message" in update:
                    event_data = {
                        "type": "error",
                        "message": update["message"],
                        "session_id": session_id
                    }
                elif "connected" in update:
                    event_data = {
                        "type": "connection",
                        "connected": update["connected"],
                        "session_id": session_id
                    }
                
                if event_data:
                    # Send debug log for response events
                    if event_data.get("type") == "response":
                        logger.info(f"Sending {event_data.get('final', False)} response to client: {event_data.get('text', '')[:50]}...")
                    
                    yield format_sse(json.dumps(event_data))
            
            # Update the last update index
            last_update_index = len(all_updates)
            
            # Send a heartbeat every 5 seconds to keep the connection alive
            yield format_sse(json.dumps({
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id
            }))
            
            # Sleep to prevent CPU overuse
            time.sleep(1)
            
    except GeneratorExit:
        logger.info(f"SSE connection closed for session {session_id}")
        # Notify the session that the connection is closed
        if session_id in active_sessions:
            active_sessions[session_id].handle_connection_status(False)
    except Exception as e:
        logger.error(f"Error in SSE generator for session {session_id}: {str(e)}")
        yield format_sse(json.dumps({
            "type": "error",
            "message": f"Server error: {str(e)}",
            "session_id": session_id
        }))
    finally:
        logger.info(f"SSE generator exiting for session {session_id}") 