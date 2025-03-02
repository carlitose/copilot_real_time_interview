/**
 * API client for Intervista Assistant
 * 
 * Provides TypeScript functions to interact with the backend API
 */

import { io, Socket } from 'socket.io-client';

// Base API URL - può essere configurato in base all'ambiente
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';
// Modifichiamo l'URL del WebSocket per assicurarci che corrisponda al backend
const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'http://127.0.0.1:8000';

// Tipi per le risposte dell'API

export interface ApiResponse<T = any> {
  success: boolean;
  error?: string;
  message?: string;
  [key: string]: any;
}

export interface SessionResponse extends ApiResponse {
  session_id: string;
}

export interface TranscriptionUpdate {
  timestamp: string;
  text: string;
}

export interface ResponseUpdate {
  timestamp: string;
  text: string;
}

export interface ErrorUpdate {
  timestamp: string;
  message: string;
}

export interface SessionUpdates {
  transcription: TranscriptionUpdate[];
  response: ResponseUpdate[];
  error: ErrorUpdate[];
}

export interface ConversationData {
  timestamp: string;
  messages: {
    role: 'user' | 'assistant' | 'system';
    content: string;
  }[];
}

export interface Monitor {
  top: number;
  left: number;
  width: number;
  height: number;
}

/**
 * Interfaccia per il controllo dello streaming audio
 */
export interface AudioStreamControl {
  /** Ferma lo streaming audio e rilascia le risorse */
  stop: () => void;
  /** Mette in pausa lo streaming audio */
  pause: () => void;
  /** Riprende lo streaming audio dopo una pausa */
  resume: () => void;
  /** Stato corrente (true se in pausa) */
  isPaused: boolean;
}

// Aggiungi la dichiarazione del tipo per webkitAudioContext
declare global {
  interface Window {
    webkitAudioContext: typeof AudioContext;
  }
}

// Client API per interagire con il backend

/**
 * Classe che gestisce le chiamate API all'assistente per interviste
 */
export class IntervistaApiClient {
  private baseUrl: string;
  private wsBaseUrl: string;
  private socket: Socket | null = null;
  private eventSource: EventSource | null = null;
  private audioConnections: Map<string, { stream: MediaStream | null }> = new Map();

  constructor(baseUrl: string = API_BASE_URL, wsBaseUrl: string = WS_BASE_URL) {
    this.baseUrl = baseUrl;
    this.wsBaseUrl = wsBaseUrl;
    this.init();
  }

  init() {
    if (this.socket) {
      if (this.socket.connected) {
        console.log("Socket.IO già connesso, riutilizzo la connessione esistente");
        return;
      } else {
        console.log("Socket.IO istanza esistente ma disconnessa, chiudo e ricreo");
        this.socket.close();
        this.socket = null;
      }
    }
    
    console.log("Inizializzazione Socket.IO con URL:", WS_BASE_URL);
    
    // Inizializza Socket.IO con riconnessione automatica
    this.socket = io(WS_BASE_URL, {
      reconnectionDelayMax: 10000,
      reconnection: true,
      reconnectionAttempts: 10,
      transports: ['websocket', 'polling'],
      path: '/socket.io',
      timeout: 20000,
      forceNew: true
    });

    // Gestione degli eventi Socket.IO
    this.socket.on('connect', () => {
      console.log('Socket.IO connected! ID:', this.socket?.id);
    });
    
    this.socket.on('connect_error', (error: any) => {
      console.error('Socket.IO connection error:', error);
    });
    
    this.socket.on('error', (error: any) => {
      console.error('Socket.IO error:', error);
    });
    
    this.socket.on('disconnect', (reason: string) => {
      console.log('Socket.IO disconnected:', reason);
    });
  }

