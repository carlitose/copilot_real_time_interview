"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Bug, Mic, MicOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef, useCallback } from "react"
import { formatMarkdown } from "@/utils/formatMessage"

// Importing APIs and services
import apiClient, { Message } from "@/utils/api"
import { useAudioStream, AudioStreamControl } from "@/utils/socketio"
import { 
  useSessionStream, 
  TranscriptionUpdate, 
  ResponseUpdate, 
  ErrorUpdate 
} from "@/utils/eventStream"

// Constant for the API base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

export default function ChatGPTInterface() {
  const [isSessionActive, setIsSessionActive] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [selectedScreen, setSelectedScreen] = useState("screen1")
  const [isRecording, setIsRecording] = useState<boolean>(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [audioControl, setAudioControl] = useState<AudioStreamControl | null>(null)
  const [isStreamError, setIsStreamError] = useState<boolean>(false)

  // State to keep track of the SSE cleanup function
  const [cleanupStream, setCleanupStream] = useState<(() => void) | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Ref for the stream listener
  const streamControlRef = useRef<any>(null);

  // Callback to handle transcription updates
  const handleTranscription = useCallback((update: TranscriptionUpdate) => {
    console.log(`Received transcription update: ${update.text}`);
    // We do nothing with the transcription for now
  }, []);

  // Callback to handle model responses
  const handleResponse = useCallback((update: ResponseUpdate) => {
    console.log(`Received response: ${update.text}`);
    setMessages(prevMessages => {
      // Find the last assistant message
      const lastAssistantIndex = [...prevMessages].reverse().findIndex(m => m.role === 'assistant');
      
      // If there's already an assistant message and it's not the final response,
      // update that message instead of adding a new one
      if (lastAssistantIndex !== -1 && !update.final) {
        const reversedIndex = lastAssistantIndex;
        const actualIndex = prevMessages.length - 1 - reversedIndex;
        
        const newMessages = [...prevMessages];
        newMessages[actualIndex] = {
          ...newMessages[actualIndex],
          content: update.text
        };
        return newMessages;
      }
      
      // If it's the final response or there are no assistant messages, add a new message
      if (update.final) {
        return [...prevMessages, { role: 'assistant', content: update.text }];
      }
      
      return prevMessages;
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

  // Effect to set up streams when the session is active
  useEffect(() => {
    if (isSessionActive && sessionId) {
      console.log(`Setting up streams for session ${sessionId}...`);
      
      // Do not call hooks inside useEffect
      // const streamControl = useSessionStream(sessionId, {
      //   onTranscription: handleTranscription,
      //   onResponse: handleResponse,
      //   onError: handleError,
      //   onConnectionError: handleConnectionError,
      //   onConnectionStatus: handleConnectionStatus
      // });
      
      // Use the streamControl that has already been created in the component body
      setCleanupStream(() => streamControlRef.current?.cleanup);
      
      return () => {
        if (streamControlRef.current) {
          streamControlRef.current.cleanup();
          streamControlRef.current = null;
        }
      };
    }
  }, [isSessionActive, sessionId, handleTranscription, handleResponse, handleError, handleConnectionError, handleConnectionStatus]);

  // Call useSessionStream in the component body
  const streamControl = useSessionStream(
    sessionId || '', 
    {
      onTranscription: handleTranscription,
      onResponse: handleResponse,
      onError: handleError, 
      onConnectionError: handleConnectionError,
      onConnectionStatus: handleConnectionStatus
    }
  );
  
  // Update the ref in the effect
  useEffect(() => {
    streamControlRef.current = streamControl;
  }, [streamControl]);

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
        await apiClient.endSession(sessionId);
        setIsSessionActive(false);
      }
    } else {
      // Start a new session
      console.log("Starting a new session...");
      
      let sid = sessionId;
      
      if (!sid) {
        // If there's no session, create a new one
        try {
          sid = await apiClient.createSession();
          setSessionId(sid);
        } catch (error) {
          console.error("Error creating session:", error);
          return;
        }
      }
      
      try {
        // Start the session on the server
        await apiClient.startSession(sid);
        setIsSessionActive(true);
        
        // Avvia automaticamente la registrazione audio
        console.log("Avvio automatico della registrazione audio...");
        
        // Verifica che audioStreamControl sia inizializzato correttamente
        if (audioStreamControl) {
          try {
            audioStreamControl.start();
            console.log("Registrazione audio avviata con successo");
            setIsRecording(true);
          } catch (error) {
            console.error("Errore nell'avvio della registrazione audio:", error);
            alert("C'è stato un problema nell'attivazione del microfono. Per favore, controlla i permessi del browser.");
          }
        } else {
          console.error("audioStreamControl non inizializzato correttamente");
        }
        
      } catch (error) {
        console.error("Error starting session:", error);
      }
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !sessionId || !isSessionActive) return;
    
    try {
      // Add the user's message
      setMessages(prev => [...prev, { role: 'user', content: inputMessage }]);
      
      // Add a waiting message from the assistant
      setMessages(prev => [...prev, { role: 'assistant', content: 'Processing your request...' }]);
      
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
          { role: 'assistant', content: 'An error occurred while sending the message.' }
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
        { role: 'assistant', content: 'An error occurred while sending the message.' }
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
      setMessages(prev => [...prev, { role: 'assistant', content: 'Thinking about this conversation...' }]);
      
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
        { role: 'assistant', content: 'An error occurred during the thinking process.' }
      ]);
    }
  };

  const handleAnalyzeScreenshot = async () => {
    if (!sessionId || !isSessionActive) return;
    
    try {
      // Get the monitor index
      const monitorIndex = selectedScreen.replace('screen', '');
      
      // Add a waiting message
      setMessages(prev => [...prev, { role: 'assistant', content: 'Capturing and analyzing the screen...' }]);
      
      // Capture and analyze the screenshot
      await apiClient.takeScreenshot(sessionId, monitorIndex);
      
      // The response will be handled via SSE events
    } catch (error) {
      console.error("Error capturing screenshot:", error);
      
      // Remove the waiting message
      setMessages(prev => prev.slice(0, prev.length - 1));
      
      // Add an error message
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'An error occurred while capturing the screenshot.' }
      ]);
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

  // Inizializza l'audio control con l'hook useAudioStream
  const audioStreamControl = useAudioStream(sessionId || '');
  
  // Effect per monitorare cambiamenti di sessionId e aggiornare lo stato di registrazione
  useEffect(() => {
    console.log(`sessionId aggiornato: ${sessionId}`);
    // Se la sessione è attiva e isRecording è true, ma audioStreamControl non è attivo,
    // prova a riavviare la registrazione
    if (isSessionActive && isRecording && audioStreamControl && !audioStreamControl.isActive) {
      console.log('Tentativo di riattivazione della registrazione audio dopo cambio sessionId');
      try {
        audioStreamControl.start();
      } catch (error) {
        console.error('Errore nella riattivazione della registrazione audio:', error);
      }
    }
  }, [sessionId, isSessionActive, isRecording, audioStreamControl]);

  const toggleRecording = () => {
    if (!isSessionActive || !sessionId) {
      alert('Per favore, avvia prima una sessione.');
      return;
    }
    
    // Usa direttamente l'audioStreamControl invece di crearlo condizionalmente
    if (!isRecording) {
      console.log('Attivazione microfono in corso...');
      try {
        audioStreamControl.start();
      } catch (error) {
        console.error('Errore nell\'attivazione del microfono:', error);
        alert('C\'è stato un problema nell\'attivazione del microfono. Assicurati di aver dato i permessi necessari.');
        return;
      }
    } else {
      audioStreamControl.stop();
      console.log('Microfono disattivato.');
    }
    
    setIsRecording(!isRecording);
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-50">
      <header className="p-4 border-b border-slate-800 flex justify-between items-center">
        <h1 className="text-xl font-bold">Integrated ChatGPT</h1>
        <div className="flex items-center space-x-2">
          <Select value={selectedScreen} onValueChange={setSelectedScreen}>
            <SelectTrigger className="w-[100px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="screen1">Screen 1</SelectItem>
              <SelectItem value="screen2">Screen 2</SelectItem>
              <SelectItem value="screen3">Screen 3</SelectItem>
            </SelectContent>
          </Select>
          <Button 
            variant={isSessionActive ? "destructive" : "default"}
            onClick={toggleSession}
            title={isSessionActive ? "End session" : "Start session"}
          >
            {isSessionActive ? <Square size={16} /> : <Play size={16} />}
          </Button>
          <Button 
            variant="ghost" 
            onClick={handleClear}
            title="Clear chat"
          >
            <Trash2 size={16} />
          </Button>
          <Button 
            variant="ghost" 
            onClick={handleSaveConversation}
            title="Save conversation"
            disabled={!isSessionActive}
          >
            <Save size={16} />
          </Button>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message, index) => (
          <div 
            key={index} 
            className={`p-3 rounded-lg max-w-[80%] ${
              message.role === 'user' 
                ? 'bg-blue-900 ml-auto' 
                : message.role === 'assistant'
                  ? 'bg-slate-800'
                  : 'bg-slate-700 mx-auto'
            }`}
          >
            <div dangerouslySetInnerHTML={{ __html: formatMarkdown(message.content) }} />
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="p-4 border-t border-slate-800 bg-slate-900">
        <div className="flex items-center space-x-2 mb-2">
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
            onClick={handleAnalyzeScreenshot}
            disabled={!isSessionActive}
            title="Analyze screen"
          >
            <Camera size={16} />
          </Button>
          <Button 
            variant="ghost" 
            size="sm"
            disabled={!isSessionActive}
            title="Debug"
          >
            <Bug size={16} />
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

