#!/usr/bin/env python3
"""
API server for Intervista Assistant.
Provides REST and WebSocket endpoints for the React/Next.js frontend.
"""

import os
import json
import logging
import asyncio
import base64
import tempfile
from typing import List, Optional, Dict, Any, Set
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# Import required modules from existing codebase (using absolute imports)
try:
    from intervista_assistant.utils.think_process import ThinkProcess
    from intervista_assistant.utils.screenshot_utils import ScreenshotManager
except ImportError:
    # Fallback to direct import if package structure is not detected
    try:
        from utils.think_process import ThinkProcess 
        from utils.screenshot_utils import ScreenshotManager
    except ImportError:
        logging.warning("Could not import utility modules - some functionality may be limited")
        ThinkProcess = None
        ScreenshotManager = None

# Logging configuration
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

# Configura anche il logging sulla console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    logger.error("OpenAI API Key not found. Set the environment variable OPENAI_API_KEY.")
    raise ValueError("OpenAI API Key not found")

# Initialize OpenAI client
client = OpenAI(api_key=api_key)

# Initialize FastAPI
app = FastAPI(title="Intervista Assistant API")

# Add CORS middleware to allow requests from the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Update with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ScreenshotManager
screenshot_manager = ScreenshotManager()

# Pydantic models for API requests/responses
class Message(BaseModel):
    role: str
    content: str

class MessageList(BaseModel):
    messages: List[Message]

class ThinkRequest(BaseModel):
    messages: List[Message]

class ThinkResponse(BaseModel):
    summary: str
    solution: str

class ScreenshotRequest(BaseModel):
    monitor_index: Optional[int] = None

class MonitorInfo(BaseModel):
    index: int
    width: int
    height: int
    name: str

class MonitorList(BaseModel):
    monitors: List[MonitorInfo]

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.session_connections: Dict[str, Set[WebSocket]] = {}
        logger.info("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, session_id: str = "default"):
        await websocket.accept()
        self.active_connections.append(websocket)
        
        # Add to session-specific connections
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(websocket)
        
        logger.info(f"WebSocket client connected to session {session_id}. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, session_id: str = "default"):
        self.active_connections.remove(websocket)
        
        # Remove from session-specific connections
        if session_id in self.session_connections and websocket in self.session_connections[session_id]:
            self.session_connections[session_id].remove(websocket)
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]
        
        logger.info(f"WebSocket client disconnected from session {session_id}. Remaining connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        logger.info(f"Broadcasting message to {len(self.active_connections)} clients")
        for connection in self.active_connections:
            await connection.send_text(message)
    
    async def broadcast_to_session(self, message: str, session_id: str = "default"):
        if session_id in self.session_connections:
            connections = self.session_connections[session_id]
            logger.info(f"Broadcasting message to {len(connections)} clients in session {session_id}")
            for connection in connections:
                await connection.send_text(message)
        else:
            logger.warning(f"No connections found for session {session_id}")

manager = ConnectionManager()

# Load system prompt
def load_system_prompt():
    try:
        with open(os.path.join(os.path.dirname(__file__), "system_prompt.json"), "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading system prompt: {e}")
        return {"item": {"content": [{"text": "You are an AI assistant helping with a coding interview."}]}}

system_prompt = load_system_prompt()

# REST Endpoints
@app.post("/api/send-message")
async def send_message(message_data: MessageList, background_tasks: BackgroundTasks):
    """Process a text message and return the AI response."""
    try:
        logger.info(f"Received message request with {len(message_data.messages)} messages")
        messages = [{"role": msg.role, "content": msg.content} for msg in message_data.messages]
        
        # Add system prompt if it's not included
        if messages and messages[0]["role"] != "system" and system_prompt:
            messages.insert(0, {
                "role": "system",
                "content": system_prompt["item"]["content"][0]["text"]
            })
        
        logger.info(f"Sending request to OpenAI with {len(messages)} messages")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
        )
        
        logger.info("Received response from OpenAI")
        
        # Broadcast the response to all connected WebSocket clients
        response_content = response.choices[0].message.content
        current_time = datetime.now().strftime("%H:%M:%S")
        
        background_tasks.add_task(
            broadcast_response_to_websockets,
            f"Response at {current_time}\n\n{response_content}"
        )
        
        return {"response": response_content}
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def broadcast_response_to_websockets(response_content: str):
    """Broadcast response to all connected WebSocket clients."""
    try:
        await manager.broadcast(json.dumps({
            "type": "response",
            "content": response_content
        }))
    except Exception as e:
        logger.error(f"Error broadcasting response: {e}")

@app.get("/api/monitors")
async def get_monitors():
    """Get a list of available monitors for screenshot capture."""
    try:
        monitors = screenshot_manager.get_monitors()
        monitor_list = []
        
        for i, monitor in enumerate(monitors):
            monitor_list.append({
                "index": i,
                "width": monitor["width"],
                "height": monitor["height"],
                "name": f"Monitor {i+1}: {monitor['width']}x{monitor['height']}"
            })
        
        return {"monitors": monitor_list}
    except Exception as e:
        logger.error(f"Error getting monitors: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/take-screenshot")
async def take_screenshot(request: ScreenshotRequest, background_tasks: BackgroundTasks):
    """Take a screenshot and return the path to the saved file."""
    try:
        logger.info(f"Taking screenshot with monitor index: {request.monitor_index}")
        screenshot_path = screenshot_manager.take_screenshot(monitor_index=request.monitor_index)
        
        # Return the path to the screenshot
        return {"screenshot_path": str(screenshot_path)}
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-screenshot")
async def analyze_screenshot(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Analyze a screenshot and return the AI's observations."""
    try:
        logger.info(f"Received screenshot analysis request, filename: {file.filename}")
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode("utf-8")
        
        # Prepare messages with the image
        messages = []
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt["item"]["content"][0]["text"] + " Please analyze the following screenshot and describe what you see."
            })
        
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Please analyze this screenshot and describe what you see:"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })
        
        logger.info("Sending screenshot to OpenAI for analysis")
        
        # Broadcast a notification that analysis is in progress
        background_tasks.add_task(
            broadcast_response_to_websockets,
            "Analyzing screenshot... Please wait."
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
        )
        
        analysis_content = response.choices[0].message.content
        logger.info("Received analysis from OpenAI")
        
        # Broadcast the analysis to all connected WebSocket clients
        current_time = datetime.now().strftime("%H:%M:%S")
        background_tasks.add_task(
            broadcast_response_to_websockets,
            f"Screenshot Analysis at {current_time}\n\n{analysis_content}"
        )
        
        return {"analysis": analysis_content}
    except Exception as e:
        logger.error(f"Error analyzing screenshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/think")
