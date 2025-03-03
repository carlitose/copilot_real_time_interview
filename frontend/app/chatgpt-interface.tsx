"use client"
import { Play, Square, Trash2, Save, Brain, Camera, Bug, Mic, MicOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useState, useEffect, useRef } from "react"
import { formatMarkdown } from "@/utils/formatMessage"

// Importazione delle API e dei servizi
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
          
          // Configura gli stream di eventi
          setupStreams(newSessionId);
        } else {
          console.error(`Errore nell'avvio automatico della sessione ${newSessionId}`);
        }
      } catch (error) {
        console.error("Errore durante l'inizializzazione della sessione:", error);
      }
    }
    
    initializeSession();
  }, []);

  // Effetto per scorrere automaticamente verso il basso quando arrivano nuovi messaggi
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const setupStreams = (sid: string) => {
    if (!sid) return;
    
    console.log(`Configurazione degli stream per la sessione ${sid}...`);
    
    // Callback per aggiornare la trascrizione
    const onTranscription = (update: TranscriptionUpdate) => {
      console.log(`Ricevuto aggiornamento trascrizione: ${update.text}`);
      // Non facciamo nulla con la trascrizione per ora
    };
    
    // Callback per gestire le risposte
    const onResponse = (update: ResponseUpdate) => {
      console.log(`Ricevuta risposta: ${update.text}`);
      setMessages(prevMessages => {
        // Trova l'ultimo messaggio dell'assistente
        const lastAssistantIndex = [...prevMessages].reverse().findIndex(m => m.role === 'assistant');
        
        // Se c'è già un messaggio dell'assistente e non è la risposta finale,
        // aggiorna quel messaggio invece di aggiungerne uno nuovo
        if (lastAssistantIndex !== -1 && !update.final) {
          const reversedIndex = lastAssistantIndex;
          const actualIndex = prevMessages.length - 1 - reversedIndex;
          
          const newMessages = [...prevMessages];
          newMessages[actualIndex] = {
            ...newMessages[actualIndex],
            content: update.text
          };
          
          return newMessages;
        } else if (update.final) {
          // Se è la risposta finale, aggiungi un nuovo messaggio
          return [...prevMessages, { role: 'assistant', content: update.text }];
        } else {
          // Se non c'è un messaggio dell'assistente, aggiungine uno nuovo
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
    
    // Callback per gestire gli errori di connessione
    const onConnectionError = (error: Event) => {
      console.error('Errore di connessione SSE:', error);
      setIsConnected(false);
      setIsStreamError(true);
    };
    
    // Callback per lo stato della connessione
    const onConnectionStatus = (connected: boolean) => {
      console.log(`Stato connessione cambiato: ${connected ? 'connesso' : 'disconnesso'}`);
      setIsConnected(connected);
    };
    
    // Configurazione dello stream
    const streamHandler = useSessionStream(sid, {
      onTranscription,
      onResponse,
      onError,
      onConnectionError,
      onConnectionStatus
    });
    
    // Salva la funzione di pulizia
    setCleanupStream(() => streamHandler.cleanup);
    
    // Avvia la connessione
    setIsConnected(true);
  };

  // Gestione dell'avvio e interruzione della sessione
  const toggleSession = async () => {
    if (isSessionActive) {
      // Interrompi la sessione
      console.log("Interruzione della sessione...");
      
      // Ferma la registrazione audio se attiva
      if (isRecording && audioControl) {
        audioControl.stop();
        setIsRecording(false);
      }
      
      // Pulisci gli stream se necessario
      if (cleanupStream) {
        try {
          cleanupStream();
          setCleanupStream(null);
        } catch (error) {
          console.error("Errore durante la pulizia degli stream:", error);
        }
      }
      
      // Termina la sessione sul server
      if (sessionId) {
        await apiClient.endSession(sessionId);
        setIsSessionActive(false);
      }
    } else {
      // Avvia una nuova sessione
      console.log("Avvio di una nuova sessione...");
      
      let sid = sessionId;
      
      if (!sid) {
        // Se non c'è una sessione, creane una nuova
        try {
          sid = await apiClient.createSession();
          setSessionId(sid);
          console.log(`Nuova sessione creata: ${sid}`);
        } catch (error) {
          console.error("Errore nella creazione della sessione:", error);
          return;
        }
      }
      
      // Avvia la sessione sul server
      try {
        const success = await apiClient.startSession(sid);
        
        if (success) {
          console.log(`Sessione ${sid} avviata con successo`);
          setIsSessionActive(true);
          
          // Configura gli stream
          setupStreams(sid);
        } else {
          console.error(`Errore nell'avvio della sessione ${sid}`);
        }
      } catch (error) {
        console.error("Errore durante l'avvio della sessione:", error);
      }
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !sessionId || !isSessionActive) return;
    
    try {
      // Aggiungi il messaggio dell'utente
      setMessages(prev => [...prev, { role: 'user', content: inputMessage }]);
      
      // Aggiungi un messaggio di attesa dall'assistente
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sto elaborando la tua richiesta...' }]);
      
      // Pulisci l'input
      setInputMessage("");
      
      // Invia il messaggio di testo
      const result = await apiClient.sendTextMessage(sessionId, inputMessage);
      
      if (!result) {
        // Rimuovi il messaggio di attesa
        setMessages(prev => prev.slice(0, prev.length - 1));
        
        // Aggiungi messaggio di errore
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: 'Si è verificato un errore durante l\'invio del messaggio.' }
        ]);
      }
      
      // La risposta verrà gestita tramite gli eventi SSE
    } catch (error) {
      console.error("Errore nell'invio del messaggio:", error);
      
      // Rimuovi il messaggio di attesa
      setMessages(prev => prev.slice(0, prev.length - 1));
      
      // Aggiungi messaggio di errore
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Si è verificato un errore durante l\'invio del messaggio.' }
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
      // Aggiungi un messaggio di attesa
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sto pensando su questa conversazione...' }]);
      
      // Avvia il processo di pensiero
      await apiClient.startThinkProcess(sessionId);
      
      // La risposta verrà gestita tramite gli eventi SSE
    } catch (error) {
      console.error("Errore nell'avvio del processo di pensiero:", error);
      
      // Rimuovi il messaggio di attesa
      setMessages(prev => prev.slice(0, prev.length - 1));
      
      // Aggiungi messaggio di errore
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Si è verificato un errore durante il processo di pensiero.' }
      ]);
    }
  };

  const handleAnalyzeScreenshot = async () => {
    if (!sessionId || !isSessionActive) return;
    
    try {
      // Ottieni l'indice del monitor
      const monitorIndex = selectedScreen.replace('screen', '');
      
      // Aggiungi un messaggio di attesa
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sto catturando e analizzando lo schermo...' }]);
      
      // Cattura e analizza lo screenshot
      await apiClient.takeScreenshot(sessionId, monitorIndex);
      
      // La risposta verrà gestita tramite gli eventi SSE
    } catch (error) {
      console.error("Errore nella cattura dello screenshot:", error);
      
      // Rimuovi il messaggio di attesa
      setMessages(prev => prev.slice(0, prev.length - 1));
      
      // Aggiungi messaggio di errore
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Si è verificato un errore durante la cattura dello screenshot.' }
      ]);
    }
  };

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
      a.download = `conversation-${sessionId}-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      // Mostra una conferma
      setMessages(prev => [
        ...prev,
        { role: 'system', content: 'Conversazione salvata con successo!' }
      ]);
    } catch (error) {
      console.error("Errore nel salvataggio della conversazione:", error);
      
      // Mostra un messaggio di errore
      setMessages(prev => [
        ...prev,
        { role: 'system', content: 'Si è verificato un errore durante il salvataggio della conversazione.' }
      ]);
    }
  };

  const handleClear = () => {
    setMessages([]);
  };

  const toggleRecording = () => {
    if (!isSessionActive) return;
    
    // Crea il controllo audio se non esiste
    if (!audioControl && sessionId) {
      const control = useAudioStream(sessionId);
      setAudioControl(control);
      
      // Avvia la registrazione
      control.start();
      setIsRecording(true);
    } else if (audioControl) {
      // Toggle dello stato di registrazione
      if (isRecording) {
        audioControl.stop();
      } else {
        audioControl.start();
      }
      
      setIsRecording(!isRecording);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-50">
      <header className="p-4 border-b border-slate-800 flex justify-between items-center">
        <h1 className="text-xl font-bold">ChatGPT Integrato</h1>
        <div className="flex items-center space-x-2">
          <Select value={selectedScreen} onValueChange={setSelectedScreen}>
            <SelectTrigger className="w-[100px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="screen1">Schermo 1</SelectItem>
              <SelectItem value="screen2">Schermo 2</SelectItem>
              <SelectItem value="screen3">Schermo 3</SelectItem>
            </SelectContent>
          </Select>
          <Button 
            variant={isSessionActive ? "destructive" : "default"}
            onClick={toggleSession}
            title={isSessionActive ? "Termina sessione" : "Avvia sessione"}
          >
            {isSessionActive ? <Square size={16} /> : <Play size={16} />}
          </Button>
          <Button 
            variant="ghost" 
            onClick={handleClear}
            title="Pulisci la chat"
          >
            <Trash2 size={16} />
          </Button>
          <Button 
            variant="ghost" 
            onClick={handleSaveConversation}
            title="Salva la conversazione"
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
            title="Pensa"
          >
            <Brain size={16} />
          </Button>
          <Button 
            variant="ghost" 
            size="sm"
            onClick={handleAnalyzeScreenshot}
            disabled={!isSessionActive}
            title="Analizza schermo"
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
          <Button 
            variant={isRecording ? "destructive" : "ghost"}
            size="sm"
            onClick={toggleRecording}
            disabled={!isSessionActive}
            title={isRecording ? "Ferma registrazione" : "Inizia registrazione"}
          >
            {isRecording ? <MicOff size={16} /> : <Mic size={16} />}
          </Button>
          <div className="ml-auto text-xs text-slate-400">
            {isConnected ? 'Connesso' : 'Disconnesso'}
            {isStreamError && ' - Errore di streaming'}
          </div>
        </div>
        <div className="flex space-x-2">
          <Input
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Scrivi un messaggio..."
            disabled={!isSessionActive}
            className="bg-slate-800 border-slate-700"
          />
          <Button 
            onClick={handleSendMessage} 
            disabled={!isSessionActive || !inputMessage.trim()}
          >
            Invia
          </Button>
        </div>
      </div>
    </div>
  )
}

