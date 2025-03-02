import axios from 'axios';

// Definizione dei tipi
export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

class ApiService {
  private baseUrl: string;
  private wsUrl: string;
  public socket: WebSocket | null = null;
  private messageCallback: ((message: Message) => void) | null = null;
  
  constructor() {
    // Use environment variable or default to localhost
    this.baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    
    // Determine WebSocket URL
    const wsProtocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = this.baseUrl.replace(/^https?:\/\//, '');
    this.wsUrl = `${wsProtocol}//${host}/ws`;
    
    console.log('API Service initialized with baseUrl:', this.baseUrl);
    console.log('WebSocket URL:', this.wsUrl);
  }

  // Inizializza la connessione WebSocket utilizzando l'API WebSocket nativa
  initWebSocket(onMessage: (message: Message) => void, onConnect: () => void, onDisconnect: () => void) {
    // Chiudi connessione precedente se esiste
    if (this.socket) {
      this.socket.close();
    }

    // Salva il callback dei messaggi
    this.messageCallback = onMessage;
    
    console.log('Initializing WebSocket connection to:', this.wsUrl);
    
    try {
      // Crea una nuova connessione WebSocket
      this.socket = new WebSocket(this.wsUrl);
      
      this.socket.onopen = () => {
        console.log('WebSocket connection established successfully');
        onConnect();
      };
      
      this.socket.onclose = (event) => {
        console.log('WebSocket connection closed:', event.code, event.reason);
        onDisconnect();
      };

      this.socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        
        // Notifichiamo l'errore all'utente
        if (this.messageCallback) {
          this.messageCallback({
            role: 'assistant',
            content: `⚠️ **Errore di connessione WebSocket**\n\nSi è verificato un errore di comunicazione con il server. Controlla la console del browser per dettagli.`,
          });
        }
      };
      
      this.socket.onmessage = (event) => {
        console.log('WebSocket message received:', event.data);
        try {
          const data = JSON.parse(event.data);
          console.log('Parsed WebSocket message:', data);
          
          if (data.type === 'response' && this.messageCallback) {
            console.log('Trovata risposta WebSocket, invoco callback con:', data.content);
            this.messageCallback({
              role: 'assistant',
              content: data.content,
            });
          } else if (data.type === 'transcription' && this.messageCallback) {
            console.log('Trovata trascrizione WebSocket, invoco callback con:', data.content);
            this.messageCallback({
              role: 'user',
              content: data.content,
            });
          } else if (data.type === 'system' && this.messageCallback) {
            console.log('Trovato messaggio di sistema WebSocket:', data.content);
            // Aggiungiamo messaggio di sistema per debugging
            this.messageCallback({
              role: 'assistant',
              content: `💻 **Sistema:** ${data.content}`,
            });
          } else if (data.type === 'pong') {
            console.log('Ricevuto pong dal server:', data);
          } else if (data.type === 'error') {
            console.error('WebSocket error response:', data.content);
            
            // Notifichiamo l'errore all'utente
            if (this.messageCallback) {
              this.messageCallback({
                role: 'assistant',
                content: `⚠️ **Errore di comunicazione con il server**\n\n${data.content}`,
              });
            }
          } else {
            console.warn('Tipo di messaggio WebSocket non gestito:', data);
          }
        } catch (error) {
          console.error('Error parsing WebSocket response:', error);
        }
      };
    } catch (error) {
      console.error('Error initializing WebSocket:', error);
      onDisconnect();
    }
    
    return () => {
      console.log('Cleaning up WebSocket connection');
      if (this.socket) {
        this.socket.close();
        this.socket = null;
        this.messageCallback = null;
      }
    };
  }

  // Invia un messaggio al server tramite WebSocket
  sendMessageWs(messages: Message[]) {
    if (!this.socket) {
      console.error('WebSocket not initialized');
      throw new Error('WebSocket connection not initialized');
    }
    
    if (this.socket.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not open, current state:', this.socket.readyState);
      throw new Error('WebSocket connection not established');
    }

    const payload = {
      type: 'text',
      messages: messages.map(({ role, content }) => ({ role, content })),
    };

    console.log('Sending message via WebSocket:', payload);
    try {
      this.socket.send(JSON.stringify(payload));
      console.log('Message sent successfully');
      
      // Aggiungiamo un messaggio di debug temporaneo
      if (this.messageCallback) {
        this.messageCallback({
          role: 'assistant',
          content: 'Messaggio inviato al server. In attesa di risposta...',
        });
      }
    } catch (err) {
      console.error('Error sending message via WebSocket:', err);
      throw new Error('Failed to send message via WebSocket');
    }
  }

