"""
Intervista Assistant - A real-time interview assistant.

This package provides tools for helping candidates during job interviews,
including real-time transcription, analysis, and advice.
"""

__version__ = '1.0.0'

# Import main components for easier access
from intervista_assistant.flask_app import create_app
from intervista_assistant.core.session_manager import SessionManager
from intervista_assistant.core.utils import active_sessions

"""
Package for the Intervista Assistant application.
""" 