async def think(request: ThinkRequest, background_tasks: BackgroundTasks):
    """Process advanced thinking request and return summary and solution."""
    try:
        logger.info(f"Received think request with {len(request.messages)} messages")
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        # Create think process with fallback
        if ThinkProcess is not None:
            try:
                think_process = ThinkProcess(client)
                
                # Start the thinking process in the background
                background_tasks.add_task(
                    process_thinking_request,
                    think_process,
                    messages
                )
                
                return {"status": "Thinking process started in background"}
            except Exception as tp_error:
                logger.error(f"Error with ThinkProcess: {tp_error}")
                raise
        else:
            # Fallback to simple completion if ThinkProcess not available
            logger.warning("ThinkProcess not available, using fallback")
            
            # Start the fallback thinking process in the background
            background_tasks.add_task(
                process_thinking_fallback,
                messages
            )
            
            return {"status": "Thinking process started in background (fallback mode)"}
    except Exception as e:
        logger.error(f"Error in think process: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_thinking_request(think_process: ThinkProcess, messages: List[Dict[str, Any]]):
    """Process a thinking request in the background."""
    try:
        # Generate summary
        logger.info("Generating summary with GPT-4o-mini")
        summary = think_process.summarize_conversation(messages)
        
        # Broadcast the summary to all connected WebSocket clients
        await manager.broadcast(json.dumps({
            "type": "response",
            "content": "**🧠 CONVERSATION SUMMARY (GPT-4o-mini):**\n\n" + summary
        }))
        
        # Generate solution
        logger.info("Generating solution with o1-preview")
        solution = think_process.deep_thinking(summary)
        
        # Broadcast the solution to all connected WebSocket clients
        await manager.broadcast(json.dumps({
            "type": "response",
            "content": "**🚀 IN-DEPTH ANALYSIS AND SOLUTION (o1-preview):**\n\n" + solution
        }))
        
        logger.info("Think process completed")
    except Exception as e:
        logger.error(f"Error in background thinking process: {e}")
        await manager.broadcast(json.dumps({
            "type": "error",
            "content": f"Error in thinking process: {str(e)}"
        }))

async def process_thinking_fallback(messages: List[Dict[str, Any]]):
    """Process a thinking request using fallback method."""
    try:
        # Generate summary
        summary_messages = messages.copy()
        summary_messages.append({
            "role": "user", 
            "content": "Please summarize our conversation so far in 2-3 sentences."
        })
        
        logger.info("Generating summary with OpenAI fallback")
        summary_response = client.chat.completions.create(
            model="gpt-4o",
            messages=summary_messages,
            temperature=0.7,
        )
        summary = summary_response.choices[0].message.content
        
        # Broadcast the summary to all connected WebSocket clients
        await manager.broadcast(json.dumps({
            "type": "response",
            "content": "**🧠 CONVERSATION SUMMARY:**\n\n" + summary
        }))
        
        # Generate solution
        solution_messages = messages.copy()
        solution_messages.append({
            "role": "user",
            "content": f"Based on our conversation and this summary: '{summary}', please provide a detailed solution or answer."
        })
        
        logger.info("Generating solution with OpenAI fallback")
        solution_response = client.chat.completions.create(
            model="gpt-4o",
            messages=solution_messages,
            temperature=0.7,
        )
        solution = solution_response.choices[0].message.content
        
        # Broadcast the solution to all connected WebSocket clients
        await manager.broadcast(json.dumps({
            "type": "response",
            "content": "**🚀 IN-DEPTH ANALYSIS AND SOLUTION:**\n\n" + solution
        }))
        
        logger.info("Fallback think process completed")
    except Exception as e:
        logger.error(f"Error in fallback thinking process: {e}")
        await manager.broadcast(json.dumps({
            "type": "error",
            "content": f"Error in thinking process: {str(e)}"
        }))

@app.post("/api/transcribe-audio")
async def transcribe_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Transcribe audio using OpenAI's Whisper model and process the transcription."""
    try:
        logger.info(f"Received audio transcription request, filename: {file.filename}")
        contents = await file.read()
        
        # Salva temporaneamente il file
        temp_file_path = f"/tmp/{file.filename}"
        with open(temp_file_path, "wb") as f:
            f.write(contents)
        
        # Transcribe using OpenAI Whisper
        logger.info("Transcribing audio with OpenAI Whisper")
        try:
            with open(temp_file_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            
            transcription_text = transcript.text
            logger.info(f"Audio transcribed: {transcription_text[:100]}...")
            
            # Broadcast the transcription to all connected WebSocket clients
            current_time = datetime.now().strftime("%H:%M:%S")
            await manager.broadcast(json.dumps({
                "type": "transcription",
                "content": f"[Audio processed at {current_time}]\n{transcription_text}"
            }))
            
            # Process the transcription with OpenAI to get a response
            background_tasks.add_task(
                process_transcription,
                transcription_text
            )
            
            return {"transcription": transcription_text}
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def process_transcription(transcription_text: str):
    """Process a transcription and generate a response."""
    try:
        # Prepare messages for OpenAI
        messages = []
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt["item"]["content"][0]["text"]
            })
        
        messages.append({
            "role": "user",
            "content": transcription_text
        })
        
        logger.info(f"Processing transcription with OpenAI: {transcription_text[:100]}...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
        )
        
        response_content = response.choices[0].message.content
        logger.info(f"Received response from OpenAI: {response_content[:100]}...")
        
        # Broadcast the response to all connected WebSocket clients
        current_time = datetime.now().strftime("%H:%M:%S")
        await manager.broadcast(json.dumps({
            "type": "response",
            "content": f"Response at {current_time}\n\n{response_content}"
        }))
    except Exception as e:
        logger.error(f"Error processing transcription: {e}")
        await manager.broadcast(json.dumps({
            "type": "error",
            "content": f"Error processing transcription: {str(e)}"
        }))

