"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Bug, Mic, MicOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef } from "react"
import { apiClient, TranscriptionUpdate, ResponseUpdate, ErrorUpdate, AudioStreamControl, startSessionAudio, useSessionStream } from "@/utils/api"
import { formatMarkdown } from "@/utils/formatMessage"

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

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Utilizziamo il custom hook per lo streaming degli aggiornamenti della sessione
  const { cleanup: cleanupStream } = useSessionStream(
    sessionId,
    {
      onTranscription: (update: TranscriptionUpdate) => {
        console.log('Trascrizione ricevuta:', update);
        
        // Se non è un messaggio di stato, aggiungilo come messaggio utente
        if (!update.text.includes("Recording...") && 
            !update.text.includes("Registrazione avviata...") && 
            !update.text.startsWith('\n[')) {
          
          setMessages(prev => {
            // Verifica se esiste già lo stesso messaggio per evitare duplicati
            const exists = prev.some(m => m.role === 'user' && m.content === update.text);
            if (exists) return prev;
            
            return [...prev, { role: 'user', content: update.text }];
          });
        }
      },
      
      onResponse: (update: ResponseUpdate) => {
        console.log('Risposta ricevuta:', update);
        
        setMessages(prev => {
          // Se l'ultimo messaggio è un messaggio di attesa dell'assistente, lo sostituiamo
          const lastMessage = prev[prev.length - 1];
          if (lastMessage && lastMessage.role === 'assistant' && 
              (lastMessage.content === 'Sto elaborando la tua richiesta...' ||
               lastMessage.content === 'Avvio processo di analisi approfondita...' ||
               lastMessage.content === 'Messaggio inviato al server. In attesa di risposta...')) {
            return [...prev.slice(0, -1), { role: 'assistant', content: update.text }];
          }
          
          // Verifica se esiste già un messaggio assistente, aggiorna se necessario
          const assistantIndex = prev.findIndex(m => m.role === 'assistant');
          if (assistantIndex >= 0) {
            // Se il contenuto è diverso, aggiungi un nuovo messaggio
            if (prev[assistantIndex].content !== update.text) {
              return [...prev, { role: 'assistant', content: update.text }];
            }
            return prev;
          }
          
          // Altrimenti aggiungi un nuovo messaggio
          return [...prev, { role: 'assistant', content: update.text }];
        });
      },
      
      onError: (update: ErrorUpdate) => {
        console.error('Errore ricevuto:', update);
        setMessages(prev => [
          ...prev, 
          { role: 'assistant', content: `Si è verificato un errore: ${update.message}` }
        ]);
      },
      
      onConnectionError: (error: Event) => {
        console.error('Errore di connessione SSE:', error);
        
        // Verifichiamo se la sessione è ancora attiva prima di mostrare errori
        // Se la sessione è stata terminata volontariamente, ignoriamo gli errori
        if (isSessionActive && !isStreamError) {
          setIsStreamError(true);
          setIsConnected(false);
          setMessages(prev => [
            ...prev,
            { role: 'assistant', content: 'Si è verificato un errore di connessione con il server. Prova a chiudere e riaprire la sessione.' }
          ]);
        }
      }
    }
  );

  // Scroll automatico alla fine dei messaggi
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Cleanup quando il componente viene smontato
  useEffect(() => {
    return () => {
      if (sessionId) {
        // Ferma lo streaming audio, se attivo
        if (audioControl) {
          audioControl.stop();
        }
        // Chiudi gli stream
        cleanupStream();
        // Termina la sessione
        apiClient.endSession(sessionId).catch(console.error);
      }
    };
  }, [sessionId, audioControl, cleanupStream]);

  // Gestisce l'avvio o la chiusura della sessione
  const toggleSession = async () => {
    try {
      if (isSessionActive) {
        setIsSessionActive(false); // Impostiamo subito a false per evitare ulteriori tentativi di connessione
        setIsConnected(false);
        
        // Ferma lo streaming audio, se attivo
        if (audioControl) {
          audioControl.stop();
          setAudioControl(null);
        }
        
        // Prima chiudiamo i nostri stream
        cleanupStream();
        
        if (sessionId) {
          try {
            await apiClient.endSession(sessionId);
          } catch (error) {
            console.error('Error ending session:', error);
          }
          setSessionId(null);
        }
        
        setIsRecording(false);
        // Puliamo i messaggi
        setMessages([]);
      } else {
        try {
          // Reimpostiamo il flag di errore di streaming
          setIsStreamError(false);
          
          // Impostiamo un messaggio di connessione
          setMessages([{ role: 'assistant', content: 'Connessione in corso...' }]);
          
          // Crea una nuova sessione con timeout
          const sessionPromise = apiClient.createSession();
          const timeoutPromise = new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Timeout durante la creazione della sessione')), 10000)
          );
          
          const newSessionId = await Promise.race([sessionPromise, timeoutPromise]) as string;
          setSessionId(newSessionId);
          
          // Aggiorniamo il messaggio di stato
          setMessages([{ role: 'assistant', content: 'Sessione creata, avvio in corso...' }]);
          
          // Avvia la sessione
          await apiClient.startSession(newSessionId);
          
          // Avvia lo streaming audio automaticamente
          try {
            const control = await startSessionAudio(newSessionId);
            setAudioControl(control);
            setIsRecording(true);
          } catch (audioError: any) {
            console.error("Errore nell'avvio dello streaming audio:", audioError);
            setMessages(prev => [
              ...prev,
              { role: 'assistant', content: 'Non è stato possibile avviare lo streaming audio. La sessione funzionerà in modalità testo.' }
            ]);
          }
          
          setMessages([{ role: 'assistant', content: 'Sessione avviata! Ora puoi parlare o digitare.' }]);
          setIsSessionActive(true);
          setIsConnected(true);
        } catch (sessionError: any) {
          console.error("Errore nell'avvio della sessione:", sessionError);
          
          // Puliamo eventuali risorse
          if (sessionId) {
            try {
              await apiClient.endSession(sessionId);
            } catch (e) {
              console.error("Errore nella pulizia della sessione:", e);
            }
            setSessionId(null);
          }
          
          setMessages([{ 
            role: 'assistant', 
            content: `Si è verificato un errore durante l'avvio della sessione: ${sessionError.message}. Verifica che il server sia in esecuzione sulla porta 8000.` 
          }]);
          
          return;
        }
      }
    } catch (error: any) {
      console.error("Errore nella gestione della sessione:", error);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Si è verificato un errore durante la gestione della sessione: ${error.message}` }
      ]);
    }
  };

  // Gestisce l'invio di un messaggio
  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !sessionId) return;
    
    // Aggiungi il messaggio dell'utente
    const userMessage: Message = { role: 'user', content: inputMessage };
    setMessages(prev => [...prev, userMessage]);
    setInputMessage("");
    
    try {
      // Aggiungiamo un messaggio temporaneo di attesa
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Sto elaborando la tua richiesta...' }
      ]);
      
      // Invia il messaggio di testo
      await apiClient.sendTextMessage(sessionId, inputMessage);
      
      // Non è necessario aggiungere manualmente la risposta perché verrà gestita 
      // tramite gli eventi SSE (onResponse callback)
    } catch (error) {
      console.error("Errore nell'invio del messaggio:", error);
      setMessages(prev => [
        ...prev.slice(0, -1), // Rimuovi il messaggio di attesa
        { role: 'assistant', content: 'Si è verificato un errore durante l\'invio del messaggio.' }
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

