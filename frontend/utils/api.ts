/**
 * API client for Intervista Assistant
 * 
 * Provides TypeScript functions to interact with the backend API
 */

// Base API URL - può essere configurato in base all'ambiente
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
// Modifichiamo l'URL del WebSocket per assicurarci che corrisponda al backend
const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/api';

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

// Client API per interagire con il backend

/**
 * Classe che gestisce le chiamate API all'assistente per interviste
 */
export class IntervistaApiClient {
  private baseUrl: string;
  private wsBaseUrl: string;
  private eventSource: EventSource | null = null;
  private audioConnections: Map<string, { ws: WebSocket; stream: MediaStream | null }> = new Map();

  constructor(baseUrl: string = API_BASE_URL, wsBaseUrl: string = WS_BASE_URL) {
    this.baseUrl = baseUrl;
    this.wsBaseUrl = wsBaseUrl;
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
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data: ApiResponse = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to start session');
      }

      return true;
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

    // Crea una nuova EventSource per SSE
    this.eventSource = new EventSource(`${this.baseUrl}/sessions/${sessionId}/stream`);
    let isConnectionClosed = false; // Flag per monitorare se la connessione è stata chiusa volontariamente

    // Registra gli handler per i vari tipi di eventi
    if (callbacks.onTranscription) {
      this.eventSource.addEventListener('transcription', (event) => {
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
        try {
          const data: ErrorUpdate = JSON.parse((event as any).data || '{}');
          callbacks.onError?.(data);
        } catch (e) {
          console.error('Error parsing error data:', e);
        }
      });
    }

    // Aggiungi un event listener per errori di connessione
    this.eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      
      // Informa il chiamante dell'errore di connessione
      callbacks.onConnectionError?.(error);
      
