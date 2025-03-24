/**
 * API client for REST calls to the backend
 */

import { supabase } from './supabase';

// Base URL for the API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

// Interfaces for API responses
export interface ApiResponse {
  success: boolean;
  message?: string;
}

export interface SessionResponse extends ApiResponse {
  session_id: string;
}

export interface SessionStatusResponse extends ApiResponse {
  status: {
    is_active: boolean;
    start_time: string;
    last_activity: string;
  };
}

export interface ConversationResponse extends ApiResponse {
  conversation: {
    messages: Message[];
    metadata: {
      session_id: string;
      created_at: string;
      updated_at: string;
    };
  };
}

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'log';
  content: string;
}

/**
 * Gets the authentication headers with the Supabase token
 * @returns Promise with headers object including authorization token
 */
async function getAuthHeaders(): Promise<HeadersInit> {
  const { data: { session } } = await supabase.auth.getSession();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  
  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`;
  }
  
  return headers;
}

// API client
const apiClient = {
  /**
   * Creates a new session
   * @returns Promise with the ID of the created session
   */
  async createSession(): Promise<string> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({}),
      });
      
      if (!response.ok) {
        throw new Error(`Error creating session: ${response.status}`);
      }
      
      const data = await response.json() as SessionResponse;
      return data.session_id;
    } catch (error) {
      console.error('Error creating session:', error);
      throw error;
    }
  },
  
  /**
   * Starts an existing session
   * @param sessionId ID of the session to start
   * @returns Promise with the result of the operation
   */
  async startSession(sessionId: string): Promise<boolean> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/start`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ session_id: sessionId }),
      });
      
      if (!response.ok) {
        throw new Error(`Error starting session: ${response.status}`);
      }
      
      const data = await response.json() as ApiResponse;
      return data.success;
    } catch (error) {
      console.error('Error starting session:', error);
      return false;
    }
  },
  
  /**
   * Ends a session
   * @param sessionId ID of the session to end
   * @returns Promise with the result of the operation
   */
  async endSession(sessionId: string): Promise<boolean> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/end`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ session_id: sessionId }),
      });
      
      if (!response.ok) {
        throw new Error(`Error ending session: ${response.status}`);
      }
      
      const data = await response.json() as ApiResponse;
      return data.success;
    } catch (error) {
      console.error('Error ending session:', error);
      return false;
    }
  },
  
  /**
   * Sends a text message
   * @param sessionId ID of the session
   * @param text Text of the message
   * @returns Promise with the result of the operation
   */
  async sendTextMessage(sessionId: string, text: string): Promise<boolean> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/text`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          session_id: sessionId,
          text: text 
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Error sending message: ${response.status}`);
      }
      
      const data = await response.json() as ApiResponse;
      return data.success;
    } catch (error) {
      console.error('Error sending message:', error);
      return false;
    }
  },
  
  /**
   * Captures and analyzes a screenshot
   * @param sessionId ID of the session
   * @param screenId Identifier of the screen
   * @returns Promise with the result of the operation
   */
  async takeScreenshot(sessionId: string, screenId: string): Promise<boolean> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/screenshot`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          session_id: sessionId,
          monitor_index: parseInt(screenId, 10)
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Error capturing screenshot: ${response.status}`);
      }
      
      const data = await response.json() as ApiResponse;
      return data.success;
    } catch (error) {
      console.error('Error capturing screenshot:', error);
      return false;
    }
  },
  
  /**
   * Sends a captured screenshot to the backend for analysis
   * @param sessionId ID of the session
   * @param imageData Base64 encoded image data
   * @returns Promise with the result of the operation
   */
  async sendScreenshot(sessionId: string, imageData: string): Promise<boolean> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/analyze-screenshot`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          session_id: sessionId,
          image_data: imageData
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Error sending screenshot: ${response.status}`);
      }
      
      const data = await response.json() as ApiResponse;
      return data.success;
    } catch (error) {
      console.error('Error sending screenshot:', error);
      return false;
    }
  },
  
  /**
   * Starts the "thinking" process
   * @param sessionId ID of the session
   * @returns Promise with the result of the operation
   */
  async startThinkProcess(sessionId: string): Promise<boolean> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/think`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ session_id: sessionId }),
      });
      
      if (!response.ok) {
        throw new Error(`Error starting thinking process: ${response.status}`);
      }
      
      const data = await response.json() as ApiResponse;
      return data.success;
    } catch (error) {
      console.error('Error starting thinking process:', error);
      return false;
    }
  },
  
  /**
   * Saves the current conversation
   * @param sessionId ID of the session
   * @returns Promise with the saved conversation
   */
  async saveConversation(sessionId: string): Promise<any> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/save`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ session_id: sessionId }),
      });
      
      if (!response.ok) {
        throw new Error(`Error saving conversation: ${response.status}`);
      }
      
      const data = await response.json() as ConversationResponse;
      return data.conversation;
    } catch (error) {
      console.error('Error saving conversation:', error);
      return null;
    }
  },
  
  /**
   * Gets the current status of a session
   * @param sessionId ID of the session
   * @returns Promise with the session status
   */
  async getSessionStatus(sessionId: string): Promise<SessionStatusResponse | null> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/status?session_id=${sessionId}`, {
        method: 'GET',
        headers,
      });
      
      if (!response.ok) {
        throw new Error(`Error retrieving session status: ${response.status}`);
      }
      
      const data = await response.json() as SessionStatusResponse;
      return data;
    } catch (error) {
      console.error('Error retrieving session status:', error);
      return null;
    }
  }
};

export default apiClient; 