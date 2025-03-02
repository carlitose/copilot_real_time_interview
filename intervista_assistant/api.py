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
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile
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
                    filename='api.log')
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

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        logger.info("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Remaining connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        logger.info(f"Broadcasting message to {len(self.active_connections)} clients")
        for connection in self.active_connections:
            await connection.send_text(message)

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
async def send_message(message_data: MessageList):
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
        return {"response": response.choices[0].message.content}
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-screenshot")
async def analyze_screenshot(file: UploadFile = File(...)):
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
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
        )
        
        logger.info("Received analysis from OpenAI")
        return {"analysis": response.choices[0].message.content}
    except Exception as e:
        logger.error(f"Error analyzing screenshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/think")
async def think(request: ThinkRequest):
    """Process advanced thinking request and return summary and solution."""
    try:
        logger.info(f"Received think request with {len(request.messages)} messages")
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        # Create think process with fallback
        if ThinkProcess is not None:
            try:
                think_process = ThinkProcess(client)
                summary = think_process.generate_summary(messages)
                solution = think_process.generate_solution(messages, summary)
                logger.info("Think process completed with ThinkProcess class")
            except Exception as tp_error:
                logger.error(f"Error with ThinkProcess: {tp_error}")
                raise
        else:
            # Fallback to simple completion if ThinkProcess not available
            logger.warning("ThinkProcess not available, using fallback")
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
        
        logger.info("Think process completed")
        return {"summary": summary, "solution": solution}
    except Exception as e:
        logger.error(f"Error in think process: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio using OpenAI's Whisper model."""
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
            
            logger.info(f"Audio transcribed: {transcript.text[:100]}...")
            return {"transcription": transcript.text}
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for real-time communication
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
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
                    
                    # Add system prompt if it's not included
                    if messages and messages[0]["role"] != "system" and system_prompt:
                        messages.insert(0, {
                            "role": "system",
                            "content": system_prompt["item"]["content"][0]["text"]
                        })
                    
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=messages,
                        temperature=0.7,
                    )
                    
                    response_content = response.choices[0].message.content
                    logger.info(f"Sending response via WebSocket: {response_content[:100]}...")
                    
                    await websocket.send_text(json.dumps({
                        "type": "response",
                        "content": response_content
                    }))
                elif message_data["type"] == "ping":
                    # Risponde a messaggi di ping per testing
                    logger.info("Received ping message, sending pong")
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": message_data.get("timestamp", ""),
                        "server_time": datetime.now().isoformat()
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