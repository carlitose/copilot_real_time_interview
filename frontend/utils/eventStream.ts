/**
 * Modulo per la gestione degli stream di eventi dal server (SSE)
 */
import { useEffect, useRef } from 'react';

// URL di base per l'API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

// Tipi di aggiornamento
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

// Tipo di aggiornamento generico
export type Update = TranscriptionUpdate | ResponseUpdate | ErrorUpdate | ConnectionUpdate;

// Callback per gli eventi
export interface StreamCallbacks {
  onTranscription?: (update: TranscriptionUpdate) => void;
  onResponse?: (update: ResponseUpdate) => void;
  onError?: (update: ErrorUpdate) => void;
  onConnectionError?: (error: Event) => void;
  onConnectionStatus?: (connected: boolean) => void;
}

/**
 * Gestisce la connessione SSE con il server
 */
export interface StreamControl {
  cleanup: () => void;
}

/**
 * Classe che gestisce la connessione EventSource
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
   * Inizia a gestire gli eventi
   */
  connect(): void {
    if (!this.sessionId) return;
    
    // Chiudi eventuali fonti di eventi esistenti
    this.disconnect();

    console.log(`[EventStream] Connecting to SSE endpoint for session ${this.sessionId}`);
    
    // Crea un nuovo EventSource per gli eventi SSE
    this.eventSource = new EventSource(`${API_BASE_URL}/sessions/stream?session_id=${this.sessionId}`);
    
    // Gestore generico per i messaggi
    this.eventSource.onmessage = (event) => {
      console.log(`[EventStream] Raw event received: ${event.data}`);
      
      try {
        const data = JSON.parse(event.data);
        
        // Verifichiamo che ci sia un tipo definito
        if (!data || typeof data !== 'object' || !('type' in data)) {
          console.warn('[EventStream] Received data without type property:', data);
          return;
        }
        
        console.log(`[EventStream] Parsed event type: ${data.type}`);
        
        // Distribuisci i messaggi in base al tipo
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
        console.error('[EventStream] Errore nel parsing del messaggio SSE:', error);
        console.error('[EventStream] Raw message data:', event.data);
      }
    };
    
    // Gestione degli errori
    this.eventSource.onerror = (error) => {
      console.error('[EventStream] SSE connection error:', error);
      if (this.callbacks.onConnectionError) {
        this.callbacks.onConnectionError(error);
      }
    };
    
    // Gestione della connessione aperta
    this.eventSource.onopen = () => {
      console.log('[EventStream] SSE connection opened');
    };
  }

  /**
   * Chiude la connessione EventSource
   */
  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

/**
 * Hook per gestire lo stream di eventi dal server
 * @param sessionId ID della sessione
 * @param callbacks Callback per vari tipi di eventi
 * @returns Controlli per lo stream di eventi
 */
export function useSessionStream(sessionId: string, callbacks: StreamCallbacks): StreamControl {
  // Creiamo un ref per mantenere il manager tra i rendering
  const managerRef = useRef<EventStreamManager | null>(null);
  
  // Utilizziamo useEffect per gestire il ciclo di vita della connessione
  useEffect(() => {
    // Verifichiamo che sia presente un ID sessione valido
    if (!sessionId) {
      return;
    }
    
    console.log(`[EventStream] Initializing connection for session ${sessionId}`);
    
    // Creiamo una nuova istanza del manager
    const manager = new EventStreamManager(sessionId, callbacks);
    managerRef.current = manager;
    
    // Avviamo la connessione
    manager.connect();
    
    // Funzione di pulizia che viene eseguita quando il componente viene smontato
    // o quando le dipendenze cambiano
    return () => {
      console.log(`[EventStream] Cleaning up connection for session ${sessionId}`);
      if (managerRef.current) {
        managerRef.current.disconnect();
        managerRef.current = null;
      }
    };
  }, [sessionId, callbacks]); // Dipendenze dell'effetto
  
  // Restituiamo un oggetto con i controlli per lo stream
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