/**
 * Module for managing event streams from the server (SSE)
 */
import { useEffect, useRef, useState } from 'react';
import { supabase } from './supabase';

// Base URL for the API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';
const SSE_URL = process.env.NEXT_PUBLIC_SSE_URL || 'http://127.0.0.1:8000/api/sessions/stream';

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

/**
 * Ottiene il token JWT dalla sessione corrente di Supabase
 * @returns Promise che risolve con il token JWT o null se non disponibile
 */
async function getAuthToken(): Promise<string | null> {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token || null;
  } catch (error) {
    console.error('Errore nel recupero del token:', error);
    return null;
  }
}

/**
 * Custom hook for handling Server-Sent Events (SSE)
 * @param sessionId Session ID
 * @returns Object with SSE events and status
 */
export function useSSEStream(sessionId: string) {
  const [events, setEvents] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  
  useEffect(() => {
    if (!sessionId) {
      console.log("[SSE] No session ID provided, not connecting to SSE");
      return;
    }
    
    let eventSource: EventSource | null = null;
    let retryCount = 0;
    const maxRetries = 3;
    
    // Funzione per inizializzare la connessione SSE con token
    const initSSE = async () => {
      try {
        // Ottieni il token JWT
        const token = await getAuthToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        
        // Costruisci l'URL con i parametri
        const url = new URL(`${API_BASE_URL}/sessions/stream?session_id=${sessionId}`);
        
        // Crea un nuovo EventSource con l'URL
        eventSource = new EventSource(url.toString());
        
        // Handler per la connessione aperta
        eventSource.onopen = () => {
          console.log(`[SSE] Connection opened for session ${sessionId}`);
          setConnected(true);
          setError(null);
          retryCount = 0;
        };
        
        // Handler per i messaggi
        eventSource.onmessage = (event) => {
          try {
            if (!event.data) {
              console.warn('[SSE] Empty data received');
              return;
            }
            
            const data = JSON.parse(event.data);
            console.log(`[SSE] Received event for session ${sessionId}:`, data);
            
            setEvents((prevEvents: any[]) => [...prevEvents, data]);
          } catch (e) {
            console.error('[SSE] Error parsing event data:', e);
          }
        };
        
        // Handler per gli errori
        eventSource.onerror = (e) => {
          console.error(`[SSE] Error in SSE connection for session ${sessionId}:`, e);
          setError('Error in SSE connection');
          setConnected(false);
          
          // Close the connection on error
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          
          // Retry connection
          retryCount++;
          if (retryCount < maxRetries) {
            console.log(`[SSE] Retrying connection (${retryCount}/${maxRetries})...`);
            setTimeout(initSSE, 2000 * retryCount);
          } else {
            console.error(`[SSE] Max retries (${maxRetries}) reached, giving up`);
            setError(`Max retries (${maxRetries}) reached, please try again later`);
          }
        };
      } catch (e) {
        console.error('[SSE] Error initializing SSE:', e);
        setError('Error initializing SSE connection');
        setConnected(false);
      }
    };
    
    // Inizializza la connessione SSE con token
    initSSE();
    
    // Cleanup function
    return () => {
      console.log(`[SSE] Closing SSE connection for session ${sessionId}`);
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
    };
  }, [sessionId]);
  
  return { events, error, connected };
}

/**
 * Function to initialize a one-time SSE connection for a specific session
 * @param sessionId Session ID
 * @param onEvent Callback for events
 * @param onError Callback for errors
 * @param onConnect Callback for connection events
 * @returns Object with methods to control the connection
 */
export function initializeSSEConnection(
  sessionId: string, 
  onEvent: (data: any) => void, 
  onError?: (error: any) => void, 
  onConnect?: () => void
) {
  let eventSource: EventSource | null = null;
  
  // Funzione per inizializzare la connessione con token
  const connect = async () => {
    try {
      if (eventSource) {
        console.log('[SSE] Closing existing connection before reconnecting');
        eventSource.close();
        eventSource = null;
      }
      
      // Ottieni il token JWT
      const token = await getAuthToken();
      
      // Costruisci l'URL con i parametri
      const url = new URL(`${API_BASE_URL}/sessions/stream?session_id=${sessionId}`);
      
      // Crea un nuovo EventSource con l'URL
      eventSource = new EventSource(url.toString());
      
      // Handler per apertura connessione
      eventSource.onopen = () => {
        console.log(`[SSE] Connection opened for session ${sessionId}`);
        if (onConnect) onConnect();
      };
      
      // Handler per messaggi eventi
      eventSource.onmessage = (event) => {
        try {
          if (!event.data) {
            console.warn('[SSE] Empty data received');
            return;
          }
          
          const data = JSON.parse(event.data);
          console.log(`[SSE] Event received:`, data);
          onEvent(data);
        } catch (e) {
          console.error('[SSE] Error parsing event data:', e);
          if (onError) onError(e);
        }
      };
      
      // Handler per errori
      eventSource.onerror = (e) => {
        console.error(`[SSE] Error in SSE connection:`, e);
        if (onError) onError(e);
      };
      
      return eventSource;
    } catch (e) {
      console.error(`[SSE] Error initializing connection:`, e);
      if (onError) onError(e);
      return null;
    }
  };
  
  // Inizializza subito la connessione
  connect();
  
  return {
    disconnect: () => {
      if (eventSource) {
        console.log('[SSE] Manually closing connection');
        eventSource.close();
        eventSource = null;
      }
    },
    reconnect: async () => {
      console.log('[SSE] Manually reconnecting');
      return connect();
    },
    isConnected: () => eventSource !== null && eventSource.readyState === EventSource.OPEN
  };
} 