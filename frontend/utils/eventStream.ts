
// Start of Selection
/**
 * Modulo per la gestione degli stream di eventi dal server (SSE)
 */
import { useEffect } from 'react';

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
 * Hook per gestire lo stream di eventi dal server
 * @param sessionId ID della sessione
 * @param callbacks Callback per vari tipi di eventi
 * @returns Controlli per lo stream di eventi
 */
export function useSessionStream(sessionId: string, callbacks: StreamCallbacks): StreamControl {
  // Effetto per gestire la connessione
  useEffect(() => {
    if (!sessionId) return;

    // Crea un EventSource per gli eventi SSE
    const eventSource = new EventSource(`${API_BASE_URL}/sessions/stream?session_id=${sessionId}`);
    
    // Gestore generico per i messaggi
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as Update;
        
        // Distribuisci i messaggi in base al tipo
        switch (data.type) {
          case 'transcription':
            callbacks.onTranscription?.(data);
            break;
          case 'response':
            callbacks.onResponse?.(data);
            break;
          case 'error':
            callbacks.onError?.(data);
            break;
          case 'connection':
            callbacks.onConnectionStatus?.(data.connected);
            break;
        }
      } catch (error) {
        console.error('Errore nel parsing del messaggio SSE:', error);
      }
    };
    
    // Gestione degli errori
    if (callbacks.onConnectionError) {
      eventSource.onerror = callbacks.onConnectionError;
    }
    
    // Pulizia al dismount del componente
    return () => {
      eventSource.close();
    };
  }, [sessionId, callbacks]);

  // Ritorna i controlli dello stream
  return {
    cleanup: () => {
      // Ottieni e chiudi l'EventSource esistente se presente
      const elements = document.querySelectorAll('event-source');
      for (let i = 0; i < elements.length; i++) {
        const element = elements[i];
        if ((element as any).url?.includes(sessionId)) {
          (element as any).close();
        }
      }
      
      // Crea un nuovo EventSource (per assicurarsi) e chiudi immediatamente
      const eventSource = new EventSource(`${API_BASE_URL}/sessions/stream?session_id=${sessionId}`);
      eventSource.close();
    }
  };
} 