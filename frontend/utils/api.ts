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

// Funzione di utilità per verificare la validità di un session ID
const isValidSessionId = (sessionId: string): boolean => {
  // Verifica che sia una stringa non vuota e che contenga solo numeri
  return sessionId !== undefined && 
         sessionId !== null && 
         sessionId.trim() !== '' && 
         /^\d+$/.test(sessionId);
};

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
      console.log('Creating new session...');
      const response = await fetch(`${this.baseUrl}/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.status} ${response.statusText}`);
      }

      const data: SessionResponse = await response.json();
      
      if (!data.success || !data.session_id) {
        throw new Error('Invalid response from server');
      }
      
      console.log(`Session created with ID: ${data.session_id}`);
      
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
    if (!isValidSessionId(sessionId)) {
      console.error('Invalid session ID:', sessionId);
      return false;
    }
    
    try {
      // Creiamo un AbortController per il timeout, più compatibile con tutti i browser
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      
      console.log(`Avvio sessione ${sessionId}...`);
      // Utilizziamo il parametro nella query string anziché nel percorso
      const response = await fetch(`${this.baseUrl}/sessions/start?sessionId=${sessionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        console.error(`Errore nell'avvio della sessione: ${response.status} ${response.statusText}`);
        return false;
      }
      
      const data: ApiResponse = await response.json();
      
      if (!data.success) {
        console.error(`Avvio sessione fallito: ${data.error || 'Unknown error'}`);
        return false;
      }
      
      console.log('Sessione avviata con successo');
      return true;
    } catch (error) {
      console.error('Error starting session:', error);
      return false;
    }
  }

  /**
   * Termina una sessione esistente
   * @param sessionId - ID della sessione da terminare
   * @returns Promise con il risultato dell'operazione
   */
  async endSession(sessionId: string): Promise<boolean> {
    if (!isValidSessionId(sessionId)) {
      console.error('Invalid session ID:', sessionId);
      return false;
    }
    
    try {
      // Ferma lo streaming audio se attivo
      this.stopAudioStream(sessionId);
      
      console.log(`Chiusura sessione ${sessionId}...`);
      // Utilizziamo il parametro nella query string anziché nel percorso
      const response = await fetch(`${this.baseUrl}/sessions/end?sessionId=${sessionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      });
      
      if (!response.ok) {
        console.error(`Errore nella chiusura della sessione: ${response.status} ${response.statusText}`);
        return false;
      }
      
      const data: ApiResponse = await response.json();
      
      if (!data.success) {
        console.error(`Chiusura sessione fallita: ${data.error || 'Unknown error'}`);
        return false;
      }
      
      console.log('Sessione chiusa con successo');
      
      // Chiudi anche il socket.io
      if (this.socket) {
        this.socket.disconnect();
        this.socket = null;
      }
      
      // Chiudi l'EventSource
      this.closeEventStream();
      
      this.audioConnections.delete(sessionId);
      
      return true;
    } catch (error) {
      console.error('Error ending session:', error);
      return false;
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
    if (!isValidSessionId(sessionId)) {
      console.error('Invalid session ID for stream updates:', sessionId);
      return () => {};
    }
    
    // Chiudi eventuali connessioni esistenti
    this.closeEventStream();
    
    let retryCount = 0;
    const MAX_RETRIES = 3;
    
    // Funzione per configurare l'EventSource
    const setupEventSource = () => {
      console.log(`Setting up new EventSource connection for session ${sessionId}...`);
      
      // Utilizziamo il parametro nella query string anziché nel percorso
      const url = new URL(`${this.baseUrl}/sessions/stream`);
      // Aggiungiamo l'ID della sessione come parametro di query
      url.searchParams.append('sessionId', sessionId);
      // Aggiungiamo un timestamp per evitare la cache del browser
      url.searchParams.append('ts', Date.now().toString());
      
      try {
        // Creazione dell'EventSource (SSE)
        this.eventSource = new EventSource(url.toString());
        
        // Gestione degli eventi di connessione
        this.eventSource.onopen = () => {
          console.log('EventSource connection established');
          retryCount = 0; // Resetta il contatore dei tentativi quando la connessione ha successo
        };
        
        // Gestione degli eventi di trascrizione
        this.eventSource.addEventListener('transcription', (event) => {
          try {
            if (callbacks.onTranscription) {
              const data = JSON.parse(event.data);
              callbacks.onTranscription(data);
            }
          } catch (error) {
            console.error('Error handling transcription event:', error);
          }
        });
        
        // Gestione degli eventi di risposta
        this.eventSource.addEventListener('response', (event) => {
          try {
            if (callbacks.onResponse) {
              const data = JSON.parse(event.data);
              callbacks.onResponse(data);
            }
          } catch (error) {
            console.error('Error handling response event:', error);
          }
        });
        
        // Gestione degli eventi di errore
        this.eventSource.addEventListener('error', (event) => {
          try {
            if (callbacks.onError) {
              // Se c'è un payload di errore, lo gestiamo come un evento di errore strutturato
              if ((event as any).data) {
                const data = JSON.parse((event as any).data);
                callbacks.onError(data);
              }
            }
            
            // Gestiamo anche gli errori di connessione SSE
            if (callbacks.onConnectionError) {
              callbacks.onConnectionError(event);
            }
            
            // Tentiamo di riconnettere se non abbiamo superato il numero massimo di tentativi
            if (retryCount < MAX_RETRIES) {
              console.log(`EventSource connection error. Retry attempt ${retryCount + 1}/${MAX_RETRIES}...`);
              retryCount++;
              
              // Chiudiamo la connessione esistente
              if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
              }
              
              // Tentiamo di riconnetterci dopo un breve ritardo
              setTimeout(() => {
                setupEventSource();
              }, 1000 * retryCount); // Aumentiamo progressivamente il ritardo
            } else {
              console.error('Max EventSource retry attempts exceeded');
              if (callbacks.onConnectionError) {
                callbacks.onConnectionError(new Event('maxretries'));
              }
            }
          } catch (error) {
            console.error('Error handling error event:', error);
          }
        });
        
        // Gestione della chiusura
        this.eventSource.addEventListener('close', () => {
          console.log('EventSource connection closed by server');
          this.eventSource = null;
        });
        
      } catch (error) {
        console.error('Error setting up EventSource:', error);
        if (callbacks.onConnectionError) {
          callbacks.onConnectionError(new Event('setup'));
        }
      }
    };
    
    // Inizializza l'EventSource
    setupEventSource();
    
    // Funzione di pulizia da restituire per useEffect
    return () => {
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
    if (!isValidSessionId(sessionId)) {
      console.error('Invalid session ID for sending text message:', sessionId);
      return false;
    }
    
    try {
      console.log(`Invio messaggio di testo alla sessione ${sessionId}: "${text}"`);
      
      // Utilizziamo il parametro nella query string anziché nel percorso
      const response = await fetch(`${this.baseUrl}/sessions/text?sessionId=${sessionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      });
      
      console.log(`Risposta del server: ${response.status} ${response.statusText}`);
      
      // Verifica se la risposta è valida
      if (!response.ok) {
        console.error(`Errore HTTP: ${response.status} ${response.statusText}`);
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      
      // Controlla se la risposta contiene JSON valido
      const textResponse = await response.text();
      console.log(`Risposta completa: ${textResponse}`);
      
      try {
        const data = JSON.parse(textResponse);
        if (!data.success) {
          throw new Error(data.error || 'Failed to send text message');
        }
        return true;
      } catch (jsonError) {
        console.error('Errore nel parsing della risposta JSON:', jsonError);
        console.error('Testo ricevuto:', textResponse);
        throw new Error('Invalid JSON response from server');
      }
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
        const startResponse = await fetch(`${this.baseUrl}/sessions/start?sessionId=${sessionId}`, {
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
        const statusResponse = await fetch(`${this.baseUrl}/sessions/status?sessionId=${sessionId}`, {
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