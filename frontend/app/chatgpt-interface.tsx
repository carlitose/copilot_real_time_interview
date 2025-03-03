"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Bug, Mic, MicOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef } from "react"
import { formatMarkdown } from "@/utils/formatMessage"

// Costante per l'URL base delle API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

// Definiamo qui l'interfaccia Message per sostituire quella che era importata
interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

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
  const [sessionStatus, setSessionStatus] = useState<any>(null)

  // Stato per tenere traccia della funzione di pulizia SSE
  const [cleanupStream, setCleanupStream] = useState<(() => void) | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Inizializzazione automatica della sessione all'avvio
  useEffect(() => {
    async function initializeSession() {
      try {
        console.log("Inizializzazione automatica di una nuova sessione...");
        const newSessionId = await apiClient.createSession();
        console.log(`Nuova sessione creata: ${newSessionId}`);
        setSessionId(newSessionId);
        
        // Avvio immediato della sessione
        const success = await apiClient.startSession(newSessionId);
        if (success) {
          console.log(`Sessione ${newSessionId} avviata automaticamente`);
          setIsSessionActive(true);
          setIsConnected(true);
          
          // Setup degli stream per la nuova sessione
          setupStreams(newSessionId);
        } else {
          console.error(`Errore nell'avvio automatico della sessione ${newSessionId}`);
        }
      } catch (error) {
        console.error("Errore durante l'inizializzazione della sessione:", error);
      }
    }
    
    // Chiama l'inizializzazione
    initializeSession();
    
    // Setup del controllo periodico dello stato della sessione
    const intervalId = setInterval(async () => {
      if (sessionId) {
        try {
          const response = await fetch(`${API_BASE_URL}/sessions/status?sessionId=${sessionId}`);
          if (response.ok) {
            const data = await response.json();
            console.log("Stato sessione:", data);
            setSessionStatus(data.status);
            
            if (!data.success || !data.status?.is_active) {
              console.warn("La sessione non sembra più essere attiva sul server");
            }
          } else {
            console.error(`Errore nel controllo stato sessione: ${response.status} ${response.statusText}`);
          }
        } catch (error) {
          console.error("Errore durante il controllo dello stato sessione:", error);
        }
      }
    }, 10000); // Controlla ogni 10 secondi
    
    return () => {
      clearInterval(intervalId);
    };
  }, []);

  // Funzione per configurare gli stream
  const setupStreams = (sid: string) => {
    console.log(`Configurazione degli stream per la sessione ${sid}`);
    
    // Callback per aggiornare la trascrizione
    const onTranscription = (update: TranscriptionUpdate) => {
      console.log(`Ricevuto aggiornamento trascrizione: ${update.text}`);
      // Non facciamo nulla con la trascrizione ora
    };

    // Callback per gestire le risposte
    const onResponse = (update: ResponseUpdate) => {
      console.log(`Ricevuta risposta: ${update.text}`);
      setMessages(prevMessages => {
        // Trova l'ultimo messaggio dell'assistente
        const lastAssistantIndex = [...prevMessages].reverse().findIndex(m => m.role === 'assistant');
        
        // Se c'è un messaggio di "caricamento" dell'assistente, lo sostituiamo
        if (lastAssistantIndex >= 0 && prevMessages[prevMessages.length - 1 - lastAssistantIndex].content === 'Sto elaborando la tua richiesta...') {
          const newMessages = [...prevMessages];
          newMessages[prevMessages.length - 1 - lastAssistantIndex] = {
            role: 'assistant',
            content: update.text
          };
          return newMessages;
        } else {
          // Altrimenti aggiungiamo un nuovo messaggio dell'assistente
          return [...prevMessages, { role: 'assistant', content: update.text }];
        }
      });
    };

    // Callback per gestire gli errori
    const onError = (update: ErrorUpdate) => {
      console.error(`Errore ricevuto dal server: ${update.message}`);
      setIsStreamError(true);
      setMessages(prevMessages => [...prevMessages, { role: 'assistant', content: `Errore: ${update.message}` }]);
    };

    // Callback per errori di connessione
    const onConnectionError = (error: Event) => {
      console.error('Errore di connessione SSE:', error);
      setIsConnected(false);
      // Se la sessione è stata chiusa volontariamente, non mostriamo errori
      if (isSessionActive) {
        setMessages(prevMessages => [
          ...prevMessages,
          { role: 'assistant', content: 'La connessione al server è stata interrotta. Prova a riavviare la sessione.' }
        ]);
      }
    };

    // Configurazione dello stream
    const { cleanup } = useSessionStream(sid, {
      onTranscription,
      onResponse,
      onError,
      onConnectionError
    });

    // Salva la funzione di cleanup
    setCleanupStream(() => cleanup);
  };

  // Scroll automatico alla fine dei messaggi
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Cleanup quando il componente viene smontato
  useEffect(() => {
    // Ferma lo streaming quando cambiamo pagina o chiudiamo l'app
    return () => {
      if (sessionId) {
        console.log(`Cleanup on unmount for session ${sessionId}`);
        // Arresta l'audio se attivo
        if (audioControl) {
          audioControl.stop();
        }
        // Chiudi gli stream
        if (cleanupStream) {
          cleanupStream();
        }
        // Termina la sessione
        apiClient.endSession(sessionId).catch(console.error);
      }
    };
  }, [sessionId, audioControl, cleanupStream]);

  // Gestisce l'avvio o la chiusura della sessione
  const toggleSession = async () => {
    try {
      if (isSessionActive) {
        // Chiusura sessione
        console.log("Chiusura sessione in corso...");
        setIsSessionActive(false);
        setIsConnected(false);
        
        // Ferma lo streaming audio, se attivo
        if (audioControl) {
          audioControl.stop();
          setAudioControl(null);
        }
        
        // Ferma lo streaming degli aggiornamenti
        if (cleanupStream) {
          cleanupStream();
          setCleanupStream(null);
        }
        
        // Chiudi la sessione sul server
        if (sessionId) {
          await apiClient.endSession(sessionId);
          console.log("Sessione chiusa con successo");
        }
      } else {
        // Utilizziamo la sessione già creata all'avvio
        if (sessionId) {
          console.log(`Riattivazione della sessione ${sessionId}...`);
          
          // Proviamo a verificare lo stato attuale
          try {
            const response = await fetch(`${API_BASE_URL}/sessions/status?sessionId=${sessionId}`);
            if (response.ok) {
              const data = await response.json();
              console.log("Status check prima di riattivare:", data);
              
              if (data.success && data.status?.is_active) {
                console.log("La sessione è già attiva, configuro solo gli stream");
                setIsSessionActive(true);
                setIsConnected(true);
                setupStreams(sessionId);
                return;
              }
            }
          } catch (error) {
            console.error("Errore nel controllo status:", error);
          }
          
          // Se arriviamo qui, dobbiamo riavviare la sessione
          const success = await apiClient.startSession(sessionId);
          
          if (success) {
            console.log(`Sessione ${sessionId} riavviata con successo`);
            setIsSessionActive(true);
            setIsConnected(true);
            // Setup degli stream
            setupStreams(sessionId);
          } else {
            console.error(`Errore nel riavvio della sessione ${sessionId}`);
          }
        } else {
          console.error("Nessun ID sessione disponibile per l'avvio");
        }
      }
    } catch (error) {
      console.error("Errore durante la gestione della sessione:", error);
    }
  };

  // Gestisce l'invio di un messaggio
  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !sessionId) return;
    
    try {
      // Verifica se la sessione è ancora attiva
      if (!isSessionActive) {
        // Se la sessione non è attiva, mostro un messaggio e non invio nulla
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: 'La sessione non è attiva. Avvia una nuova sessione prima di inviare messaggi.' }
        ]);
        return;
      }
    
      // Aggiungi il messaggio dell'utente
      const userMessage: Message = { role: 'user', content: inputMessage };
      setMessages(prev => [...prev, userMessage]);
      setInputMessage("");
      
      // Aggiungiamo un messaggio temporaneo di attesa
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Sto elaborando la tua richiesta...' }
      ]);
      
      // Invia il messaggio di testo
      const result = await apiClient.sendTextMessage(sessionId, inputMessage);
      
      if (!result) {
        // Rimuovi il messaggio di attesa
        setMessages(prev => [
          ...prev.slice(0, -1),
          { role: 'assistant', content: 'Si è verificato un errore durante l\'invio del messaggio. Prova a riavviare la sessione.' }
        ]);
      }
      
      // Se invio riuscito, il messaggio di risposta verrà gestito tramite gli eventi SSE
      
    } catch (error) {
      console.error("Errore nell'invio del messaggio:", error);
      setMessages(prev => [
        ...prev.slice(0, -1), // Rimuovi il messaggio di attesa
        { role: 'assistant', content: 'Si è verificato un errore durante l\'invio del messaggio. Prova a riavviare la sessione.' }
      ]);
    }
  };

  // Gestisce l'invio con il tasto Enter
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Gestisce il bottone "think"
  const handleThink = async () => {
    if (messages.length === 0 || !sessionId) return;
    
    try {
      // Aggiungiamo un messaggio temporaneo di attesa
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Avvio processo di analisi approfondita...' }
      ]);
      
      // Avvia il processo di pensiero
      await apiClient.startThinkProcess(sessionId);
      
      // La risposta verrà gestita tramite gli eventi SSE
    } catch (error) {
      console.error("Errore nel processo di analisi:", error);
      setMessages(prev => [
        ...prev.slice(0, -1), // Rimuovi il messaggio di attesa
        { role: 'assistant', content: 'Si è verificato un errore durante il processo di analisi.' }
      ]);
    }
  };

  // Gestisce l'analisi degli screenshot
  const handleAnalyzeScreenshot = async () => {
    if (!sessionId) return;
    
    try {
      // Utilizziamo l'indice del monitor selezionato
      const monitorIndex = parseInt(selectedScreen.replace('screen', '')) - 1;
      
      // Aggiungiamo un messaggio temporaneo
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Acquisizione e analisi dello screenshot in corso...' }
      ]);
      
      // Cattura e analizza lo screenshot
      await apiClient.takeScreenshot(sessionId, monitorIndex);
      
      // La risposta verrà gestita tramite gli eventi SSE
    } catch (error) {
      console.error("Errore nell'analisi dello screenshot:", error);
      setMessages(prev => [
        ...prev.slice(0, -1), // Rimuovi il messaggio di attesa
        { role: 'assistant', content: 'Si è verificato un errore durante l\'analisi dello screenshot.' }
      ]);
    }
  };

  // Gestisce il salvataggio della conversazione
  const handleSaveConversation = async () => {
    if (!sessionId) return;
    
    try {
      const conversation = await apiClient.saveConversation(sessionId);
      
      // Crea e scarica il file JSON
      const conversationData = JSON.stringify(conversation, null, 2);
      const blob = new Blob([conversationData], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      
      const a = document.createElement('a');
      a.href = url;
      a.download = `conversation-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Errore nel salvataggio della conversazione:", error);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Si è verificato un errore durante il salvataggio della conversazione.' }
      ]);
    }
  };

  // Gestisce il clear dei messaggi
  const handleClear = () => {
    setMessages([]);
  };

  // Gestisce il toggle dello streaming audio
  const toggleRecording = () => {
    if (!audioControl) return;
    
    if (isRecording) {
      audioControl.pause();
    } else {
      audioControl.resume();
    }
    
    setIsRecording(!isRecording);
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
            <div className="flex">
              <Input
                className="border-0 shadow-none focus-visible:ring-0 placeholder:text-gray-400 text-base resize-none flex-grow"
                placeholder="Fai una domanda"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={!isSessionActive}
              />
              <Button
                className="ml-2"
                onClick={handleSendMessage}
                disabled={!isSessionActive || !inputMessage.trim()}
              >
                Invia
              </Button>
            </div>
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
                  variant={isRecording ? "outline" : "destructive"}
                  size="sm"
                  className="h-8 w-8 p-0 rounded-full"
                  onClick={toggleRecording}
                >
                  {isRecording ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
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
      />
    </div>
  )
}

