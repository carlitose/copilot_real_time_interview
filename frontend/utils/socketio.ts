/**
 * Modulo per la gestione dello streaming audio tramite Socket.IO
 */
import { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';

// URL di connessione per Socket.IO
const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://127.0.0.1:8000';

// Interfaccia per il controllo dello stream audio
export interface AudioStreamControl {
  start: () => void;
  stop: () => void;
  isActive: boolean;
}

/**
 * Hook personalizzato per gestire lo streaming audio
 * @param sessionId ID della sessione
 * @returns Controlli per lo stream audio (start, stop, isActive)
 */
export function useAudioStream(sessionId: string): AudioStreamControl {
  const socketRef = useRef<Socket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<any>(null);
  const [isActive, setIsActive] = useState(false);
  const sessionIdRef = useRef<string>(sessionId);
  
  // Aggiorna il riferimento al sessionId quando cambia
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);
  
  // Inizializza Socket.IO
  useEffect(() => {
    if (!socketRef.current) {
      socketRef.current = io(SOCKET_URL);
      
      socketRef.current.on('connect', () => {
        console.log('Socket.IO connesso con successo');
      });
      
      socketRef.current.on('disconnect', () => {
        console.log('Socket.IO disconnesso');
        setIsActive(false);
      });
    }
    
    // Pulizia alla dismissione del componente
    return () => {
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
      
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
        mediaStreamRef.current = null;
      }
      
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
    };
  }, []);
  
  /**
   * Avvia la registrazione audio e lo streaming al server
   */
  const startRecording = async () => {
    try {
      if (!socketRef.current) {
        throw new Error('Socket.IO non inizializzato');
      }
      
      // Richiedi l'accesso al microfono
      mediaStreamRef.current = await navigator.mediaDevices.getUserMedia({ 
        audio: { 
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });
      
      // Configura l'AudioContext
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = audioContext.createMediaStreamSource(mediaStreamRef.current);
      
      // Crea un processor node per campionare l'audio
      processorRef.current = audioContext.createScriptProcessor(4096, 1, 1);
      
      // Callback chiamata quando arrivano nuovi dati audio
      processorRef.current.onaudioprocess = (e: AudioProcessingEvent) => {
        if (!socketRef.current || !isActive) return;
        
        // Ottieni i dati audio dal canale sinistro
        const inputData = e.inputBuffer.getChannelData(0);
        
        // Converti i dati in un array standard
        const audioData = Array.from(inputData);
        
        try {
          // Invia i dati audio al server
          socketRef.current.emit('audio_data', sessionIdRef.current, audioData);
        } catch (error) {
          console.error('Errore nell\'invio dei dati audio:', error);
        }
      };
      
      // Connetti il processor all'audio graph
      source.connect(processorRef.current);
      processorRef.current.connect(audioContext.destination);
      
      setIsActive(true);
      console.log('Registrazione audio avviata');
    } catch (error) {
      console.error('Errore nell\'avvio della registrazione audio:', error);
      setIsActive(false);
    }
  };
  
  /**
   * Interrompe la registrazione audio e lo streaming
   */
  const stopRecording = () => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
    
    setIsActive(false);
    console.log('Registrazione audio fermata');
  };
  
  return {
    start: startRecording,
    stop: stopRecording,
    isActive
  };
} 