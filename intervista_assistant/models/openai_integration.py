#!/usr/bin/env python3
"""
OpenAI integration for Intervista Assistant.
Contains the WebRealtimeTextThread class for real-time communication with OpenAI.
"""
import logging

# Import the thread for real-time API communication with OpenAI
try:
    # Try to import as a module
    from intervista_assistant.web_realtime_text_thread import WebRealtimeTextThread
except ImportError:
    # Local import fallback
    from web_realtime_text_thread import WebRealtimeTextThread

# Logging configuration
logger = logging.getLogger(__name__)

# Note: We're importing the WebRealtimeTextThread class from the existing file
# rather than duplicating its code here. In a future refactoring, the actual
# implementation could be moved into this file. 