  // Invia un messaggio al server tramite HTTP
  async sendMessage(messages: Message[]): Promise<Message> {
    try {
      console.log('Sending message via HTTP:', messages);
      const response = await axios.post(`${this.baseUrl}/api/send-message`, {
        messages: messages.map(({ role, content }) => ({ role, content })),
      });

      console.log('HTTP response:', response.data);
      return {
        role: 'assistant',
        content: response.data.response,
      };
    } catch (error) {
      console.error('Error sending message via HTTP:', error);
      return {
        role: 'assistant',
        content: 'Sorry, there was an error processing your request.',
      };
    }
  }

  // Invia una richiesta "Think" al server
  async think(messages: Message[]): Promise<Message> {
    try {
      console.log('Sending think request:', messages);
      const response = await axios.post(`${this.baseUrl}/api/think`, {
        messages: messages.map(({ role, content }) => ({ role, content })),
      });

      console.log('Think response:', response.data);
      return {
        role: 'assistant',
        content: `**Summary:**\n${response.data.summary}\n\n**Solution:**\n${response.data.solution}`,
      };
    } catch (error) {
      console.error('Error in think process:', error);
      return {
        role: 'assistant',
        content: 'Sorry, there was an error with the thinking process.',
      };
    }
  }

  // Analizza uno screenshot
  async analyzeScreenshot(file: File): Promise<Message> {
    try {
      console.log('Sending screenshot for analysis, file size:', file.size);
      const formData = new FormData();
      formData.append('file', file);

      const response = await axios.post(`${this.baseUrl}/api/analyze-screenshot`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      console.log('Screenshot analysis response:', response.data);
      return {
        role: 'assistant',
        content: response.data.analysis,
      };
    } catch (error) {
      console.error('Error analyzing screenshot:', error);
      return {
        role: 'assistant',
        content: 'Sorry, there was an error analyzing the screenshot.',
      };
    }
  }

  // Trascrive un file audio
  async transcribeAudio(file: File): Promise<Message> {
    try {
      console.log('Sending audio for transcription, file size:', file.size);
      const formData = new FormData();
      formData.append('file', file);

      const response = await axios.post(`${this.baseUrl}/api/transcribe-audio`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      console.log('Audio transcription response:', response.data);
      return {
        role: 'user',
        content: response.data.transcription,
      };
    } catch (error) {
      console.error('Error transcribing audio:', error);
      return {
        role: 'user',
        content: 'Sorry, there was an error transcribing the audio.',
      };
    }
  }

  // Invia un ping per testare la connessione WebSocket
  sendPing() {
    if (!this.socket) {
      console.error('WebSocket not initialized');
      return false;
    }
    
    if (this.socket.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not open, current state:', this.socket.readyState);
      return false;
    }
    
    console.log('Sending ping via WebSocket...');
    
    // Debug info to help diagnose the problem
    const debug = {
      socketReadyState: this.socket.readyState,
      socketBufferedAmount: this.socket.bufferedAmount,
      timestamp: new Date().toISOString(),
      clientInfo: {
        userAgent: navigator.userAgent,
        platform: navigator.platform
      }
    };
    
    try {
      const pingPayload = {
        type: 'ping',
        timestamp: new Date().toISOString(),
        debug: debug
      };
      
      console.log('Ping payload:', pingPayload);
      this.socket.send(JSON.stringify(pingPayload));
      console.log('Ping sent successfully');
      
      // Add a timeout to detect if we don't get a response
      setTimeout(() => {
        console.log('Checking for ping response...');
        // We don't send a message here, just log to console
      }, 2000);
      
      return true;
    } catch (error) {
      console.error('Error sending ping:', error);
      return false;
    }
  }

  // Nuovo metodo per inviare audio in streaming tramite WebSocket
  sendAudioStreamWs(base64Audio: string): boolean {
    if (!this.socket) {
      console.error('WebSocket not initialized');
      return false;
    }
    
    if (this.socket.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not open, current state:', this.socket.readyState);
      return false;
    }

    const payload = {
      type: 'audio',
      audio: base64Audio,
      timestamp: new Date().toISOString()
    };

    console.log('Sending audio via WebSocket');
    try {
      this.socket.send(JSON.stringify(payload));
      console.log('Audio sent successfully via WebSocket');
      return true;
    } catch (err) {
      console.error('Error sending audio via WebSocket:', err);
      return false;
    }
  }
}

// Esporta un'istanza singleton del servizio
export const apiService = new ApiService(); 