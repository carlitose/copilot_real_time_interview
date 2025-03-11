/**
 * Module for managing event streams from the server (SSE)
 */
import { useEffect, useRef } from 'react';

// Base URL for the API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

// Update types
export interface TranscriptionUpdate {
  type: 'transcription';
  text: string;
  session_id: string;
}

export interface ResponseUpdate {
  type: 'response';
  text: string;
  session_id: string;
  final: boolean;
}

export interface ErrorUpdate {
  type: 'error';
  message: string;
  session_id: string;
}

export interface ConnectionUpdate {
  type: 'connection';
  connected: boolean;
  session_id: string;
}

// Generic update type
export type Update = TranscriptionUpdate | ResponseUpdate | ErrorUpdate | ConnectionUpdate;

// Call Event callbacks
export interface StreamCallbacks {
  onTranscription?: (update: TranscriptionUpdate) => void;
  onResponse?: (update: ResponseUpdate) => void;
  onError?: (update: ErrorUpdate) => void;
  onConnectionError?: (error: Event) => void;
  onConnectionStatus?: (connected: boolean) => void;
}

/**
 * Manages the SSE connection with the server
 */
export interface StreamControl {
  cleanup: () => void;
}

/**
 * Class that manages the EventSource connection
 */
class EventStreamManager {
  private eventSource: EventSource | null = null;
  private sessionId: string;
  private callbacks: StreamCallbacks;

  constructor(sessionId: string, callbacks: StreamCallbacks) {
    this.sessionId = sessionId;
    this.callbacks = callbacks;
  }

  /**
   * Starts managing events
   */
  connect(): void {
    if (!this.sessionId) return;
    
    // Close any existing event sources
    this.disconnect();

    console.log(`[EventStream] Connecting to SSE endpoint for session ${this.sessionId}`);
    
    // Create a new EventSource for SSE events
    this.eventSource = new EventSource(`${API_BASE_URL}/sessions/stream?session_id=${this.sessionId}`);
    
    // Generic handler for messages
    this.eventSource.onmessage = (event) => {
      console.log(`[EventStream] Raw event received: ${event.data}`);
      
      try {
        const data = JSON.parse(event.data);
        
        // Check that there is a defined type
        if (!data || typeof data !== 'object' || !('type' in data)) {
          console.warn('[EventStream] Received data without type property:', data);
          return;
        }
        
        console.log(`[EventStream] Parsed event type: ${data.type}`);
        
        // Distribute messages based on type
        switch (data.type) {
          case 'transcription':
            console.log(`[EventStream] Transcription received: ${(data as TranscriptionUpdate).text.substring(0, 30)}...`);
            this.callbacks.onTranscription?.(data as TranscriptionUpdate);
            break;
          case 'response':
            console.log(`[EventStream] Response received: ${(data as ResponseUpdate).text.substring(0, 30)}...`);
            this.callbacks.onResponse?.(data as ResponseUpdate);
            break;
          case 'error':
            console.log(`[EventStream] Error received: ${(data as ErrorUpdate).message}`);
            this.callbacks.onError?.(data as ErrorUpdate);
            break;
          case 'connection':
            console.log(`[EventStream] Connection status: ${(data as ConnectionUpdate).connected ? 'connected' : 'disconnected'}`);
            this.callbacks.onConnectionStatus?.((data as ConnectionUpdate).connected);
            break;
          default:
            console.log(`[EventStream] Unknown event type: ${data.type}`);
        }
      } catch (error) {
        console.error('[EventStream] Error parsing SSE message:', error);
        console.error('[EventStream] Raw message data:', event.data);
      }
    };
    
    // Error handling
    this.eventSource.onerror = (error) => {
      console.error('[EventStream] SSE connection error:', error);
      if (this.callbacks.onConnectionError) {
        this.callbacks.onConnectionError(error);
      }
    };
    
    // Handling the open connection
    this.eventSource.onopen = () => {
      console.log('[EventStream] SSE connection opened');
    };
  }

  /**
   * Closes the EventSource connection
   */
  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

/**
 * Hook to manage the event stream from the server
 * @param sessionId Session ID
 * @param callbacks Callbacks for various event types
 * @returns Controls for the event stream
 */
export function useSessionStream(sessionId: string, callbacks: StreamCallbacks): StreamControl {
  // Create a ref to keep the manager between renders
  const managerRef = useRef<EventStreamManager | null>(null);
  
  // Use useEffect to manage the connection lifecycle
  useEffect(() => {
    // Check that there is a valid session ID
    if (!sessionId) {
      return;
    }
    
    console.log(`[EventStream] Initializing connection for session ${sessionId}`);
    
    // Create a new instance of the manager
    const manager = new EventStreamManager(sessionId, callbacks);
    managerRef.current = manager;
    
    // Start the connection
    manager.connect();
    
    // Cleanup function that runs when the component unmounts
    // or when dependencies change
    return () => {
      console.log(`[EventStream] Cleaning up connection for session ${sessionId}`);
      if (managerRef.current) {
        managerRef.current.disconnect();
        managerRef.current = null;
      }
    };
  }, [sessionId, callbacks]); // Effect dependencies
  
  // Return an object with controls for the stream
  return {
    cleanup: () => {
      console.log(`[EventStream] Manual cleanup for session ${sessionId}`);
      if (managerRef.current) {
        managerRef.current.disconnect();
        managerRef.current = null;
      }
    }
  };
} 