"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Bug, Mic, MicOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef } from "react"
import { apiService, Message } from "@/lib/api"
import { audioRecorder, AudioRecorder } from "@/lib/audio"

export default function ChatGPTInterface() {
  const [isSessionActive, setIsSessionActive] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [selectedScreen, setSelectedScreen] = useState("screen1")
  const [isRecording, setIsRecording] = useState(false)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  // Configurazione del WebSocket all'avvio della sessione
  useEffect(() => {
    if (isSessionActive) {
      // Inizializza il microfono quando si avvia la sessione
      const initMicrophone = async () => {
        if (AudioRecorder.isSupported()) {
          await audioRecorder.initialize();
          console.log('Microfono inizializzato con la sessione');
          
          // Avvio automatico della registrazione audio
          const started = audioRecorder.startRecording();
          if (started) {
            setIsRecording(true);
            console.log('Registrazione audio avviata automaticamente');
          } else {
            console.error('Impossibile avviare la registrazione audio automaticamente');
          }
        }
      };
      
      initMicrophone();
      
      console.log('Inizializzazione WebSocket...');
      const cleanup = apiService.initWebSocket(
        // Callback per i messaggi in arrivo
        (message) => {
          console.log('Messaggio ricevuto dal WebSocket:', message);
          // Rimuovi il messaggio temporaneo se presente
          setMessages(prev => {
            console.log('Stato attuale dei messaggi:', prev);
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.role === 'assistant' && 
                lastMessage.content === 'Sto elaborando la tua richiesta...') {
              console.log('Sostituisco il messaggio di attesa con la risposta');
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
      
      return () => {
        // Rilascia il microfono quando la sessione termina
        audioRecorder.release();
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
    
    // Aggiungi il messaggio dell'utente
    const userMessage: Message = { role: 'user', content: inputMessage }
    setMessages(prev => [...prev, userMessage])
    setInputMessage("")
    
    try {
      console.log(`Invio messaggio, sessione attiva: ${isSessionActive}, connesso: ${isConnected}`);
      
      // Se la sessione è attiva, usa WebSocket, altrimenti HTTP
      if (isSessionActive && isConnected) {
        console.log("Invio messaggio via WebSocket");
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
    if (isSessionActive) {
      // Se stiamo terminando la sessione, fermiamo la registrazione e rilasciamo le risorse
      if (isRecording) {
        audioRecorder.stopRecording().then(audioBlob => {
          console.log('Registrazione audio fermata con la sessione, blob size:', audioBlob.size);
          // Non inviamo l'audio se terminiamo la sessione
        }).catch(error => {
          console.error('Errore durante l\'arresto della registrazione:', error);
        }).finally(() => {
          setIsRecording(false);
          audioRecorder.release();
        });
      } else {
        audioRecorder.release();
      }
    }
    setIsSessionActive(!isSessionActive);
  }
  
  // Funzione di debug per testare la connessione WebSocket
  const testWebSocketConnection = () => {
    console.log('Test della connessione WebSocket...');
    console.log('Stato sessione:', isSessionActive);
    console.log('Stato connessione:', isConnected);
    
    if (isSessionActive && isConnected) {
      const success = apiService.sendPing();
      if (success) {
        // Aggiungiamo un messaggio temporaneo per debug
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: 'Test WebSocket - Ping inviato al server. Controlla la console per la risposta.' }
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

  // Gestisce l'arresto della registrazione e l'invio dell'audio
  const stopAudioRecording = async () => {
    if (!isRecording) {
      console.error('Nessuna registrazione in corso');
      return;
    }
    
    try {
      console.log('Arresto della registrazione audio...');
      const audioBlob = await audioRecorder.stopRecording();
      setIsRecording(false);
      
      console.log('Registrazione completata, creazione del file audio...');
      const audioFile = audioRecorder.createAudioFile(audioBlob, `audio_${Date.now()}.wav`);
      
      console.log('Invio del file audio al server per la trascrizione...');
      // Aggiungiamo un messaggio temporaneo
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Trascrizione dell\'audio in corso...' }
      ]);
      
      const transcription = await apiService.transcribeAudio(audioFile);
      
      // Sostituiamo il messaggio temporaneo con la trascrizione
      setMessages(prev => {
        const newMessages = [...prev];
        const lastIndex = newMessages.length - 1;
        
        if (lastIndex >= 0 && newMessages[lastIndex].content === 'Trascrizione dell\'audio in corso...') {
          // Rimuoviamo il messaggio temporaneo
          newMessages.pop();
        }
        
        // Aggiungiamo la trascrizione come messaggio dell'utente
        return [...newMessages, transcription];
      });
      
      // Inviamo il messaggio trascritto al backend
      if (isSessionActive && isConnected) {
        console.log("Invio messaggio trascritto via WebSocket");
        const updatedMessages = [...messages, transcription];
        apiService.sendMessageWs(updatedMessages);
        
        // Aggiungiamo un messaggio temporaneo di attesa
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: 'Sto elaborando la tua richiesta...' }
        ]);
      }
    } catch (error) {
      console.error('Errore durante la registrazione audio:', error);
      setIsRecording(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-white text-gray-800">
      {/* Connection Status Indicator */}
      <div className={`w-full text-center text-sm py-1 ${isConnected ? 'bg-green-500 text-white' : 'bg-yellow-500 text-black'}`}>
        {isConnected ? 'Connesso al server in tempo reale' : 'Non connesso al server in tempo reale'}
      </div>
      
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
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-8 rounded-md flex items-center space-x-1 text-blue-500"
                  onClick={testWebSocketConnection}
                >
                  <Bug className="w-4 h-4" />
                  <span className="text-sm">Test WS</span>
                </Button>
                
                {isSessionActive && isRecording && (
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="h-8 rounded-md flex items-center space-x-1 text-red-500"
                    onClick={stopAudioRecording}
                  >
                    <MicOff className="w-4 h-4" />
                    <span className="text-sm">Stop Recording</span>
                  </Button>
                )}
                
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

