"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Bug, Mic, MicOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef } from "react"
import { apiService, Message } from "@/utils/api"
import { AudioRecorder } from "@/utils/audio"
import { formatMarkdown } from "@/utils/formatMessage"

export default function ChatGPTInterface() {
  const [isSessionActive, setIsSessionActive] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [selectedScreen, setSelectedScreen] = useState("screen1")
  const [isRecording, setIsRecording] = useState<boolean>(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const audioRecorderRef = useRef<AudioRecorder | null>(null)

  // Configurazione del WebSocket all'avvio della sessione
  useEffect(() => {
    if (isSessionActive) {
      if (!audioRecorderRef.current) {
        audioRecorderRef.current = new AudioRecorder();
      }
      
      const initMic = async () => {
        if (audioRecorderRef.current) {
          try {
            await audioRecorderRef.current.initialize();
            console.log('Microphone initialized successfully');
          } catch (error) {
            console.error('Failed to initialize microphone:', error);
          }
        }
      };
      
      console.log('Inizializzazione WebSocket...');
      const cleanup = apiService.initWebSocket(
        // Callback per i messaggi in arrivo
        (message) => {
          console.log('Messaggio ricevuto dal WebSocket:', message);
          
          // Se è un messaggio di debugging temporaneo, lo sostituiamo 
          // o lo ignoriamo se è già stato processato un messaggio successivo
          if (message.content === 'Messaggio inviato al server. In attesa di risposta...') {
            setMessages(prev => {
              // Se l'ultimo messaggio è già una risposta (non temporanea), ignoriamo
              const lastMessage = prev[prev.length - 1];
              if (lastMessage && lastMessage.role === 'assistant' && 
                  lastMessage.content !== 'Sto elaborando la tua richiesta...' &&
                  lastMessage.content !== message.content) {
                return prev;
              }
              
              // Altrimenti sostituiamo o aggiungiamo
              if (lastMessage && lastMessage.role === 'assistant' && 
                  (lastMessage.content === 'Sto elaborando la tua richiesta...' ||
                   lastMessage.content === 'Avvio processo di analisi approfondita...')) {
                console.log('Sostituisco il messaggio di attesa con un altro temporaneo');
                return [...prev.slice(0, -1), message];
              }
              
              return [...prev, message];
            });
            return;
          }
          
          // Rimuovi il messaggio temporaneo se presente
          setMessages(prev => {
            console.log('Aggiornamento dei messaggi con:', message);
            const lastMessage = prev[prev.length - 1];
            
            // Se l'ultimo messaggio è temporaneo, lo sostituiamo
            if (lastMessage && lastMessage.role === 'assistant' && 
                (lastMessage.content === 'Sto elaborando la tua richiesta...' ||
                 lastMessage.content === 'Avvio processo di analisi approfondita...' ||
                 lastMessage.content === 'Messaggio inviato al server. In attesa di risposta...')) {
              console.log('Sostituisco il messaggio temporaneo con la risposta');
              return [...prev.slice(0, -1), message];
            }
            
            console.log('Aggiungo nuovo messaggio alla lista');
            return [...prev, message];
          });
        },
        // Callback per la connessione
        () => {
          console.log('WebSocket connesso!');
          setIsConnected(true);
        },
        // Callback per la disconnessione
        () => {
          console.log('WebSocket disconnesso!');
          setIsConnected(false);
        }
      )
      
      initMic();
      
      return () => {
        if (audioRecorderRef.current) {
          audioRecorderRef.current.release();
        }
        cleanup();
      }
    }
  }, [isSessionActive])

  // Scroll automatico alla fine dei messaggi
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Gestisce l'invio di un messaggio
  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return
    
    // Comandi speciali per testing e debug
    if (inputMessage.startsWith('/test')) {
      testWebSocketConnection();
      setInputMessage("");
      return;
    }
    
    if (inputMessage.startsWith('/ping')) {
      if (isSessionActive && isConnected) {
        apiService.sendPing();
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: 'Ping inviato al server. Controlla la console per la risposta.' 
        }]);
      } else {
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: 'WebSocket non connesso. Impossibile inviare ping.' 
        }]);
      }
      setInputMessage("");
      return;
    }
    
    // Aggiungi il messaggio dell'utente
    const userMessage: Message = { role: 'user', content: inputMessage }
    setMessages(prev => [...prev, userMessage])
    setInputMessage("")
    
    try {
      console.log(`Invio messaggio, sessione attiva: ${isSessionActive}, connesso: ${isConnected}`);
      
      // Se la sessione è attiva, usa WebSocket, altrimenti HTTP
      if (isSessionActive && isConnected) {
        console.log("Invio messaggio via WebSocket");
        console.log("Lista messaggi da inviare:", [...messages, userMessage]);
        // Non aggiorniamo i messaggi qui perché lo faremo quando il WebSocket riceverà la risposta
        apiService.sendMessageWs([...messages, userMessage])
        
        // Aggiungiamo un messaggio temporaneo di attesa
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: 'Sto elaborando la tua richiesta...' }
        ])
      } else {
        console.log("Invio messaggio via HTTP");
        const response = await apiService.sendMessage([...messages, userMessage])
        setMessages(prev => [...prev, response])
      }
    } catch (error) {
      console.error("Error sending message:", error)
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Sorry, there was an error processing your request.' }
      ])
    }
  }

  // Gestisce l'invio con il tasto Enter
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  // Gestisce il bottone "think"
  const handleThink = async () => {
    if (messages.length === 0) return
    
    try {
      // Aggiungiamo un messaggio temporaneo di attesa
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Avvio processo di analisi approfondita...' }
      ])
      
      // Nota: non salviamo la risposta qui perché verrà gestita tramite WebSocket
      await apiService.think(messages)
    } catch (error) {
      console.error("Error in think process:", error)
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Si è verificato un errore durante il processo di analisi.' }
      ])
    }
  }

  // Gestisce l'analisi degli screenshot
  const handleAnalyzeScreenshot = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  // Gestisce il caricamento di un file screenshot
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    
    const file = files[0]
    try {
      const response = await apiService.analyzeScreenshot(file)
      setMessages(prev => [...prev, response])
    } catch (error) {
      console.error("Error analyzing screenshot:", error)
    }
    
    // Reset input file
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  // Gestisce il salvataggio della conversazione
  const handleSaveConversation = () => {
    const conversationData = JSON.stringify(messages, null, 2)
    const blob = new Blob([conversationData], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    
    const a = document.createElement('a')
    a.href = url
    a.download = `conversation-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // Gestisce il clear dei messaggi
  const handleClear = () => {
    setMessages([])
  }

  // Gestisce il toggle della sessione
  const toggleSession = () => {
    if (isSessionActive) {
      // Se stiamo terminando la sessione, rilasciamo le risorse
      audioRecorderRef.current?.release();
      setIsRecording(false);
    } else {
      // Se stiamo avviando la sessione, non facciamo nulla qui
      // L'inizializzazione avviene nell'useEffect
    }
    setIsSessionActive(!isSessionActive);
  }

  // Funzione di debug per testare la connessione WebSocket
  const testWebSocketConnection = () => {
    console.log('Test della connessione WebSocket...');
    console.log('Stato sessione:', isSessionActive);
    console.log('Stato connessione:', isConnected);
    
    // Aggiungiamo un messaggio di diagnostica
    setMessages(prev => [
      ...prev,
      { role: 'assistant', content: `🔍 Test diagnostico WebSocket:\n- Sessione attiva: ${isSessionActive}\n- Connessione stabilita: ${isConnected}` }
    ]);
    
    if (isSessionActive && isConnected) {
      const success = apiService.sendPing();
      if (success) {
        // Aggiungiamo un messaggio temporaneo per debug
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: '🔄 Test WebSocket - Ping inviato al server. Controlla la console per la risposta.' }
        ]);
      } else {
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: 'Test WebSocket fallito. Il socket non è aperto o non è inizializzato. Controlla la console.' }
        ]);
      }
    } else {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Test WebSocket non possibile. Stato: sessione=${isSessionActive}, connesso=${isConnected}` }
      ]);
    }
  }

  // Funzione per avviare/fermare la registrazione audio
  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // Avvia la registrazione
  const startRecording = () => {
    if (audioRecorderRef.current && !isRecording) {
      console.log('Starting recording...');
      audioRecorderRef.current.startRecording();
      setIsRecording(true);
    }
  };

  // Ferma la registrazione e invia l'audio al server
  const stopRecording = async () => {
    if (audioRecorderRef.current && isRecording) {
      console.log('Stopping recording...');
      setIsRecording(false);
      
      try {
        const audioBlob = await audioRecorderRef.current.stopRecording();
        console.log('Recording stopped, blob size:', audioBlob.size);
        
        // Solo se l'audio ha una dimensione significativa
        if (audioBlob.size > 1000) {
          const audioFile = audioRecorderRef.current.createAudioFile(audioBlob);
          
          // Aggiungi un messaggio di caricamento
          setMessages(prev => [...prev, { role: 'assistant', content: 'Transcribing audio...' }]);
          
          // Invia il file audio per la trascrizione
          const transcription = await apiService.transcribeAudio(audioFile);
          
          // Aggiorna i messaggi sostituendo il messaggio di caricamento con la trascrizione
          setMessages(prev => [...prev.slice(0, -1), transcription]);
        } else {
          console.log('Audio too short, ignoring');
        }
      } catch (error) {
        console.error('Error processing audio:', error);
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: 'Sorry, there was an error processing your audio.' 
        }]);
      }
    }
  };

  return (
    <div className="flex flex-col h-screen bg-white text-gray-800">
      {/* Header con stato connessione */}
      {isSessionActive && (
        <div className={`px-4 py-2 text-sm font-medium ${isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {isConnected ? 'Connected to the server in real-time' : 'Disconnected from server'}
        </div>
      )}

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((message, index) => (
          <div key={index} className={message.role === 'user' ? 'flex justify-end' : 'space-y-2'}>
            {message.role === 'user' ? (
              <div className="bg-gray-100 rounded-2xl px-4 py-2 max-w-md">
                <p>{message.content}</p>
              </div>
            ) : (
              <div className="flex space-x-4">
                <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center text-white">
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-5 w-5"
                  >
                    <path
                      d="M20 11.5C20 11.5 17.197 18.5 12 18.5C6.80304 18.5 4 11.5 4 11.5C4 11.5 6.80304 4.5 12 4.5C17.197 4.5 20 11.5 20 11.5Z"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    ></path>
                    <circle
                      cx="12"
                      cy="11.5"
                      r="2.5"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    ></circle>
                  </svg>
                </div>
                <div className="flex-1 space-y-2">
                  <div dangerouslySetInnerHTML={{ __html: formatMarkdown(message.content) }} />
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4">
        <div className="border rounded-2xl shadow-sm relative">
          <div className="p-3 min-h-[100px] flex flex-col">
            <Input
              className="border-0 shadow-none focus-visible:ring-0 placeholder:text-gray-400 text-base resize-none"
              placeholder="Fai una domanda"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!isSessionActive}
            />
            <div className="mt-auto flex items-center justify-between pt-2">
              <div className="flex items-center space-x-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 rounded-md flex items-center space-x-1"
                  onClick={toggleSession}
                >
                  {isSessionActive ? (
                    <>
                      <Square className="w-4 h-4" />
                      <span className="text-sm">End Session</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      <span className="text-sm">Start Session</span>
                    </>
                  )}
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-8 rounded-md flex items-center space-x-1"
                  onClick={handleClear}
                  disabled={!isSessionActive}
                >
                  <Trash2 className="w-4 h-4" />
                  <span className="text-sm">Clear</span>
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-8 rounded-md flex items-center space-x-1"
                  onClick={handleSaveConversation}
                  disabled={!isSessionActive || messages.length === 0}
                >
                  <Save className="w-4 h-4" />
                  <span className="text-sm">Save Conversation</span>
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-8 rounded-md flex items-center space-x-1"
                  onClick={handleThink}
                  disabled={!isSessionActive || !isConnected || messages.length === 0}
                >
                  <Brain className="w-4 h-4" />
                  <span className="text-sm">Think</span>
                </Button>
                <div className="flex items-center space-x-1">
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="h-8 rounded-md flex items-center space-x-1"
                    onClick={handleAnalyzeScreenshot}
                    disabled={!isSessionActive}
                  >
                    <Camera className="w-4 h-4" />
                    <span className="text-sm">Analyze Screenshot</span>
                  </Button>
                  <Select 
                    defaultValue="screen1"
                    value={selectedScreen}
                    onValueChange={setSelectedScreen}
                    disabled={!isSessionActive}
                  >
                    <SelectTrigger className="h-8 w-[120px]">
                      <SelectValue placeholder="Select screen" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="screen1">Screen 1</SelectItem>
                      <SelectItem value="screen2">Screen 2</SelectItem>
                      <SelectItem value="screen3">Screen 3</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {isSessionActive && (
                <Button
                  variant={isRecording ? "destructive" : "outline"}
                  size="sm"
                  className="h-8 w-8 p-0 rounded-full"
                  onClick={toggleRecording}
                >
                  {isRecording ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Input file nascosto per gli screenshot */}
      <input
        type="file"
        ref={fileInputRef}
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileUpload}
      />
    </div>
  )
}

