# Intervista Assistant Backend

Backend service for Intervista Assistant, which provides REST APIs and WebSocket support for real-time assistance during interviews.

## Structure

- `flask_app.py`: Main Flask application
- `api_launcher.py`: Script to launch the API server
- `web_realtime_text_thread.py`: Module for managing real-time text via WebSocket
- `api/`: Folder containing API routes and Socket.IO handlers
- `core/`: Core functionalities of the backend
- `models/`: Data models
- `utils/`: Various utilities

## Requirements

- Python 3.8+
- Flask, Flask-SocketIO
- PyAudio
- OpenAI

## Starting

To start the backend server: