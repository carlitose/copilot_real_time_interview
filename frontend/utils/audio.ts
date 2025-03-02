import { apiService } from './api';

/**
 * Classe per gestire la registrazione audio nel browser
 */
export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private isRecording: boolean = false;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private silenceDetector: SilenceDetector | null = null;
  private streamingIntervalId: number | null = null;

  // Configurazione per il rilevamento delle pause e l'invio periodico
  private readonly CHUNK_INTERVAL_MS = 1000; // Intervallo di invio ogni 1 secondo
  private readonly MIN_CHUNK_SIZE = 3200; // Dimensione minima del chunk prima di inviarlo

  /**
   * Inizializza il recorder richiedendo l'accesso al microfono
   */
  async initialize(): Promise<void> {
    try {
      console.log('Initializing audio recorder');
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Specifica il formato audio supportato da OpenAI (audio/wav)
      const options = { mimeType: 'audio/wav' };
      
      // Verifica se il formato è supportato, altrimenti usa un fallback
      if (MediaRecorder.isTypeSupported('audio/wav')) {
        this.mediaRecorder = new MediaRecorder(this.stream, options);
        console.log('Utilizzando formato audio WAV');
      } else if (MediaRecorder.isTypeSupported('audio/webm')) {
        this.mediaRecorder = new MediaRecorder(this.stream, { mimeType: 'audio/webm' });
        console.log('Utilizzando formato audio WebM (fallback)');
      } else {
        // Usa il formato predefinito
        this.mediaRecorder = new MediaRecorder(this.stream);
        console.log('Utilizzando formato audio predefinito');
      }

      // Inizializza l'analizzatore audio per il rilevamento delle pause
      this.audioContext = new AudioContext();
      const source = this.audioContext.createMediaStreamSource(this.stream);
      this.analyser = this.audioContext.createAnalyser();
      source.connect(this.analyser);
      
      // Inizializza il rilevatore di silenzio
      this.silenceDetector = new SilenceDetector(this.analyser);

      console.log('Audio recorder initialized successfully');
      
      // Configura l'event listener per i dati audio disponibili
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
          // Salva il chunk per l'invio in streaming
          this._processPendingAudioChunk(event.data);
        }
      };
    } catch (error) {
      console.error('Error initializing audio recorder:', error);
      throw new Error(`Failed to initialize audio recorder: ${error}`);
    }
  }

  /**
   * Avvia la registrazione audio
   */
  startRecording(): void {
    if (!this.mediaRecorder) {
      throw new Error('Audio recorder not initialized');
    }

    if (this.isRecording) {
      console.warn('Recording already in progress');
      return;
    }

    console.log('Starting audio recording');
    this.audioChunks = [];
    this.isRecording = true;
    this.mediaRecorder.start(100); // Cattura chunk di audio ogni 100ms

    // Avvia l'invio periodico dei chunk audio
    this._startPeriodicSending();

    console.log('Audio recording started');
  }

  /**
   * Ferma la registrazione e restituisce il blob audio
   */
  async stopRecording(): Promise<Blob> {
    if (!this.mediaRecorder || !this.isRecording) {
      throw new Error('No recording in progress');
    }

    console.log('Stopping audio recording');

    // Interrompe l'invio periodico
    this._stopPeriodicSending();

    return new Promise<Blob>((resolve) => {
      this.mediaRecorder!.onstop = async () => {
        console.log('Media recorder stopped');
        this.isRecording = false;
        
        // Verifica se ci sono chunk audio rimanenti da inviare
        if (this.audioChunks.length > 0) {
          const finalBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
          this._sendRemainingAudio(finalBlob);
          resolve(finalBlob);
        } else {
          resolve(new Blob([], { type: 'audio/webm' }));
        }
      };

      this.mediaRecorder!.stop();
    });
  }

  /**
   * Converte un blob audio in un file
   */
  createAudioFile(blob: Blob, filename: string = 'audio.wav'): File {
    return new File([blob], filename, { type: blob.type });
  }

  /**
   * Rilascia le risorse quando non più necessarie
   */
  release(): void {
    console.log('Releasing audio recorder resources');
    this._stopPeriodicSending();
    
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
      this.isRecording = false;
    }

    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }

    this.mediaRecorder = null;
    this.audioChunks = [];
    
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    
    this.analyser = null;
    this.silenceDetector = null;
  }

  /**
   * Verifica se il browser supporta la registrazione audio
   */
  static isSupported(): boolean {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  }

  // Metodi privati per l'invio in streaming

  // Processa un chunk audio appena ricevuto
  private _processPendingAudioChunk(chunk: Blob): void {
    // Se il rilevatore di silenzio indica una pausa, invia immediatamente
    if (this.silenceDetector && this.silenceDetector.isSilence()) {
      console.log('Silence detected, sending audio chunk immediately');
      this._sendAudioChunk(chunk);
    }
  }

  // Avvia l'invio periodico dei chunk audio
  private _startPeriodicSending(): void {
    if (this.streamingIntervalId !== null) {
      clearInterval(this.streamingIntervalId);
    }

    this.streamingIntervalId = window.setInterval(() => {
      if (this.audioChunks.length > 0) {
        // Crea un blob dai chunk accumulati
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        
        // Invia solo se il blob è abbastanza grande
        if (audioBlob.size >= this.MIN_CHUNK_SIZE) {
          console.log(`Sending audio chunk of size ${audioBlob.size} bytes`);
          this._sendAudioChunk(audioBlob);
          // Pulisci i chunk già inviati
          this.audioChunks = [];
        }
      }
    }, this.CHUNK_INTERVAL_MS);
  }

  // Interrompe l'invio periodico
  private _stopPeriodicSending(): void {
    if (this.streamingIntervalId !== null) {
      clearInterval(this.streamingIntervalId);
      this.streamingIntervalId = null;
    }
  }

  // Invia un chunk audio al server
  private _sendAudioChunk(audioBlob: Blob): void {
    try {
      const audioFile = this.createAudioFile(audioBlob, `chunk_${Date.now()}.webm`);
      console.log(`Sending audio chunk: ${audioFile.name}, size: ${audioFile.size} bytes`);
      
      // Invia il file attraverso WebSocket
      this._sendAudioViaWebSocket(audioFile);
      
    } catch (error) {
      console.error('Error sending audio chunk:', error);
    }
  }

  // Invia l'audio rimanente alla fine della registrazione
  private _sendRemainingAudio(audioBlob: Blob): void {
    if (audioBlob.size > 0) {
      console.log(`Sending final audio chunk of size ${audioBlob.size} bytes`);
      this._sendAudioChunk(audioBlob);
    }
  }

  // Invia l'audio tramite WebSocket
  private async _sendAudioViaWebSocket(audioFile: File): Promise<void> {
    try {
      // Converte il file in base64
      const base64Audio = await this._fileToBase64(audioFile);
      
      // Invia tramite metodo apiService.sendAudioStreamWs
      console.log('Sending audio via WebSocket');
      const success = apiService.sendAudioStreamWs(base64Audio);
      
      if (success) {
        console.log('Audio sent successfully via WebSocket');
      } else {
        console.error('Failed to send audio via WebSocket');
      }
    } catch (err) {
      console.error('Error sending audio via WebSocket:', err);
    }
  }
  
  // Converte un file in base64
  private _fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          // Rimuovi il prefisso "data:audio/webm;base64,"
          const base64 = reader.result.split(',')[1];
          resolve(base64);
        } else {
          reject(new Error('Failed to convert file to base64'));
        }
      };
      reader.onerror = error => reject(error);
    });
  }
}

// Classe per il rilevamento del silenzio
class SilenceDetector {
  private analyser: AnalyserNode;
  private readonly SILENCE_THRESHOLD = 10; // Soglia per considerare un suono silenzioso
  private dataArray: Uint8Array;

  constructor(analyser: AnalyserNode) {
    this.analyser = analyser;
    this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
  }

  isSilence(): boolean {
    this.analyser.getByteFrequencyData(this.dataArray);
    
    // Calcola il valore RMS
    let sum = 0;
    for (let i = 0; i < this.dataArray.length; i++) {
      sum += Math.pow(this.dataArray[i], 2);
    }
    const rms = Math.sqrt(sum / this.dataArray.length);
    
    return rms < this.SILENCE_THRESHOLD;
  }
}

// Istanza singleton del recorder
export const audioRecorder = new AudioRecorder(); 