  /**
   * Crea una nuova sessione
   * @returns Promise con l'ID della sessione
   */
  async createSession(): Promise<string> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data: SessionResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to create session');
      }

      return data.session_id;
    } catch (error) {
      console.error('Error creating session:', error);
      throw error;
    }
  }

  /**
   * Avvia una sessione esistente
   * @param sessionId - ID della sessione da avviare
   * @returns Promise con il risultato dell'operazione
   */
  async startSession(sessionId: string): Promise<boolean> {
    try {
      // Creiamo un AbortController per il timeout, più compatibile con tutti i browser
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 secondi di timeout
      
      try {
        const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/start`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          // Usiamo il signal dell'AbortController invece di AbortSignal.timeout
          signal: controller.signal
        });
        
        // Puliamo il timeout
        clearTimeout(timeoutId);

        const data: ApiResponse = await response.json();

        if (!data.success) {
          throw new Error(data.error || 'Failed to start session');
        }

        return true;
      } catch (error: any) {
        // Puliamo il timeout anche in caso di errore
        clearTimeout(timeoutId);
        
        // Se è un errore di abort, lo trasformiamo in un errore di timeout
        if (error.name === 'AbortError') {
          throw new Error('Timeout while connecting to the server');
        }
        
        throw error;
      }
    } catch (error) {
      console.error('Error starting session:', error);
      throw error;
    }
  }

  /**
   * Termina una sessione esistente
   * @param sessionId - ID della sessione da terminare
   * @returns Promise con il risultato dell'operazione
   */
  async endSession(sessionId: string): Promise<boolean> {
    try {
      // Ferma lo streaming audio se attivo
      this.stopAudioStream(sessionId);
      
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/end`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to end session');
      }

      // Assicurati di chiudere la connessione SSE se attiva
      this.closeEventStream();

      return true;
    } catch (error) {
      console.error('Error ending session:', error);
      throw error;
    }
  }

  /**
   * Ottiene gli aggiornamenti di una sessione (polling)
   * @param sessionId - ID della sessione
   * @param type - Tipo di aggiornamenti da ottenere (opzionale)
   * @returns Promise con gli aggiornamenti
   */
  async getSessionUpdates(sessionId: string, type?: string): Promise<SessionUpdates | TranscriptionUpdate[] | ResponseUpdate[] | ErrorUpdate[]> {
    try {
      const url = new URL(`${this.baseUrl}/sessions/${sessionId}/updates`);
      if (type) {
        url.searchParams.append('type', type);
      }

      const response = await fetch(url.toString(), {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to get session updates');
      }

      return data.updates;
    } catch (error) {
      console.error('Error getting session updates:', error);
      throw error;
    }
  }

  /**
   * Avvia lo streaming degli aggiornamenti della sessione utilizzando SSE
   * @param sessionId - ID della sessione
   * @param callbacks - Oggetto con callback per diversi tipi di eventi
   * @returns La funzione per chiudere lo stream
   */
  streamSessionUpdates(
    sessionId: string,
    callbacks: {
      onTranscription?: (update: TranscriptionUpdate) => void;
      onResponse?: (update: ResponseUpdate) => void;
      onError?: (update: ErrorUpdate) => void;
      onConnectionError?: (error: Event) => void;
    }
  ): () => void {
    // Chiudi eventuali connessioni esistenti
    this.closeEventStream();

    let isConnectionClosed = false;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 3;
    let hasReceived404 = false; // Flag per tracciare errori 404

    const setupEventSource = () => {
      if (isConnectionClosed || hasReceived404) return;

      try {
        console.log('Setting up new EventSource connection...');
        this.eventSource = new EventSource(`${this.baseUrl}/sessions/${sessionId}/stream`);

        // Registra gli handler per i vari tipi di eventi
        if (callbacks.onTranscription) {
          this.eventSource.addEventListener('transcription', (event) => {
            if (isConnectionClosed) return;
            try {
              const data: TranscriptionUpdate = JSON.parse(event.data);
              callbacks.onTranscription?.(data);
            } catch (e) {
              console.error('Error parsing transcription data:', e);
            }
          });
        }

        if (callbacks.onResponse) {
          this.eventSource.addEventListener('response', (event) => {
            if (isConnectionClosed) return;
            try {
              const data: ResponseUpdate = JSON.parse(event.data);
              callbacks.onResponse?.(data);
            } catch (e) {
              console.error('Error parsing response data:', e);
            }
          });
        }

        if (callbacks.onError) {
          this.eventSource.addEventListener('error', (event) => {
            if (isConnectionClosed) return;
            try {
              const data: ErrorUpdate = JSON.parse((event as any).data || '{}');
              callbacks.onError?.(data);
            } catch (e) {
              console.error('Error parsing error data:', e);
            }
          });
        }

        // Gestione errori di connessione
        this.eventSource.onerror = async (error) => {
          console.error('SSE connection error:', error);
          
          if (isConnectionClosed) {
            this.closeEventStream();
            return;
          }

          // Verifica se la sessione esiste ancora
          try {
            const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/status`, {
              method: 'GET',
              headers: { 'Content-Type': 'application/json' }
            });

            if (response.status === 404) {
              console.log('Session no longer exists, stopping reconnection attempts');
              hasReceived404 = true;
              this.closeEventStream();
              callbacks.onConnectionError?.(new Event('sessionClosed'));
              return;
            }
          } catch (checkError) {
            console.error('Error checking session status:', checkError);
          }

          callbacks.onConnectionError?.(error);
          
          // Tentativo di riconnessione solo se non abbiamo ricevuto un 404
          if (!hasReceived404 && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            console.log(`SSE reconnection attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`);
            
            // Aumenta il delay tra i tentativi (exponential backoff)
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 5000);
            
            setTimeout(() => {
              if (!isConnectionClosed && !hasReceived404) {
                this.closeEventStream();
                setupEventSource();
              }
            }, delay);
          } else {
            console.error('Max SSE reconnection attempts reached or session closed');
            this.closeEventStream();
          }
        };

        // Reset del contatore di tentativi quando la connessione ha successo
        this.eventSource.onopen = () => {
          console.log('SSE connection established successfully');
          reconnectAttempts = 0;
        };

      } catch (error) {
        console.error('Error setting up EventSource:', error);
        callbacks.onConnectionError?.(new Event('error'));
      }
    };

    // Avvia la connessione SSE
    setupEventSource();

    // Restituisci la funzione per chiudere lo stream
    return () => {
      console.log('Closing SSE connection voluntarily');
      isConnectionClosed = true;
      hasReceived404 = true; // Impediamo ulteriori tentativi di riconnessione
      this.closeEventStream();
    };
  }

  /**
   * Chiude la connessione SSE corrente
   */
  private closeEventStream(): void {
    if (this.eventSource) {
      try {
        console.log('Closing EventSource connection');
        this.eventSource.close();
      } catch (error) {
        console.error('Error closing EventSource:', error);
      } finally {
        this.eventSource = null;
      }
    }
  }

  /**
   * Invia un messaggio di testo alla sessione
   * @param sessionId - ID della sessione
   * @param text - Testo da inviare
   * @returns Promise con il risultato dell'operazione
   */
  async sendTextMessage(sessionId: string, text: string): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/text`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to send text message');
      }

      return true;
    } catch (error) {
      console.error('Error sending text message:', error);
      throw error;
    }
  }

  /**
   * Acquisisce e analizza uno screenshot
   * @param sessionId - ID della sessione
   * @param monitorIndex - Indice del monitor (opzionale)
   * @returns Promise con il risultato dell'operazione
   */
  async takeScreenshot(sessionId: string, monitorIndex?: number): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/screenshot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(monitorIndex !== undefined ? { monitor_index: monitorIndex } : {}),
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to take screenshot');
      }

      return true;
    } catch (error) {
      console.error('Error taking screenshot:', error);
      throw error;
    }
  }

  /**
   * Avvia il processo di pensiero avanzato
   * @param sessionId - ID della sessione
   * @returns Promise con il risultato dell'operazione
   */
  async startThinkProcess(sessionId: string): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/think`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to start think process');
      }

      return true;
    } catch (error) {
      console.error('Error starting think process:', error);
      throw error;
    }
  }

  /**
   * Salva la conversazione corrente
   * @param sessionId - ID della sessione
   * @returns Promise con i dati della conversazione
   */
  async saveConversation(sessionId: string): Promise<ConversationData> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/save`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to save conversation');
      }

      return data.conversation as ConversationData;
    } catch (error) {
      console.error('Error saving conversation:', error);
      throw error;
    }
  }

  /**
   * Ottiene l'elenco dei monitor disponibili
   * @returns Promise con l'elenco dei monitor
   */
  async getMonitors(): Promise<Monitor[]> {
    try {
      const response = await fetch(`${this.baseUrl}/monitors`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to get monitors');
      }

      return data.monitors as Monitor[];
    } catch (error) {
      console.error('Error getting monitors:', error);
      throw error;
    }
  }

  /**
   * Ferma lo streaming audio per una sessione
   * @param sessionId - ID della sessione
   */
  private stopAudioStream(sessionId: string): void {
    const connection = this.audioConnections.get(sessionId);
    if (connection) {
      // Ferma lo stream del microfono
      if (connection.stream) {
        try {
          connection.stream.getTracks().forEach(track => track.stop());
        } catch (err) {
          console.error('Error stopping audio tracks:', err);
        }
      }
      
      // Rimuovi la connessione dalla mappa
      this.audioConnections.delete(sessionId);
    }
  }

  /**
   * Inizia lo streaming audio dal microfono verso il backend
   * @param sessionId - ID della sessione
   * @returns Promise con il controllo dello streaming
   */
  async startAudioStream(sessionId: string): Promise<AudioStreamControl> {
    // Ferma un eventuale streaming audio precedente
    this.stopAudioStream(sessionId);

    try {
      console.log("Tentativo di avvio streaming audio per la sessione:", sessionId);
      
      // Verifica che la sessione esista prima di iniziare lo streaming
      try {
        // Prima, assicuriamoci che la sessione sia avviata
        console.log("Avvio della sessione prima dello streaming audio...");
        const startResponse = await fetch(`${this.baseUrl}/sessions/${sessionId}/start`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Accept': 'application/json' 
          },
          mode: 'cors'
        });
        
        if (!startResponse.ok) {
          console.warn(`Risposta non ok dall'avvio sessione: ${startResponse.status}`);
          // Non interrompiamo il flusso qui, potrebbe essere già avviata
        } else {
          console.log("Sessione avviata con successo");
        }
        
        // Ora verifichiamo lo stato
        const statusResponse = await fetch(`${this.baseUrl}/sessions/${sessionId}/status`, {
          method: 'GET',
          headers: { 
            'Content-Type': 'application/json',
            'Accept': 'application/json'
          },
          mode: 'cors',
        });

        console.log("Risposta status:", statusResponse.status);
        
        if (statusResponse.status === 404) {
          throw new Error('Session not found');
        }
        
        // Verifica la risposta
        const data = await statusResponse.json();
        console.log("Dati risposta status:", data);
        
        if (!data.success) {
          throw new Error(data.error || 'Error checking session status');
        }
        
        // Verifichiamo che la registrazione sia effettivamente attiva
        if (!data.status?.is_recording) {
          console.warn("La sessione esiste ma non è in registrazione, riprova...");
          // Tenta di avviare nuovamente
          await fetch(`${this.baseUrl}/sessions/${sessionId}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            mode: 'cors'
          });
        }
      } catch (error) {
        console.error("Errore durante il controllo dello stato della sessione:", error);
        // Continuiamo comunque, potrebbe essere solo un problema dell'endpoint status
      }

      // Connetti Socket.IO se non è già connesso
      if (!this.socket) {
        this.init();
      }
      
      if (!this.socket?.connected) {
        console.log("Tentativo di connessione Socket.IO...");
        await new Promise<void>((resolve, reject) => {
          if (!this.socket) {
            this.init();
            if (!this.socket) return reject(new Error('Socket not initialized'));
          }
          
          const timeout = setTimeout(() => {
            reject(new Error('Socket connection timeout'));
          }, 10000); // Aumentiamo il timeout a 10 secondi

          this.socket.once('connect', () => {
            clearTimeout(timeout);
            console.log("Socket.IO connesso con successo");
            resolve();
          });

          this.socket.connect();
        });
      } else {
        console.log("Socket.IO già connesso");
      }

      // Richiedi l'accesso al microfono con parametri ottimizzati
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 16000,
        },
        video: false,
      });

      // Crea un AudioContext con sample rate fisso
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(stream);
      
      // Carica l'AudioWorklet
      await audioContext.audioWorklet.addModule('/audio-processor.js');
      const processor = new AudioWorkletNode(audioContext, 'audio-processor');
      
      let isPaused = false;
      let isActive = true;
      
      // Memorizza la connessione
      this.audioConnections.set(sessionId, { stream });
      
      // Gestisci i messaggi dall'AudioWorklet
      processor.port.onmessage = (event) => {
        if (!isActive || isPaused || !this.socket?.connected) return;
        
        try {
          const audioData = event.data;
          this.socket.emit('audio_data', sessionId, audioData, (error: any) => {
            if (error) {
              console.error('Error sending audio data:', error);
              if (error.message === 'Session not found') {
                isActive = false;
                this.stopAudioStream(sessionId);
              }
            }
          });
        } catch (err) {
          console.error('Error processing audio data:', err);
        }
      };
      
      // Collega il processor
      source.connect(processor);
      processor.connect(audioContext.destination);
      
      // Gestisci gli errori Socket.IO
      const errorHandler = (error: any) => {
        console.error('Socket.IO error:', error);
        if (error.message === 'Session not found' || error.message === 'Session not recording') {
          isActive = false;
          this.stopAudioStream(sessionId);
        }
      };

      this.socket?.on('error', errorHandler);
      
      // Restituisci l'interfaccia di controllo
      return {
        stop: () => {
          isActive = false;
          this.socket?.off('error', errorHandler);
          this.stopAudioStream(sessionId);
        },
        pause: () => {
          isPaused = true;
          console.log('Audio streaming paused');
        },
        resume: () => {
          isPaused = false;
          console.log('Audio streaming resumed');
        },
        get isPaused() {
          return isPaused;
        }
      };
      
    } catch (error) {
      console.error('Error starting audio stream:', error);
      this.stopAudioStream(sessionId);
      throw error;
    }
  }
}

// Esporta un'istanza predefinita per comodità
export const apiClient = new IntervistaApiClient();

// Funzioni helper esportate per un accesso più diretto

/**
 * Funzione di supporto per avviare lo streaming audio in una sessione
 * @param sessionId - ID della sessione
 * @returns Promise con il controllo dello streaming audio
 */
export async function startSessionAudio(sessionId: string): Promise<AudioStreamControl> {
  return await apiClient.startAudioStream(sessionId);
}

/**
 * Funzione di supporto per l'utilizzo di SSE con React hooks
 * @param sessionId - ID della sessione
 * @param callbacks - Callbacks per i diversi tipi di eventi
 * @returns Oggetto con funzione cleanup per useEffect
 */
export function useSessionStream(
  sessionId: string | null,
  callbacks: {
    onTranscription?: (update: TranscriptionUpdate) => void;
    onResponse?: (update: ResponseUpdate) => void;
    onError?: (update: ErrorUpdate) => void;
    onConnectionError?: (error: Event) => void;
  }
): { cleanup: () => void } {
  let cleanup = () => {};

  if (sessionId) {
    cleanup = apiClient.streamSessionUpdates(sessionId, callbacks);
  }

  return { cleanup };
}