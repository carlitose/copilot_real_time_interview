import { useState, useEffect, useRef, useCallback } from 'react';
import { 
  TranscriptionUpdate, 
  ResponseUpdate, 
  ErrorUpdate, 
  Message 
} from '@/app/types/chat';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

interface EventStreamHookProps {
  sessionId: string | null;
  isSessionActive: boolean;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
}

interface EventStreamHookResult {
  isConnected: boolean;
  isStreamError: boolean;
  cleanupStream: (() => void) | null;
}

export function useEventStream({
  sessionId,
  isSessionActive,
  setMessages
}: EventStreamHookProps): EventStreamHookResult {
  const [isConnected, setIsConnected] = useState(false);
  const [isStreamError, setIsStreamError] = useState<boolean>(false);
  const [cleanupStream, setCleanupStream] = useState<(() => void) | null>(null);
  
  // Ref for EventSource
  const eventSourceRef = useRef<EventSource | null>(null);

  // Callback to handle transcription updates
  const handleTranscription = useCallback((update: TranscriptionUpdate) => {
    console.log(`Received transcription update: ${update.text}`);
    // We do nothing with the transcription for now
  }, []);

  // Callback to handle model responses
  const handleResponse = useCallback((update: ResponseUpdate) => {
    console.log(`Received response from server: ${update.text}`);
    console.log(`Is final response: ${update.final ? 'yes' : 'no'}`);
    
    setMessages(prevMessages => {
      console.log(`Current messages count: ${prevMessages.length}`);
      
      // Find the last assistant message
      const lastAssistantIndex = [...prevMessages].reverse().findIndex(m => m.role === 'assistant');
      console.log(`Last assistant message index: ${lastAssistantIndex !== -1 ? prevMessages.length - 1 - lastAssistantIndex : 'none'}`);
      
      // If there's already an assistant message and it's not the final response,
      // update that message instead of adding a new one
      if (lastAssistantIndex !== -1 && !update.final) {
        const reversedIndex = lastAssistantIndex;
        const actualIndex = prevMessages.length - 1 - reversedIndex;
        
        console.log(`Updating existing assistant message at index: ${actualIndex}`);
        
        const newMessages = [...prevMessages];
        newMessages[actualIndex] = {
          ...newMessages[actualIndex],
          content: update.text
        };
        return newMessages;
      }
      
      // Find and remove any waiting message if this is a screenshot response
      if (update.text.includes("screenshot") || update.text.includes("screen")) {
        // Look for a temporary message about screenshot or screen
        const waitingMsgIndex = prevMessages.findIndex(m => 
          (m.role === 'log' || m.role === 'assistant') && 
          (m.content.includes('Capturing') || 
           m.content.includes('Screenshot') || 
           m.content.includes('screen') ||
           m.content.includes('analyzing'))
        );
        
        if (waitingMsgIndex !== -1) {
          console.log(`Found waiting message at index: ${waitingMsgIndex}, replacing it`);
          const newMessages = [...prevMessages];
          
          newMessages[waitingMsgIndex] = {
            role: 'assistant',
            content: update.text
          };
          return newMessages;
        }
      }
      
      return [...prevMessages, {
        role: 'assistant',
        content: update.text
      }];
    });
  }, [setMessages]);

  // Callback to handle errors
  const handleError = useCallback((update: ErrorUpdate) => {
    console.error(`Error received from stream: ${update.message}`);
    setIsStreamError(true);
  }, []);

  // Callback to handle connection errors
  const handleConnectionError = useCallback((error: Event) => {
    console.error("Stream connection error:", error);
    setIsStreamError(true);
  }, []);

  // Callback to handle connection status
  const handleConnectionStatus = useCallback((connected: boolean) => {
    console.log(`Stream connection status: ${connected ? 'connected' : 'disconnected'}`);
    setIsConnected(connected);
  }, []);

  // Effect to set up and clean up event stream
  useEffect(() => {
    // Cleanup any existing EventSource
    if (eventSourceRef.current) {
      console.log('Closing existing EventSource');
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    if (sessionId && isSessionActive) {
      console.log(`Setting up SSE stream for session ${sessionId}`);
      
      try {
        // Create EventSource for SSE
        const eventSourceUrl = `${API_BASE_URL}/sessions/stream?session_id=${sessionId}`;
        console.log(`Connecting to SSE endpoint: ${eventSourceUrl}`);
        
        const eventSource = new EventSource(eventSourceUrl);
        eventSourceRef.current = eventSource;
        
        console.log("EventSource created:", eventSource);
        
        // Setup message handler
        eventSource.onmessage = (event) => {
          console.log(`[DEBUG] Raw SSE message received:`, event.data);
          
          try {
            const data = JSON.parse(event.data);
            console.log(`[DEBUG] Parsed SSE data:`, data);
            
            if (data.type === 'response') {
              handleResponse({
                type: 'response',
                text: data.text,
                session_id: data.session_id,
                final: data.final || true
              });
            } else if (data.type === 'transcription') {
              handleTranscription({
                type: 'transcription',
                text: data.text,
                session_id: data.session_id
              });
            } else if (data.type === 'error') {
              handleError({
                type: 'error',
                message: data.message,
                session_id: data.session_id
              });
            } else if (data.type === 'connection') {
              handleConnectionStatus(data.connected);
            } else if (data.type === 'log') {
              // Handling log messages from the backend
              setMessages(prev => {
                // Look for an existing and similar log message
                const logIndex = prev.findIndex(m => 
                  m.role === 'log' && 
                  (m.content.includes('Analyzing') || 
                   m.content.includes('Capturing') || 
                   m.content.includes('Screenshot'))
                );
                
                if (logIndex !== -1) {
                  // Update the existing log message
                  const newMessages = [...prev];
                  newMessages[logIndex] = { role: 'log', content: data.text };
                  return newMessages;
                } else {
                  // Add a new log message
                  return [...prev, { role: 'log', content: data.text }];
                }
              });
            } else if (data.type === 'heartbeat') {
              console.log(`[DEBUG] Heartbeat received: ${data.timestamp}`);
            }
          } catch (error) {
            console.error('[DEBUG] Error parsing SSE data:', error);
          }
        };
        
        // Setup error handler
        eventSource.onerror = (error) => {
          console.error('[DEBUG] EventSource error:', error);
          handleConnectionError(error);
        };
        
        // Setup open handler
        eventSource.onopen = () => {
          console.log('[DEBUG] EventSource connection opened');
          handleConnectionStatus(true);
        };
        
        // Save cleanup function
        setCleanupStream(() => {
          return () => {
            console.log('[DEBUG] Cleaning up EventSource');
            if (eventSourceRef.current) {
              eventSourceRef.current.close();
              eventSourceRef.current = null;
            }
          };
        });
      } catch (error) {
        console.error('[DEBUG] Error setting up SSE stream:', error);
        setIsStreamError(true);
      }
    }
    
    // Cleanup function
    return () => {
      console.log('Cleaning up SSE stream on component unmount');
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [
    sessionId,
    isSessionActive,
    handleTranscription,
    handleResponse,
    handleError,
    handleConnectionStatus,
    handleConnectionError,
    setMessages
  ]);

  return {
    isConnected,
    isStreamError,
    cleanupStream
  };
} 