      // Se la connessione è stata chiusa volontariamente, non tentare di riconnettersi
      if (isConnectionClosed) {
        // Chiudi definitivamente l'EventSource per evitare riconnessioni automatiche
        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }
      }
    };

    // Restituisci la funzione per chiudere lo stream
    return () => {
      isConnectionClosed = true;
      this.closeEventStream();
    };
  }

  /**
   * Chiude la connessione SSE corrente
   */
  private closeEventStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
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
   * Inizia lo streaming audio dal microfono verso il backend
   * @param sessionId - ID della sessione
   * @returns Promise con il controllo dello streaming
   */
  async startAudioStream(sessionId: string): Promise<AudioStreamControl> {
    // Ferma un eventuale streaming audio precedente
    this.stopAudioStream(sessionId);

    try {
      // Richiedi l'accesso al microfono
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000, // Importante per la compatibilità con OpenAI
        },
        video: false,
      });

      // Crea un AudioContext per elaborare i dati audio
      const audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(stream);
      
      // NOTA: ScriptProcessorNode è deprecato, ma è ancora ampiamente supportato.
      // In futuro verrà sostituito con AudioWorkletNode
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      
      // Flag di pausa
      let isPaused = false;
      let isReconnecting = false;
      let reconnectionAttempts = 0;
      const MAX_RECONNECTION_ATTEMPTS = 3;
      let ws: WebSocket | null = null;
      let isClosingVoluntarily = false; // Flag per chiusura volontaria
      
      // Funzione per creare e connettere il WebSocket
      const connectWebSocket = (): Promise<WebSocket> => {
        return new Promise((resolve, reject) => {
          // Verifica se il sessionId è valido
          if (!sessionId) {
            reject(new Error('Session ID is required'));
            return;
          }

          // Reset della flag per la chiusura volontaria
          isClosingVoluntarily = false;

          // Crea una nuova connessione WebSocket
          ws = new WebSocket(`${this.wsBaseUrl}/sessions/${sessionId}/audio`);
          
          // Timeout per la connessione (5 secondi)
          const connectionTimeout = setTimeout(() => {
            if (ws && ws.readyState !== WebSocket.OPEN) {
              ws.close();
              reject(new Error('WebSocket connection timeout'));
            }
          }, 5000);
          
          // Handler per l'apertura della connessione
          const onOpen = () => {
            console.log('WebSocket audio connection established');
            clearTimeout(connectionTimeout);
            reconnectionAttempts = 0;
            resolve(ws as WebSocket);
            
            // Rimuovi gli eventi dopo la connessione
            if (ws) {
              ws.removeEventListener('open', onOpen);
              ws.removeEventListener('error', onError);
            }
          };
          
          // Handler per gli errori di connessione
          const onError = (event: Event) => {
            console.error('WebSocket connection error:', event);
            clearTimeout(connectionTimeout);
            reject(new Error('Failed to establish WebSocket connection'));
            
            // Rimuovi gli eventi dopo l'errore
            if (ws) {
              ws.removeEventListener('open', onOpen);
              ws.removeEventListener('error', onError);
            }
          };
          
          // Aggiungi gli handler alla connessione
          ws.addEventListener('open', onOpen);
          ws.addEventListener('error', onError);
          
          // Handler per la chiusura della connessione
          ws.addEventListener('close', (event) => {
            console.log(`WebSocket closed: ${event.code} ${event.reason}`);
            
            // Tenta di riconnettersi solo se:
            // 1. Non è una chiusura volontaria
            // 2. Non stiamo già tentando di riconnetterci
            // 3. Non abbiamo raggiunto il numero massimo di tentativi
            if (!isClosingVoluntarily && !isReconnecting && reconnectionAttempts < MAX_RECONNECTION_ATTEMPTS) {
              attemptReconnect();
            } else if (isClosingVoluntarily) {
              console.log('WebSocket closed voluntarily - not attempting reconnection');
            }
          });
        });
      };
      
      // Funzione per tentare la riconnessione
      const attemptReconnect = async () => {
        if (isReconnecting || isClosingVoluntarily) return;
        
        isReconnecting = true;
        reconnectionAttempts++;
        
        console.log(`\n[Connection lost. Reconnection attempt ${reconnectionAttempts}/${MAX_RECONNECTION_ATTEMPTS}]`);
        
        try {
          // Attendi un po' prima di riconnetterti (tempo crescente)
          await new Promise(resolve => setTimeout(resolve, 1000 * reconnectionAttempts));
          
          // Chiudi la connessione esistente se aperta
          if (ws) {
            ws.close();
            ws = null;
          }
          
          // Tenta di riconnettersi
          await connectWebSocket();
          
          isReconnecting = false;
        } catch (error) {
          isReconnecting = false;
          
          if (reconnectionAttempts < MAX_RECONNECTION_ATTEMPTS && !isClosingVoluntarily) {
            // Ritenta la connessione
            attemptReconnect();
          } else {
            console.error('Failed to reconnect after maximum attempts');
          }
        }
      };
      
      // Connetti il WebSocket inizialmente
      await connectWebSocket();
      
      // Memorizza la connessione
      if (ws) {
        this.audioConnections.set(sessionId, { ws, stream });
      } else {
        throw new Error('Failed to establish WebSocket connection');
      }
      
      // Callback di elaborazione audio
      processor.onaudioprocess = (e) => {
        // Non inviare audio se in pausa, se il WebSocket non esiste, 
        // se non è aperto o se stiamo chiudendo volontariamente
        if (isPaused || !ws || ws.readyState !== WebSocket.OPEN || isClosingVoluntarily) return;
        
        // Ottieni i dati audio dal canale sinistro
        const inputData = e.inputBuffer.getChannelData(0);
        
        // Converti in Int16Array (formato richiesto per l'API OpenAI)
        const audioData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          // Il formato Float32Array va da -1 a 1, convertiamo in Int16 (-32768 a 32767)
          audioData[i] = Math.max(-32768, Math.min(32767, Math.floor(inputData[i] * 32768)));
        }
        
        try {
          // Invia i dati audio al server come stringa Base64
          if (ws.readyState === WebSocket.OPEN) {
            // Converti i dati in Base64 per una compatibilità migliore
            const buffer = audioData.buffer;
            const base64data = btoa(
              new Uint8Array(buffer)
                .reduce((data, byte) => data + String.fromCharCode(byte), '')
            );
            ws.send(base64data);
          }
        } catch (err) {
          console.error('Error sending audio data:', err);
        }
      };
      
      // Collega il processor all'output (necessario per attivare onaudioprocess)
      source.connect(processor);
      processor.connect(audioContext.destination);
      
      // Restituisci un'interfaccia per controllare lo streaming
      return {
        stop: () => {
          // Imposta la flag per chiusura volontaria prima di fermare lo streaming
          isClosingVoluntarily = true;
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
  
  /**
   * Ferma lo streaming audio per una sessione
   * @param sessionId - ID della sessione
   */
  private stopAudioStream(sessionId: string): void {
    const connection = this.audioConnections.get(sessionId);
    if (connection) {
      // Chiudi la connessione WebSocket
      if (connection.ws) {
        try {
          if (connection.ws.readyState === WebSocket.OPEN || 
              connection.ws.readyState === WebSocket.CONNECTING) {
            connection.ws.close();
          }
        } catch (err) {
          console.error('Error closing WebSocket connection:', err);
        }
      }
      
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
}

// Esporta un'istanza predefinita per comodità
export const apiClient = new IntervistaApiClient();

// Funzioni helper esportate per un accesso più diretto

/**
 * Crea e avvia una nuova sessione
 * @returns Promise con l'ID della sessione
 */
export async function createAndStartSession(): Promise<string> {
  const sessionId = await apiClient.createSession();
  await apiClient.startSession(sessionId);
  return sessionId;
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

// Funzioni utility per l'audio

/**
 * Funzione di supporto per avviare lo streaming audio in una sessione
 * @param sessionId - ID della sessione
 * @returns Promise con il controllo dello streaming audio
 */
export async function startSessionAudio(sessionId: string): Promise<AudioStreamControl> {
  return await apiClient.startAudioStream(sessionId);
}
