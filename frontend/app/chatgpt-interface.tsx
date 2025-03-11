"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Bug, Mic, MicOff, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef, useCallback } from "react"
import { formatMarkdown } from "@/utils/formatMessage"

// Importing APIs and services
import apiClient, { Message } from "@/utils/api"
import { useAudioStream, AudioStreamControl } from "@/utils/socketio"
import { 
  TranscriptionUpdate, 
  ResponseUpdate, 
  ErrorUpdate
} from "@/utils/eventStream"
import { getAvailableScreens, captureScreenshot, ScreenInfo } from "@/utils/screenCapture"

// Constant for the API base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';
console.log("API base URL:", API_BASE_URL);

export default function ChatGPTInterface() {
  const [isSessionActive, setIsSessionActive] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [selectedScreen, setSelectedScreen] = useState("screen1")
  const [availableScreens, setAvailableScreens] = useState<ScreenInfo[]>([])
  const [isScreenSelectOpen, setIsScreenSelectOpen] = useState(false)
  const [isCapturingScreen, setIsCapturingScreen] = useState(false)
  const [isRecording, setIsRecording] = useState<boolean>(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [audioControl, setAudioControl] = useState<AudioStreamControl | null>(null)
  const [isStreamError, setIsStreamError] = useState<boolean>(false)

  // State to keep track of the SSE cleanup function
  const [cleanupStream, setCleanupStream] = useState<(() => void) | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
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
          
          // Non abbiamo più bisogno di questa logica poiché i messaggi 
          // di log sono ora gestiti separatamente
          newMessages[waitingMsgIndex] = {
            role: 'assistant',
            content: update.text
          };
          return newMessages;
        }
      }
      
      // Non abbiamo più bisogno di questa logica poiché i messaggi 
      // di log sono ora gestiti separatamente
      return [...prevMessages, {
        role: 'assistant',
        content: update.text
      }];
    });
  }, []);

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
              // Gestione dei messaggi di log dal backend
              setMessages(prev => {
                // Cerca un messaggio di log esistente e simile
                const logIndex = prev.findIndex(m => 
                  m.role === 'log' && 
                  (m.content.includes('Analyzing') || 
                   m.content.includes('Capturing') || 
                   m.content.includes('Screenshot'))
                );
                
                if (logIndex !== -1) {
                  // Aggiorna il messaggio di log esistente
                  const newMessages = [...prev];
                  newMessages[logIndex] = { role: 'log', content: data.text };
                  return newMessages;
                } else {
                  // Aggiungi un nuovo messaggio di log
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
    handleConnectionError
  ]);

  // Automatically initialize the session on startup
  useEffect(() => {
    async function initializeSession() {
      try {
        console.log("Creating a new session without automatic start...");
        const newSessionId = await apiClient.createSession();
        console.log(`New session created: ${newSessionId}`);
        setSessionId(newSessionId);
        // Do not automatically start the session
      } catch (error) {
        console.error("Error creating session:", error);
      }
    }
    
    initializeSession();
  }, []);

  // Effect to automatically scroll to the bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  // Handle session start and stop
  const toggleSession = async () => {
    if (isSessionActive) {
      // Stop the session
      console.log("Stopping the session...");
      
      // Stop audio recording if active
      if (isRecording) {
        audioStreamControl.stop();
        setIsRecording(false);
      }
      
      // Clean up streams if necessary
      if (cleanupStream) {
        try {
          cleanupStream();
          setCleanupStream(null);
        } catch (error) {
          console.error("Error cleaning up streams:", error);
        }
      }
      
      // End the session on the server
      if (sessionId) {
        try {
          await apiClient.endSession(sessionId);
        } catch (error) {
          console.error("Error ending session:", error);
        } finally {
          // Reset stream error state
          setIsStreamError(false);
          // Indicate session is inactive
          setIsSessionActive(false);
          // Keep the sessionId for history, but mark as ended
          console.log(`Session ${sessionId} ended.`);
          
          // Aggiungere un messaggio di sistema che indica che la sessione è terminata
          setMessages(prev => [
            ...prev,
            { 
              role: 'system', 
              content: '--- Session ended ---' 
            }
          ]);
        }
      }
    } else {
      // Start a new session
      console.log("Starting a new session...");
      
      // Always create a new session when starting
      try {
        // Create a new session ID every time we start
        const newSessionId = await apiClient.createSession();
        console.log(`New session created: ${newSessionId}`);
        setSessionId(newSessionId);
        
        // Start the new session on the server
        await apiClient.startSession(newSessionId);
        setIsSessionActive(true);
        setIsStreamError(false); // Reset any stream errors
        
        // Aggiungere un messaggio di sistema che indica l'inizio di una nuova sessione
        setMessages(prev => [
          ...prev,
          { 
            role: 'system', 
            content: '--- New session started ---' 
          }
        ]);
        
        // Automatically start audio recording
        console.log("Automatically starting audio recording...");
        
        // Ensure audioStreamControl is properly initialized
        if (audioStreamControl) {
          try {
            audioStreamControl.start();
            console.log("Audio recording started successfully");
            setIsRecording(true);
          } catch (error) {
            console.error("Error starting audio recording:", error);
            alert("There was a problem activating the microphone. Please check your browser permissions.");
          }
        } else {
          console.error("audioStreamControl not properly initialized");
        }
      } catch (error) {
        console.error("Error starting new session:", error);
        alert("Impossibile avviare una nuova sessione. Ricarica la pagina e riprova.");
      }
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !sessionId || !isSessionActive) return;
    
    try {
      // Add the user's message
      setMessages(prev => [...prev, { role: 'user', content: inputMessage }]);
      
      // Add a waiting message from the assistant
      setMessages(prev => [...prev, { role: 'log', content: 'Processing your request...' }]);
      
      // Clear the input
      setInputMessage("");
      
      // Send the text message
      const result = await apiClient.sendTextMessage(sessionId, inputMessage);
      
      if (!result) {
        // Remove the waiting message
        setMessages(prev => prev.slice(0, prev.length - 1));
        
        // Add an error message
        setMessages(prev => [
          ...prev,
          { role: 'log', content: 'An error occurred while sending the message.' }
        ]);
      }
      
      // The response will be handled via SSE events
    } catch (error) {
      console.error("Error sending message:", error);
      
      // Remove the waiting message
      setMessages(prev => prev.slice(0, prev.length - 1));
      
      // Add an error message
      setMessages(prev => [
        ...prev,
        { role: 'log', content: 'An error occurred while sending the message.' }
      ]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleThink = async () => {
    if (!sessionId || !isSessionActive) return;
    
    try {
      // Add a waiting message
      setMessages(prev => [...prev, { role: 'log', content: 'Thinking about this conversation...' }]);
      
      // Start the thinking process
      await apiClient.startThinkProcess(sessionId);
      
      // The response will be handled via SSE events
    } catch (error) {
      console.error("Error starting think process:", error);
      
      // Remove the waiting message
      setMessages(prev => prev.slice(0, prev.length - 1));
      
      // Add an error message
      setMessages(prev => [
        ...prev,
        { role: 'log', content: 'An error occurred during the thinking process.' }
      ]);
    }
  };

  const handleAnalyzeScreenshot = async () => {
    if (!sessionId || !isSessionActive) return;
    
    try {
      setIsCapturingScreen(true);
      
      // Add a waiting message with a unique identifier
      const messageId = `screenshot-${Date.now()}`;
      // @ts-ignore - Adding temporary id for tracking this message
      setMessages(prev => [...prev, { 
        role: 'log', 
        content: 'Capturing and analyzing the screen... (please wait a few seconds)',
        id: messageId 
      }]);
      
      // Capture the screenshot from the browser
      const imageData = await captureScreenshot(selectedScreen);
      
      // Verifica se la connessione è ancora attiva dopo la cattura dello screenshot
      if (!isConnected && isSessionActive && sessionId) {
        console.log("Connection lost after screenshot, attempting to reconnect...");
        
        // Chiudi qualsiasi EventSource esistente
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }
        
        // Ricrea l'EventSource
        try {
          const eventSourceUrl = `${API_BASE_URL}/sessions/stream?session_id=${sessionId}`;
          console.log(`Reconnecting to SSE endpoint: ${eventSourceUrl}`);
          
          const eventSource = new EventSource(eventSourceUrl);
          eventSourceRef.current = eventSource;
          
          // Setup message handler
          eventSource.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
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
                // Gestione dei messaggi di log dal backend
                setMessages(prev => {
                  // Cerca un messaggio di log esistente e simile
                  const logIndex = prev.findIndex(m => 
                    m.role === 'log' && 
                    (m.content.includes('Analyzing') || 
                     m.content.includes('Capturing') || 
                     m.content.includes('Screenshot'))
                  );
                  
                  if (logIndex !== -1) {
                    // Aggiorna il messaggio di log esistente
                    const newMessages = [...prev];
                    newMessages[logIndex] = { role: 'log', content: data.text };
                    return newMessages;
                  } else {
                    // Aggiungi un nuovo messaggio di log
                    return [...prev, { role: 'log', content: data.text }];
                  }
                });
              }
            } catch (error) {
              console.error('Error parsing SSE data:', error);
            }
          };
          
          eventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            handleConnectionError(error);
          };
          
          eventSource.onopen = () => {
            console.log('EventSource connection reopened');
            handleConnectionStatus(true);
          };
        } catch (error) {
          console.error('Error reconnecting to SSE stream:', error);
        }
      }
      
      if (imageData) {
        // Show a preview of the captured screenshot (optional)
        setMessages(prev => prev.map(msg => 
          // @ts-ignore - Using temporary id for tracking
          msg.id === messageId ? 
          { ...msg, content: 'Capturing and analyzing the screen... (image sent to server)' } : 
          msg
        ));
        
        // Send the captured screenshot to the backend
        const success = await apiClient.sendScreenshot(sessionId, imageData);
        
        if (!success) {
          throw new Error("Error sending screenshot to backend");
        }
        
        // Let the user know we're waiting for analysis
        setMessages(prev => prev.map(msg => 
          // @ts-ignore - Using temporary id for tracking
          msg.id === messageId ? 
          { ...msg, content: 'Screenshot sent! Waiting for server analysis...' } : 
          msg
        ));
      } else {
        throw new Error("Unable to capture screenshot");
      }
      
      // The response will be handled via SSE events
    } catch (error) {
      console.error("Error capturing screenshot:", error);
      
      // Add an error message
      setMessages(prev => [
        ...prev,
        { role: 'log', content: `An error occurred while capturing the screenshot: ${error instanceof Error ? error.message : 'Unknown error'}` }
      ]);
    } finally {
      setIsCapturingScreen(false);
    }
  };

  const handleSaveConversation = async () => {
    if (!sessionId) return;
    
    try {
      const conversation = await apiClient.saveConversation(sessionId);
      
      // Create and download the JSON file
      const conversationData = JSON.stringify(conversation, null, 2);
      const blob = new Blob([conversationData], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      
      const a = document.createElement('a');
      a.href = url;
      a.download = `conversation-${sessionId}-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      // Show a confirmation
      setMessages(prev => [
        ...prev,
        { role: 'system', content: 'Conversation saved successfully!' }
      ]);
    } catch (error) {
      console.error("Error saving conversation:", error);
      
      // Show an error message
      setMessages(prev => [
        ...prev,
        { role: 'system', content: 'An error occurred while saving the conversation.' }
      ]);
    }
  };

  const handleClear = () => {
    setMessages([]);
  };

  const handleDeleteMessage = (indexToDelete: number) => {
    setMessages(prevMessages => prevMessages.filter((_, index) => index !== indexToDelete));
  };

  // Initialize audio control with the useAudioStream hook
  const audioStreamControl = useAudioStream(sessionId || '');
  
  // Effect to monitor sessionId changes and update recording state
  useEffect(() => {
    console.log(`sessionId updated: ${sessionId}`);
    // If the session is active and isRecording is true, but audioStreamControl is not active,
    // try to restart the recording
    if (isSessionActive && isRecording && audioStreamControl && !audioStreamControl.isActive) {
      console.log('Attempting to reactivate audio recording after sessionId change');
      try {
        audioStreamControl.start();
      } catch (error) {
        console.error('Error reactivating audio recording:', error);
      }
    }
  }, [sessionId, isSessionActive, isRecording, audioStreamControl]);

  const toggleRecording = () => {
    if (!isSessionActive || !sessionId) {
      alert('Please start a session first.');
      return;
    }
    
    // Use audioStreamControl directly instead of creating it conditionally
    if (!isRecording) {
      console.log('Activating microphone...');
      try {
        audioStreamControl.start();
      } catch (error) {
        console.error('Error activating microphone:', error);
        alert('There was a problem activating the microphone. Make sure you have given the necessary permissions.');
        return;
      }
    } else {
      audioStreamControl.stop();
      console.log('Microphone deactivated.');
    }
    
    setIsRecording(!isRecording);
  };

  // Load available screens when component mounts
  useEffect(() => {
    async function loadScreens() {
      const screens = await getAvailableScreens();
      setAvailableScreens(screens);
      
      if (screens.length > 0) {
        setSelectedScreen(screens[0].id);
      }
    }
    
    // Load screens only once on startup
    loadScreens();
  }, []);

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-50">
      <header className="p-4 border-b border-slate-800 flex justify-between items-center">
        <h1 className="text-xl font-bold">Integrated ChatGPT</h1>
      </header>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message, index) => (
          <div 
            key={index} 
            className={`p-3 rounded-lg max-w-[80%] relative ${
              message.role === 'user' 
                ? 'bg-blue-900 ml-auto' 
                : message.role === 'assistant'
                  ? 'bg-slate-800 group'
                  : message.role === 'log'
                    ? 'bg-slate-600 border border-slate-500 italic'
                    : 'bg-slate-700 mx-auto text-center text-sm font-semibold'
            }`}
          >
            <div dangerouslySetInnerHTML={{ __html: formatMarkdown(message.content) }} />
            {message.role === 'assistant' && (
              <Button
                variant="ghost"
                size="sm"
                className="absolute -top-1 -right-1 h-5 w-5 p-0 rounded-full bg-slate-700 hover:bg-slate-600 opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                onClick={() => handleDeleteMessage(index)}
                title="Delete message"
              >
                <X size={10} className="text-slate-300" />
              </Button>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="p-4 border-t border-slate-800 bg-slate-900">
        <div className="flex items-center space-x-2 mb-2">
          <Button 
            variant="ghost"
            size="sm"
            onClick={toggleSession}
            title={isSessionActive ? "End session" : "Start session"}
          >
            {isSessionActive ? <Square size={16} /> : <Play size={16} />}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleAnalyzeScreenshot}
            disabled={!isSessionActive || isCapturingScreen}
            title="Capture and analyze screen"
          >
            <Camera className="h-4 w-4" />
            {isCapturingScreen && <span className="ml-2">Capturing...</span>}
          </Button>
          <Button 
            variant="ghost" 
            size="sm"
            onClick={handleThink}
            disabled={!isSessionActive}
            title="Think"
          >
            <Brain size={16} />
          </Button>
          <Button 
            variant="ghost" 
            size="sm"
            onClick={handleSaveConversation}
            title="Save conversation"
            disabled={!isSessionActive}
          >
            <Save size={16} />
          </Button>
          <Button 
            variant="ghost" 
            size="sm"
            onClick={handleClear}
            title="Clear chat"
          >
            <Trash2 size={16} />
          </Button>
          <div className="ml-auto text-xs text-slate-400">
            {isConnected ? 'Connected' : 'Disconnected'}
            {isStreamError && ' - Streaming error'}
            {isRecording && ' - 🎤 Recording active'}
          </div>
        </div>
        <div className="flex space-x-2">
          <Input
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            disabled={!isSessionActive}
            className="bg-slate-800 border-slate-700"
          />
          <Button 
            onClick={handleSendMessage} 
            disabled={!isSessionActive || !inputMessage.trim()}
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  )
}



