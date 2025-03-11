/**
 * Module for handling audio streaming via Socket.IO
 */
import { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';

// Connection URL for Socket.IO
const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://127.0.0.1:8000';

// Interface for audio stream control
export interface AudioStreamControl {
  start: () => void;
  stop: () => void;
  isActive: boolean;
}

/**
 * Custom hook for handling audio streaming
 * @param sessionId Session ID
 * @returns Audio stream controls (start, stop, isActive)
 */
export function useAudioStream(sessionId: string): AudioStreamControl {
  const socketRef = useRef<Socket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<any>(null);
  const [isActive, setIsActive] = useState(false);
  const sessionIdRef = useRef<string>(sessionId);
  
  // Add a ref to track the active state independently from React state
  const isActiveRef = useRef<boolean>(false);
  
  // Update the sessionId reference when it changes
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);
  
  // Initialize Socket.IO
  useEffect(() => {
    if (!socketRef.current) {
      console.log(`[SOCKET.IO] Initializing Socket.IO for session ${sessionId}`);
      socketRef.current = io(SOCKET_URL);
      
      socketRef.current.on('connect', () => {
        console.log(`[SOCKET.IO] Successfully connected [ID: ${socketRef.current?.id}] for session ${sessionId}`);
      });
      
      socketRef.current.on('disconnect', () => {
        console.log('[SOCKET.IO] Disconnected');
        setIsActive(false);
        isActiveRef.current = false; // Update the ref as well
      });

      socketRef.current.on('error', (error: any) => {
        console.error('[SOCKET.IO] Error:', error);
      });

      socketRef.current.on('connect_error', (error: any) => {
        console.error('[SOCKET.IO] Connection error:', error);
      });
    }
    
    // Cleanup when component unmounts
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
  
  // Register timestamp of last audio processing
  const lastProcessTimestampRef = useRef<number>(Date.now());
  
  /**
   * Start audio recording and streaming to the server
   */
  const startRecording = async () => {
    try {
      if (!socketRef.current) {
        throw new Error('[AUDIO] Socket.IO not initialized');
      }

      console.log(`[AUDIO] Starting audio recording for session ${sessionIdRef.current}`);
      console.log(`[SOCKET.IO] Connection status: ${socketRef.current.connected ? 'Connected' : 'Disconnected'}`);
      
      // Set isActive to true at the beginning, before any other operation
      // Update both React state and the ref
      setIsActive(true);
      isActiveRef.current = true;
      console.log(`[AUDIO] isActive flag set to true before starting recording`);
      
      // TEST MODE: Send test data every second to verify the connection
      const TEST_MODE = false;
      
      if (TEST_MODE) {
        console.log('[AUDIO TEST] Starting test mode for audio streaming');
        
        // Send test data every second
        const testInterval = setInterval(() => {
          // Use the ref instead of the state
          if (!socketRef.current || !socketRef.current.connected || !isActiveRef.current) {
            console.log('[AUDIO TEST] Stopping test interval');
            clearInterval(testInterval);
            console.log('[AUDIO TEST] Test interval cleared');
            return;
          }
          
          const testData = [1000, 2000, 3000, 4000, 5000];
          console.log(`[AUDIO TEST] Sending test data: ${testData.length} samples`);
          
          socketRef.current.emit('audio_data', sessionIdRef.current, testData, (acknowledgement: any) => {
            if (acknowledgement && acknowledgement.received) {
              console.log(`[AUDIO TEST] Server confirmed receipt of test data`);
              if (acknowledgement.samples) {
                console.log(`[AUDIO TEST] Server processed ${acknowledgement.samples} samples`);
              }
            } else {
              console.error('[AUDIO TEST] Server did not confirm receipt', acknowledgement);
              if (acknowledgement && acknowledgement.error) {
                console.error(`[AUDIO TEST] Error: ${acknowledgement.error}`);
              }
            }
          });
        }, 1000);
        
        // Save interval to clear it when recording stops
        (window as any).testAudioInterval = testInterval;
        
        // Remove this isActive setting as we already set it at the beginning
        // setIsActive(true);
        return;
      }
      
      // Check microphone permission - improved version
      try {
        console.log('[AUDIO] Explicitly requesting microphone permissions...');
        
        // Clearer message for the user
        console.log('[AUDIO] Checking microphone access...');
        
        // First attempt to request the microphone with explicit options
        const stream = await navigator.mediaDevices.getUserMedia({ 
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          } 
        });
        console.log('[AUDIO] Microphone permission granted!', stream.getAudioTracks());
        
        // Verify that the stream has active audio tracks
        const audioTracks = stream.getAudioTracks();
        if (audioTracks.length === 0) {
          console.error('[AUDIO] No audio tracks available after obtaining permissions');
          throw new Error('No audio tracks available');
        }
        
        console.log('[AUDIO] Available audio tracks:', audioTracks.map(track => ({
          label: track.label,
          enabled: track.enabled,
          muted: track.muted,
          readyState: track.readyState
        })));
        
        // Do not close the stream but reuse it instead of creating a new one
        mediaStreamRef.current = stream;
        console.log('[AUDIO] Microphone stream activated successfully');
        
      } catch (err) {
        console.error('[AUDIO] Error attempting to obtain microphone permissions:', err);
        alert('Please grant microphone permissions to continue with audio recording.');
        throw new Error('Microphone permission denied or device not available');
      }
      
      // Do not request a new stream as we already have the one obtained previously
      // mediaStreamRef.current is already set
      
      // Set up AudioContext
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 24000  // Set to 24kHz as required by OpenAI
      });
      
      // Make sure audioContext is running
      if (audioContext.state !== 'running') {
        console.log(`AudioContext not running, current state: ${audioContext.state}. Attempting to start...`);
        await audioContext.resume();
        console.log(`AudioContext now in state: ${audioContext.state}`);
      }
      
      console.log(`[AUDIO] AudioContext configured with sampling rate: ${audioContext.sampleRate}Hz`);
      
      const source = audioContext.createMediaStreamSource(mediaStreamRef.current);
      
      // Create a processor node to sample audio - increase buffer size for more data
      processorRef.current = audioContext.createScriptProcessor(8192, 1, 1);  // From 4096 to 8192 for larger data chunks
      
      // Buffer to accumulate audio data
      let audioAccumulatorRef: Int16Array[] = [];
      const minimumAudioLength = 12000; // 500ms of audio at 24kHz (24000 * 0.5)
      
      // Callback called when new audio data arrives
      processorRef.current.onaudioprocess = (e: AudioProcessingEvent) => {
        const now = Date.now();
        // Log every 3 seconds to verify the function is being called
        if (now - lastProcessTimestampRef.current > 3000) {
          console.log(`[AUDIO DEBUG] onaudioprocess active, last process: ${new Date(lastProcessTimestampRef.current).toISOString()}`);
          lastProcessTimestampRef.current = now;
        }
        
        // Use the ref instead of the state
        if (!socketRef.current || !isActiveRef.current) {
          console.log(`Audio processor active but conditions not met: socketRef.current=${!!socketRef.current}, isActiveRef.current=${isActiveRef.current}`);
          return;
        }
        
        // Get audio data from the left channel
        const inputData = e.inputBuffer.getChannelData(0);
        
        // Verify there is audio data
        const hasAudioData = inputData.some(value => Math.abs(value) > 0.01);
        if (!hasAudioData) {
          // Don't log all the time to avoid spam, but check periodically
          if (Math.random() < 0.05) { // Log only in 5% of cases
            console.log('No significant audio data detected');
          }
          return; // Don't send data if there's no significant audio
        }
        
        try {
          // DEBUG: Log more complete information about audio data
          const maxValue = Math.max(...Array.from(inputData).map(Math.abs));
          console.log(`[AUDIO DEBUG] Audio data detected. Max amplitude: ${maxValue.toFixed(5)}`);
          
          // Convert Float32Array to Int16Array (more common format for audio)
          // The backend expects an array of numbers or binary data
          const scaledData = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            // Scale from [-1.0, 1.0] to [-32768, 32767]
            scaledData[i] = Math.max(-32768, Math.min(32767, Math.round(inputData[i] * 32767)));
          }
          
          // CRUCIAL: Verify that scaled data actually contains non-zero values
          const nonZeroCount = Array.from(scaledData).filter(v => v !== 0).length;
          console.log(`[AUDIO DEBUG] Non-zero audio data: ${nonZeroCount}/${scaledData.length} (${((nonZeroCount/scaledData.length)*100).toFixed(2)}%)`);
          
          if (nonZeroCount < 10) {
            console.log('[AUDIO DEBUG] Too few significant audio data, skipping this frame');
            return;
          }
          
          // Add to the accumulation buffer
          audioAccumulatorRef.push(scaledData);
          
          // Calculate the total accumulated samples
          const totalSamples = audioAccumulatorRef.reduce((sum, array) => sum + array.length, 0);
          
          // Verify if we have enough audio data (at least 200ms)
          if (totalSamples < minimumAudioLength) {
            console.log(`[AUDIO DEBUG] Accumulated ${totalSamples}/${minimumAudioLength} samples, continuing to accumulate...`);
            return;
          }
          
          // Now we have enough data, we can send it
          // Merge all fragments into a single array
          const mergedArray = new Int16Array(totalSamples);
          let offset = 0;
          
          for (const array of audioAccumulatorRef) {
            mergedArray.set(array, offset);
            offset += array.length;
          }
          
          // Final verification that there is enough data
          if (mergedArray.length < minimumAudioLength) {
            console.log(`[AUDIO WARNING] Merged buffer too small (${mergedArray.length}/${minimumAudioLength}), skipping`);
            return;
          }
          
          // Convert data to a standard JavaScript array for sending
          const audioData = Array.from(mergedArray);
          
          // Calculate the duration in ms
          const audioDurationMs = (audioData.length / audioContext.sampleRate) * 1000;
          console.log(`[AUDIO DEBUG] Sending ${audioData.length} samples (${audioDurationMs.toFixed(2)}ms of audio at ${audioContext.sampleRate}Hz)`);
          
          // Send audio data to server
          const avgAmplitude = audioData.reduce((sum, val) => sum + Math.abs(val), 0) / audioData.length;
          console.log(`Sending audio data: ${audioData.length} samples for session ${sessionIdRef.current}, average amplitude: ${avgAmplitude}, format: PCM 16-bit`);
          
          // Verify socket.io connection before sending
          if (!socketRef.current.connected) {
            console.error(`[AUDIO ERROR] Socket.IO not connected before sending! Attempting to reconnect...`);
            socketRef.current.connect();
            return;
          }
          
          // Direct sending and verification
          console.log(`[AUDIO DEBUG] Sending audio data to server with event 'audio_data', sessionId=${sessionIdRef.current}`);
          // Print the first 10 values for debug
          console.log(`[AUDIO DEBUG] First 10 values: [${audioData.slice(0, 10).join(', ')}]`);
          
          socketRef.current.emit('audio_data', sessionIdRef.current, audioData, (acknowledgement: any) => {
            if (acknowledgement && acknowledgement.received) {
              console.log(`[AUDIO SUCCESS] Server confirmed receipt of ${audioData.length} samples`);
              if (acknowledgement.samples) {
                console.log(`[AUDIO SUCCESS] Server processed ${acknowledgement.samples} samples`);
              }
            } else if (acknowledgement && acknowledgement.error) {
              console.error(`[AUDIO ERROR] Server reported error: ${acknowledgement.error}`);
            } else {
              console.log(`[AUDIO WARNING] No proper acknowledgement from server`, acknowledgement);
            }
          });
          
          // Reset accumulation buffer
          audioAccumulatorRef = [];
          
          // Add a timeout to check if the server responds
          setTimeout(() => {
            console.log(`[AUDIO CHECK] It's been 1 second since the last audio data batch was sent`);
          }, 1000);
          
        } catch (error) {
          console.error('Error sending audio data:', error);
        }
      };

      // Connect the audio nodes
      source.connect(processorRef.current);
      processorRef.current.connect(audioContext.destination);
      
      // Set active flag
      setIsActive(true);
      console.log('Audio recording started successfully');
      
    } catch (error) {
      console.error('Error during audio recording:', error);
    }
  };

  return {
    start: startRecording,
    stop: () => {
      // Implement logic to stop audio recording
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
      
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
        mediaStreamRef.current = null;
      }
      
      // Clear test interval if in test mode
      if ((window as any).testAudioInterval) {
        clearInterval((window as any).testAudioInterval);
        (window as any).testAudioInterval = null;
        console.log('[AUDIO TEST] Test interval cleared');
      }
      
      // Update both React state and the ref
      setIsActive(false);
      isActiveRef.current = false;
      console.log('Audio recording stopped');
    },
    isActive
  };
}