@app.post("/api/send-text")
async def send_text(message: Message, background_tasks: BackgroundTasks):
    """Send a text message directly and get a response."""
    try:
        logger.info(f"Received text message: {message.content[:100]}...")
        
        # Broadcast the message to all connected WebSocket clients
        current_time = datetime.now().strftime("%H:%M:%S")
        await manager.broadcast(json.dumps({
            "type": "transcription",
            "content": f"[Text message sent at {current_time}]\n{message.content}"
        }))
        
        # Process the message with OpenAI to get a response
        background_tasks.add_task(
            process_transcription,
            message.content
        )
        
        return {"status": "Message received and processing started"}
    except Exception as e:
        logger.error(f"Error sending text message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint di test per verificare la comunicazione HTTP
@app.post("/api/ping-test")
async def ping_test(request: Request):
    """Test endpoint to verify HTTP communication."""
    logger.info("Received ping-test request")
    try:
        body = await request.json()
        message = body.get("message", "No message provided")
        logger.info(f"Ping message: {message}")
        return {
            "status": "success",
            "message": f"Received: {message}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in ping-test: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for real-time communication
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info(f"WebSocket connection request from: {websocket.client.host}:{websocket.client.port}")
    logger.info(f"WebSocket headers: {websocket.headers}")
    
    await manager.connect(websocket)
    logger.info(f"WebSocket connection accepted. Active connections: {len(manager.active_connections)}")
    
    # Send an initial welcome message to confirm the connection is working
    try:
        welcome_message = {
            "type": "system",
            "content": "WebSocket connection established successfully with the server",
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_text(json.dumps(welcome_message))
        logger.info("Sent welcome message to new WebSocket client")
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
    
    try:
        logger.info("New WebSocket connection established")
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received WebSocket message: {data[:100]}...")
            
            try:
                message_data = json.loads(data)
                
                # Handle different message types
                if message_data["type"] == "text":
                    messages = message_data["messages"]
                    logger.info(f"Processing text message with {len(messages)} messages")
                    
                    # Log dei messaggi ricevuti per debug
                    for idx, msg in enumerate(messages):
                        role = msg.get('role', 'unknown')
                        content_preview = msg.get('content', '')[:50]
                        logger.info(f"Message {idx}: role={role}, content preview: {content_preview}...")
                    
                    try:
                        # Add system prompt if it's not included
                        if messages and messages[0]["role"] != "system" and system_prompt:
                            messages.insert(0, {
                                "role": "system",
                                "content": system_prompt["item"]["content"][0]["text"]
                            })
                        
                        logger.info("Calling OpenAI API for response")
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=messages,
                            temperature=0.7,
                        )
                        
                        response_content = response.choices[0].message.content
                        logger.info(f"Sending response via WebSocket: {response_content[:100]}...")
                        
                        current_time = datetime.now().strftime("%H:%M:%S")
                        formatted_response = f"Response at {current_time}\n\n{response_content}"
                        
                        response_data = {
                            "type": "response",
                            "content": formatted_response
                        }
                        
                        logger.info(f"Sending response data: {str(response_data)[:200]}...")
                        await websocket.send_text(json.dumps(response_data))
                        logger.info("Response sent successfully")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        error_response = {
                            "type": "error",
                            "content": f"Error processing your request: {str(e)}"
                        }
                        await websocket.send_text(json.dumps(error_response))
                elif message_data["type"] == "audio":
                    # Gestione dello streaming audio
                    logger.info("Received audio stream chunk via WebSocket")
                    
                    try:
                        # Estrai l'audio base64 dal messaggio
                        base64_audio = message_data.get("audio", "")
                        if not base64_audio:
                            logger.error("Audio stream chunk is empty")
                            continue
                            
                        # Decodifica l'audio da base64 a bytes
                        audio_bytes = base64.b64decode(base64_audio)
                        logger.info(f"Decoded audio chunk, size: {len(audio_bytes)} bytes")
                        
                        # Salva temporaneamente il file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        
                        # Utilizza .wav che è un formato supportato esplicitamente da OpenAI
                        temp_file_path = f"/tmp/audio_chunk_{timestamp}.wav"
                        
                        with open(temp_file_path, "wb") as f:
                            f.write(audio_bytes)
                        
                        # Transcribe usando OpenAI Whisper
                        try:
                            with open(temp_file_path, "rb") as audio_file:
                                transcript = client.audio.transcriptions.create(
                                    model="whisper-1",
                                    file=audio_file
                                )
                            
                            transcription_text = transcript.text
                            if transcription_text.strip():  # Invia solo se c'è testo
                                logger.info(f"Audio chunk transcribed: {transcription_text}")
                                
                                # Broadcast della trascrizione a tutti i client WebSocket
                                current_time = datetime.now().strftime("%H:%M:%S")
                                await manager.broadcast(json.dumps({
                                    "type": "transcription",
                                    "content": f"{transcription_text}"
                                }))
                                
                                # Avvia l'elaborazione della trascrizione in background
                                # per ottenere una risposta dal modello AI
                                asyncio.create_task(process_transcription(transcription_text))
                            else:
                                logger.info("Audio chunk transcription is empty, skipping")
                        except Exception as e:
                            logger.error(f"Error transcribing audio chunk: {e}")
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "content": f"Error transcribing audio: {str(e)}"
                            }))
                        finally:
                            # Pulizia file temporaneo
                            if os.path.exists(temp_file_path):
                                os.remove(temp_file_path)
                    except Exception as e:
                        logger.error(f"Error processing audio stream: {e}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "content": f"Error processing audio stream: {str(e)}"
                        }))
                elif message_data["type"] == "ping":
                    # Risponde a messaggi di ping per testing
                    logger.info("Received ping message, sending pong")
                    
                    # Log more details about the ping message
                    debug_info = message_data.get("debug", {})
                    logger.info(f"Ping debug info: {debug_info}")
                    
                    # Send a more detailed response
                    response_data = {
                        "type": "pong",
                        "timestamp": message_data.get("timestamp", ""),
                        "server_time": datetime.now().isoformat(),
                        "message": "Pong response from server",
                        "server_info": {
                            "connections": len(manager.active_connections),
                            "api_version": "1.0.0"
                        }
                    }
                    
                    logger.info(f"Sending pong response: {response_data}")
                    await websocket.send_text(json.dumps(response_data))
                elif message_data["type"] == "think":
                    # Process thinking request
                    logger.info("Received thinking request via WebSocket")
                    messages = message_data.get("messages", [])
                    
                    if ThinkProcess is not None:
                        think_process = ThinkProcess(client)
                        
                        # Generate summary
                        logger.info("Generating summary with GPT-4o-mini")
                        summary = think_process.summarize_conversation(messages)
                        
                        # Send summary to client
                        await websocket.send_text(json.dumps({
                            "type": "response",
                            "content": "**🧠 CONVERSATION SUMMARY (GPT-4o-mini):**\n\n" + summary
                        }))
                        
                        # Generate solution
                        logger.info("Generating solution with o1-preview")
                        solution = think_process.deep_thinking(summary)
                        
                        # Send solution to client
                        await websocket.send_text(json.dumps({
                            "type": "response",
                            "content": "**🚀 IN-DEPTH ANALYSIS AND SOLUTION (o1-preview):**\n\n" + solution
                        }))
                    else:
                        # Fallback
                        logger.warning("ThinkProcess not available, using fallback")
                        
                        # Generate summary
                        summary_messages = messages.copy()
                        summary_messages.append({
                            "role": "user", 
                            "content": "Please summarize our conversation so far in 2-3 sentences."
                        })
                        
                        summary_response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=summary_messages,
                            temperature=0.7,
                        )
                        summary = summary_response.choices[0].message.content
                        
                        # Send summary to client
                        await websocket.send_text(json.dumps({
                            "type": "response",
                            "content": "**🧠 CONVERSATION SUMMARY:**\n\n" + summary
                        }))
                        
                        # Generate solution
                        solution_messages = messages.copy()
                        solution_messages.append({
                            "role": "user",
                            "content": f"Based on our conversation and this summary: '{summary}', please provide a detailed solution or answer."
                        })
                        
                        solution_response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=solution_messages,
                            temperature=0.7,
                        )
                        solution = solution_response.choices[0].message.content
                        
                        # Send solution to client
                        await websocket.send_text(json.dumps({
                            "type": "response",
                            "content": "**🚀 IN-DEPTH ANALYSIS AND SOLUTION:**\n\n" + solution
                        }))
                else:
                    logger.warning(f"Unknown message type: {message_data.get('type')}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "content": f"Unknown message type: {message_data.get('type')}"
                    }))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": "Invalid JSON format"
                }))
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "content": str(e)
            }))
        except:
            logger.error("Could not send error message to client, connection might be closed")
        finally:
            manager.disconnect(websocket)

# Root route for checking API status
@app.get("/")
async def root():
    return {"status": "API is running", "version": "1.0.0"}

# Launch the API with Uvicorn when run directly
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting API server...")
    uvicorn.run("intervista_assistant.api:app", host="0.0.0.0", port=8000, reload=True) 