#!/bin/bash

# Kill any previous processes on the requested ports
echo "Checking and cleaning up existing processes..."
if lsof -i:3000 -t &> /dev/null; then
  echo "Terminating processes on port 3000..."
  kill $(lsof -i:3000 -t) 2>/dev/null || true
  sleep 1
fi

if lsof -i:8000 -t &> /dev/null; then
  echo "Terminating processes on port 8000..."
  kill $(lsof -i:8000 -t) 2>/dev/null || true
  sleep 1
fi

# Determine the path of the current directory (where the script is located)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/intervista_assistant"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Check that the directories exist
if [ ! -d "$BACKEND_DIR" ]; then
  echo "Backend directory not found: $BACKEND_DIR"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "Frontend directory not found: $FRONTEND_DIR"
  exit 1
fi

# Start the backend
echo "Starting the backend API..."
cd "$BACKEND_DIR" 
# Set PYTHONPATH to include the current directory
export PYTHONPATH="$SCRIPT_DIR:$BACKEND_DIR:$PYTHONPATH"
python api_launcher.py &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Wait for the backend to be ready
echo "Waiting for the backend to be ready..."
sleep 5

# Start the frontend
echo "Starting the frontend (Next.js)..."
cd "$FRONTEND_DIR" 
npm run dev &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

# Function to terminate all processes
cleanup() {
  echo 'Closing processes...'
  # Terminate all child processes
  pkill -P $$ || true
  # Explicitly terminate known processes
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  exit 0
}

# Handle shutdown with Ctrl+C and other signals
trap cleanup INT TERM

# Keep the script running
echo "The application is running. Press Ctrl+C to terminate."
wait 