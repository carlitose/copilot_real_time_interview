#!/usr/bin/env python3
"""
Authentication utilities for Socket.IO connections.
"""
import os
import logging
from typing import Dict, Any, Optional

from flask import request, session

from intervista_assistant.models.supabase_integration import supabase_client

# Configure logging
logger = logging.getLogger(__name__)

def verify_auth_token(token) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase token.
    
    Args:
        token: Authentication token
        
    Returns:
        User data if valid, None otherwise
    """
    try:
        if not token:
            return None
            
        user_data = supabase_client.auth.get_user(token)
        if user_data and 'user' in user_data:
            return user_data['user']
    except Exception as e:
        logger.error(f"Token verification error: {e}")
    
    return None

def get_openai_api_key(user_id=None) -> Optional[str]:
    """
    Get the OpenAI API key to use.
    
    Args:
        user_id: User ID to get API key for
        
    Returns:
        API key if found, None otherwise
    """
    # First check if user has a stored API key
    if user_id and supabase_client.is_connected:
        try:
            profile = supabase_client.client.table("user_profiles").select("openai_api_key").eq("user_id", user_id).execute()
            if profile.data and profile.data[0].get("openai_api_key"):
                logger.info(f"Using user's custom OpenAI API key")
                return profile.data[0].get("openai_api_key")
        except Exception as e:
            logger.error(f"Error getting user API key: {e}")
    
    # Otherwise use the app's default API key
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        logger.info("Using default OpenAI API key")
        return api_key
    
    logger.error("No OpenAI API key found")
    return None

def authenticate_socket_connection():
    """
    Authenticate a Socket.IO connection.
    
    Returns:
        User ID if authenticated, None otherwise
    """
    # Check for authentication token
    auth_token = request.args.get('token')
    user = verify_auth_token(auth_token) if auth_token else None
    
    if user:
        # Store user in session
        session['user_id'] = user.get('id')
        logger.info(f"Authenticated connection for user: {user.get('email')}")
        return user.get('id')
    else:
        session['user_id'] = None
        logger.info("Anonymous connection")
        return None

def save_conversation_to_supabase(user_id, chat_history, metadata=None):
    """
    Save a conversation to Supabase.
    
    Args:
        user_id: User ID
        chat_history: List of messages
        metadata: Additional metadata
        
    Returns:
        Success flag
    """
    if not user_id or not chat_history:
        return False
    
    try:
        # Format conversation data
        conversation_data = {
            'messages': chat_history,
            'timestamp': metadata.get('timestamp') if metadata and 'timestamp' in metadata else None,
            'metadata': metadata or {}
        }
        
        # Save conversation
        result = supabase_client.save_conversation(user_id, conversation_data)
        
        if "error" in result:
            logger.error(f"Error saving conversation: {result['error']}")
            return False
            
        logger.info(f"Conversation saved for user: {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")
        return False 