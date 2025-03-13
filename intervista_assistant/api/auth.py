#!/usr/bin/env python3
"""
Authentication and user management for the Intervista Assistant API.
Uses Supabase for authentication and user data storage.
"""
import os
import json
import logging
import time
from functools import wraps
from typing import Dict, Any, Optional, Callable

from flask import request, jsonify, g, current_app
from werkzeug.local import LocalProxy

from intervista_assistant.models.supabase_integration import supabase_client

# Configure logging
logger = logging.getLogger(__name__)

# Local proxy to access the current user
current_user = LocalProxy(lambda: getattr(g, 'user', None))

def authenticate_request():
    """
    Authenticate the request using the Authorization header.
    
    Sets g.user if authentication is successful.
    """
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.split(' ')[1]
    if not token:
        return None
    
    try:
        # Validate token with Supabase
        user_data = supabase_client.auth.get_user(token)
        if user_data and 'user' in user_data:
            g.user = user_data['user']
            return user_data['user']
    except Exception as e:
        logger.error(f"Authentication error: {e}")
    
    return None

def login_required(f: Callable) -> Callable:
    """
    Decorator to require authentication for API endpoints.
    
    Args:
        f: The function to decorate
        
    Returns:
        Decorated function
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = authenticate_request()
        if not user:
            return jsonify({
                'success': False,
                'error': 'Authentication required'
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def optional_auth(f: Callable) -> Callable:
    """
    Decorator to optionally authenticate a request.
    
    Sets g.user if authenticated but doesn't fail if not.
    
    Args:
        f: The function to decorate
        
    Returns:
        Decorated function
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        authenticate_request()
        return f(*args, **kwargs)
    return decorated_function

class AuthController:
    """
    Controller for authentication-related API endpoints.
    """
    
    @staticmethod
    def register(email: str, password: str) -> Dict[str, Any]:
        """
        Register a new user.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Response with status and user data
        """
        try:
            response = supabase_client.signup(email, password)
            
            if "error" in response:
                return {
                    "success": False,
                    "error": response["error"]
                }
            
            return {
                "success": True,
                "data": {
                    "user": response.get("user", {}),
                    "session": response.get("session", {})
                }
            }
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def login(email: str, password: str) -> Dict[str, Any]:
        """
        Log in a user.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Response with status and session data
        """
        try:
            response = supabase_client.login(email, password)
            
            if "error" in response:
                return {
                    "success": False,
                    "error": response["error"]
                }
            
            return {
                "success": True,
                "data": {
                    "user": response.get("user", {}),
                    "session": response.get("session", {}),
                    "access_token": response.get("session", {}).get("access_token"),
                    "refresh_token": response.get("session", {}).get("refresh_token")
                }
            }
        except Exception as e:
            logger.error(f"Login error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def update_api_key(user_id: str, api_key: str) -> Dict[str, Any]:
        """
        Update the OpenAI API key for a user.
        
        Args:
            user_id: User ID
            api_key: OpenAI API key
            
        Returns:
            Response with status
        """
        try:
            response = supabase_client.update_openai_api_key(user_id, api_key)
            
            if "error" in response:
                return {
                    "success": False,
                    "error": response["error"]
                }
            
            return {
                "success": True,
                "data": response.get("data", {})
            }
        except Exception as e:
            logger.error(f"API key update error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def get_user_profile(user_id: str) -> Dict[str, Any]:
        """
        Get user profile data.
        
        Args:
            user_id: User ID
            
        Returns:
            Response with user profile data
        """
        try:
            if not supabase_client.is_connected:
                return {
                    "success": False,
                    "error": "Database connection not available"
                }
            
            profile = supabase_client.client.table("user_profiles").select("*").eq("user_id", user_id).execute()
            
            if not profile.data:
                return {
                    "success": True,
                    "data": None  # No profile exists yet
                }
            
            return {
                "success": True,
                "data": profile.data[0]
            }
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def save_conversation(user_id: str, conversation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save a conversation to the user's history.
        
        Args:
            user_id: User ID
            conversation_data: Conversation data
            
        Returns:
            Response with status
        """
        try:
            response = supabase_client.save_conversation(user_id, conversation_data)
            
            if "error" in response:
                return {
                    "success": False,
                    "error": response["error"]
                }
            
            return {
                "success": True,
                "data": response.get("data", {})
            }
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def get_conversations(user_id: str) -> Dict[str, Any]:
        """
        Get all conversations for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Response with list of conversations
        """
        try:
            conversations = supabase_client.get_conversations(user_id)
            
            return {
                "success": True,
                "data": conversations
            }
        except Exception as e:
            logger.error(f"Error getting conversations: {e}")
            return {
                "success": False,
                "error": str(e)
            } 