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

    // Crea un nuovo EventSource per gli eventi SSE
    this.eventSource = new EventSource(`${API_BASE_URL}/sessions/stream?session_id=${this.sessionId}`);
    
    // Gestore generico per i messaggi
    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as Update;
        
        // Distribuisci i messaggi in base al tipo
        switch (data.type) {
          case 'transcription':
            this.callbacks.onTranscription?.(data);
            break;
          case 'response':
            this.callbacks.onResponse?.(data);
            break;
          case 'error':
            this.callbacks.onError?.(data);
            break;
          case 'connection':
            this.callbacks.onConnectionStatus?.(data.connected);
            break;
        }
      } catch (error) {
        console.error('Errore nel parsing del messaggio SSE:', error);
      }
    };
    
    // Gestione degli errori
    if (this.callbacks.onConnectionError) {
      this.eventSource.onerror = this.callbacks.onConnectionError;
    }
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
  // Utilizza useRef per mantenere un riferimento alla classe EventStreamManager
  const managerRef = useRef<EventStreamManager | null>(null);
  
  // Effetto per gestire la connessione
  useEffect(() => {
    if (!sessionId) return;
    
    // Crea un nuovo manager
    const manager = new EventStreamManager(sessionId, callbacks);
    managerRef.current = manager;
    
    // Inizia a gestire gli eventi
    manager.connect();
    
    // Pulizia al dismount del componente
    return () => {
      if (managerRef.current) {
        managerRef.current.disconnect();
      }
    };
  }, [sessionId, callbacks]);

  // Ritorna i controlli dello stream
  return {
    cleanup: () => {
      if (managerRef.current) {
        managerRef.current.disconnect();
      }
    }
  };
} 