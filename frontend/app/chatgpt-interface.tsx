"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Mic, MicOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef } from "react"
import { apiService, Message } from "@/lib/api"
import { audioRecorder } from "@/lib/audio"

export default function ChatGPTInterface() {
  const [isSessionActive, setIsSessionActive] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [selectedScreen, setSelectedScreen] = useState("screen1")
  const [isRecording, setIsRecording] = useState(false)
  const [microphoneAccessGranted, setMicrophoneAccessGranted] = useState(false)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  // Inizializza il microfono all'avvio
  useEffect(() => {
    const initMicrophone = async () => {
      if (audioRecorder.isSupported()) {
        const granted = await audioRecorder.initialize();
        setMicrophoneAccessGranted(granted);
      }
    };
    
    initMicrophone();
    
    // Cleanup quando il componente viene smontato
    return () => {
      audioRecorder.release();
    };
  }, []);
  
  // Configurazione del WebSocket all'avvio
  useEffect(() => {
    if (isSessionActive) {
      const cleanup = apiService.initWebSocket(
        // Callback per i messaggi in arrivo
        (message) => {
          setMessages(prev => [...prev, message])
        },
        // Callback per la connessione
        () => setIsConnected(true),
        // Callback per la disconnessione
        () => setIsConnected(false)
      )
      
      return cleanup
    }
  }, [isSessionActive])
  
  // Scroll automatico alla fine dei messaggi
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])
  
  // Gestisce l'invio di un messaggio
  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return
    
    // Aggiungi il messaggio dell'utente
    const userMessage: Message = { role: 'user', content: inputMessage }
    setMessages(prev => [...prev, userMessage])
    setInputMessage("")
    
    try {
      // Se la sessione è attiva, usa WebSocket, altrimenti HTTP
      if (isSessionActive && isConnected) {
        apiService.sendMessageWs([...messages, userMessage])
      } else {
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
      const response = await apiService.think(messages)
      setMessages(prev => [...prev, response])
    } catch (error) {
      console.error("Error in think process:", error)
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
    setIsSessionActive(!isSessionActive)
  }
  
  // Gestisce l'avvio della registrazione audio
  const handleStartRecording = () => {
    if (!microphoneAccessGranted) {
      console.error("Microphone access not granted");
      return;
    }
    
    const success = audioRecorder.startRecording();
    if (success) {
      setIsRecording(true);
    }
  };
  
  // Gestisce la fine della registrazione audio
  const handleStopRecording = async () => {
    if (!isRecording) return;
    
    try {
      const audioBlob = await audioRecorder.stopRecording();
      const audioFile = audioRecorder.createAudioFile(audioBlob);
      
      // Mostra un messaggio temporaneo
      setMessages(prev => [...prev, { role: 'assistant', content: 'Trascrivendo audio...' }]);
      
      // Trascrive l'audio
      const transcription = await apiService.transcribeAudio(audioFile);
      
      // Rimuove il messaggio temporaneo
      setMessages(prev => prev.slice(0, -1));
      
      // Aggiunge la trascrizione ai messaggi
      setMessages(prev => [...prev, transcription]);
      
      // Invia la trascrizione al backend
      if (isSessionActive && isConnected) {
        apiService.sendMessageWs([...messages, transcription]);
      } else {
        const response = await apiService.sendMessage([...messages, transcription]);
        setMessages(prev => [...prev, response]);
      }
    } catch (error) {
      console.error("Error processing audio recording:", error);
    } finally {
      setIsRecording(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-white text-gray-800">
      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((message, index) => (
          message.role === 'user' ? (
            // User Message
            <div key={index} className="flex justify-end">
              <div className="bg-gray-100 rounded-2xl px-4 py-2 max-w-md">
                <p>{message.content}</p>
              </div>
            </div>
          ) : (
            // Assistant Response
            <div key={index} className="space-y-2">
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
                  {/* Pre-format message content with newlines and markdown */}
                  <div style={{ whiteSpace: 'pre-wrap' }}>
                    {message.content.split('\n').map((line, i) => (
                      <p key={i}>{line}</p>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )
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
            />
            <div className="mt-auto flex items-center justify-between pt-2">
              <div className="flex items-center space-x-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className={`h-8 rounded-md flex items-center space-x-1 ${isSessionActive ? 'text-red-500' : ''}`}
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
                >
                  <Trash2 className="w-4 h-4" />
                  <span className="text-sm">Clear</span>
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-8 rounded-md flex items-center space-x-1"
                  onClick={handleSaveConversation}
                >
                  <Save className="w-4 h-4" />
                  <span className="text-sm">Save Conversation</span>
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-8 rounded-md flex items-center space-x-1"
                  onClick={handleThink}
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
                  >
                    <Camera className="w-4 h-4" />
                    <span className="text-sm">Analyze Screenshot</span>
                  </Button>
                  <Select 
                    defaultValue={selectedScreen}
                    onValueChange={setSelectedScreen}
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
                  
                  {/* Pulsanti per la registrazione audio */}
                  {!isRecording ? (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="h-8 rounded-md flex items-center space-x-1"
                      onClick={handleStartRecording}
                      disabled={!microphoneAccessGranted}
                      title={microphoneAccessGranted ? "Start recording" : "Microphone access not granted"}
                    >
                      <Mic className="w-4 h-4" />
                      <span className="text-sm">Record Audio</span>
                    </Button>
                  ) : (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="h-8 rounded-md flex items-center space-x-1 text-red-500"
                      onClick={handleStopRecording}
                    >
                      <MicOff className="w-4 h-4" />
                      <span className="text-sm">Stop Recording</span>
                    </Button>
                  )}
                  
                  {/* Hidden file input for screenshot upload */}
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept="image/*"
                    style={{ display: 'none' }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

