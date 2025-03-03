#!/usr/bin/env python3

import time
import json
import queue
import logging
import threading
import numpy as np
from web_realtime_text_thread import WebRealtimeTextThread

logger = logging.getLogger(__name__)

class WebSocketRealtimeTextThread(WebRealtimeTextThread):
    """Versione di WebRealtimeTextThread che accetta audio da WebSocket anziché dal microfono locale."""
    
    def __init__(self, callbacks=None):
        super().__init__(callbacks)
        self.external_audio_queue = queue.Queue(maxsize=100)  # Limita la dimensione per evitare memory leak
        self.use_external_audio = True
        self.process_thread = None
    
    def start_recording(self):
        """Override che non avvia la registrazione locale ma attende dati dal WebSocket."""
        with self.lock:
            if self.recording:
                return
            self.recording = True
        
        self.audio_buffer = []
        self.accumulated_audio = b''
        
        # Non inizializziamo PyAudio, ma avviamo il thread di elaborazione
        if self.use_external_audio:
            self.process_thread = threading.Thread(target=self._process_external_audio, daemon=True)
            self.process_thread.start()
            
            self.emit_transcription("Registrazione avviata... Parla ora.")
            return
        
        # Fallback alla registrazione normale se necessario
        super().start_recording()
    
    def stop_recording(self):
        """Override per fermare la registrazione."""
        with self.lock:
            if not self.recording:
                return
            self.recording = False
        
        # Non abbiamo PyAudio da chiudere, ma dobbiamo gestire la coda
        if self.use_external_audio:
            # Svuota la coda e aggiunge un marker di fine
            try:
                while not self.external_audio_queue.empty():
                    self.external_audio_queue.get_nowait()
                self.external_audio_queue.put(None)  # Segnala la fine
            except:
                pass
            
            # Procedi con il commit dell'audio accumulato
            with self.lock:
                has_connection = self.connected and self.websocket
                has_audio = bool(self.accumulated_audio)
            
            if has_connection and has_audio:
                self._send_entire_audio_message()
                commit_message = {"type": "input_audio_buffer.commit"}
                self.websocket.send(json.dumps(commit_message))
            
            return
        
        # Fallback all'implementazione normale
        super().stop_recording()
    
    def add_audio_data(self, audio_data):
        """Metodo pubblico per aggiungere dati audio dalla connessione WebSocket."""
        if not self.recording:
            logger.warning("add_audio_data chiamato ma recording è False")
            return False
        
        try:
            # Verifica del tipo e dimensione dei dati
            data_type = type(audio_data).__name__
            data_size = len(audio_data) if audio_data else 0
            logger.debug(f"add_audio_data: ricevuti {data_size} bytes, tipo {data_type}")
            
            # Verifica che i dati siano in formato binario
            if not isinstance(audio_data, bytes):
                logger.warning(f"add_audio_data: formato non valido, attesi bytes ma ricevuto {data_type}")
                try:
                    # Tentativo di conversione
                    audio_data = bytes(audio_data)
                    logger.debug(f"add_audio_data: conversione a bytes riuscita, nuova dimensione {len(audio_data)}")
                except Exception as e:
                    logger.error(f"add_audio_data: impossibile convertire a bytes: {str(e)}")
                    return False
            
            # Aggiungi i dati alla coda, con timeout per evitare blocchi
            self.external_audio_queue.put(audio_data, timeout=0.5)
            return True
        except queue.Full:
            logger.warning("add_audio_data: coda piena, dati scartati")
            return False
        except Exception as e:
            logger.error(f"add_audio_data: errore non previsto: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _process_external_audio(self):
        """Elabora i dati audio ricevuti dal WebSocket."""
        try:
            self.last_commit_time = time.time()
            logger.info("Avvio elaborazione audio WebSocket")
            
            while True:
                with self.lock:
                    if not self.recording:
                        logger.info("Registrazione fermata, uscita dal ciclo di elaborazione")
                        break
                
                try:
                    # Attendi dati dalla coda con timeout
                    audio_data = self.external_audio_queue.get(timeout=0.1)
                    
                    # None indica fine della registrazione
                    if audio_data is None:
                        logger.info("Ricevuto None nella coda, terminazione elaborazione")
                        break
                    
                    # Log dei dati ricevuti
                    data_size = len(audio_data) if audio_data else 0
                    logger.debug(f"Elaborazione di {data_size} bytes di dati audio")
                    
                    # Aggiungi i dati ai buffer
                    self.audio_buffer.append(audio_data)
                    self.accumulated_audio += audio_data
                    
                    # Calcola RMS e gestisci il rilevamento del parlato
                    try:
                        rms = self._calculate_rms(audio_data)
                        logger.debug(f"RMS calcolato: {rms} (threshold: {self.silence_threshold})")
                    except Exception as e:
                        logger.error(f"Errore nel calcolo RMS: {str(e)}")
                        rms = 0
                    
                    current_time = time.time()
                    
                    # Logica di rilevamento del parlato (come nella versione originale)
                    if rms > self.silence_threshold:
                        if not self.is_speaking:
                            logger.info(f"Speech start detected (RMS: {rms})")
                            self.is_speaking = True
                        self.silence_start_time = 0
                    else:
                        if self.is_speaking:
                            if self.silence_start_time == 0:
                                self.silence_start_time = current_time
                            elif current_time - self.silence_start_time > self.silence_duration_threshold:
                                logger.info(f"Speech end detected (silence duration: {current_time - self.silence_start_time}s)")
                                self.is_speaking = False
                                self.silence_start_time = 0
                    
                    # Logica per l'invio dei dati accumulati per la trascrizione
                    if (current_time - self.last_commit_time >= self.commit_interval or
                        not self.is_speaking and len(self.audio_buffer) > 0):
                        
                        # Calcola dimensioni totali
                        total_size = sum(len(chunk) for chunk in self.audio_buffer)
                        logger.info(f"Invio di {total_size} bytes di audio per la trascrizione")
                        
                        # Invia i dati all'API OpenAI
                        if len(self.accumulated_audio) > 0:
                            self._send_audio_for_transcription()
                        
                        # Resetta i buffer
                        self.last_commit_time = current_time
                        self.accumulated_audio = b''
                        self.audio_buffer = []
                        
                except queue.Empty:
                    # Timeout della coda, continua il ciclo
                    pass
                except Exception as e:
                    logger.error(f"Errore durante l'elaborazione audio: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info("Thread di elaborazione audio terminato")
        except Exception as e:
            logger.error(f"Errore critico nel thread di elaborazione: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _calculate_rms(self, audio_data):
        """Calcola il valore RMS (Root Mean Square) dei dati audio."""
        try:
            # Converti i dati audio in un array numpy
            # Assumiamo che i dati siano in formato Int16 (16 bit)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            if len(audio_array) == 0:
                return 0
            
            # Calcola RMS
            rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2))
            return rms
        except Exception as e:
            logger.error(f"Error calculating RMS: {str(e)}")
            return 0 