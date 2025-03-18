"use client"
import { useEffect } from "react"

// Importing components
import Navbar from '@/app/components/Navbar'
import MessageList from '@/app/components/chat/MessageList'
import MessageInput from '@/app/components/chat/MessageInput'
import ControlBar from '@/app/components/chat/ControlBar'

// Importing hooks
import { useSession } from '@/app/hooks/useSession'
import { useEventStream } from '@/app/hooks/useEventStream'
import { useScreenCapture } from '@/app/hooks/useScreenCapture'

// Constant for the API base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';
console.log("API base URL:", API_BASE_URL);

export default function ChatGPTInterface() {
  // Use session hook
  const {
    sessionId,
    isSessionActive,
    isRecording,
    messages,
    setMessages,
    toggleSession,
    sendTextMessage,
    startThinkProcess,
    saveConversation,
    clearMessages,
    deleteMessage,
    toggleRecording
  } = useSession();

  // Use event stream hook
  const {
    isConnected,
    isStreamError,
    cleanupStream
  } = useEventStream({
    sessionId,
    isSessionActive,
    setMessages
  });

  // Use screen capture hook
  const {
    isCapturingScreen,
    availableScreens,
    selectedScreen,
    setSelectedScreen,
    handleAnalyzeScreenshot
  } = useScreenCapture({
    sessionId,
    isSessionActive,
    isConnected,
    setMessages
  });

  // Effect to clean up resources when component unmounts
  useEffect(() => {
    return () => {
      if (cleanupStream) {
        cleanupStream();
      }
    };
  }, [cleanupStream]);

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-50">
      <Navbar />
      
      <MessageList 
        messages={messages} 
        onDeleteMessage={deleteMessage} 
      />
      
      <div className="p-4 border-t border-slate-800 bg-slate-900">
        <ControlBar
          isSessionActive={isSessionActive}
          isConnected={isConnected}
          isStreamError={isStreamError}
          isRecording={isRecording}
          isCapturingScreen={isCapturingScreen}
          onToggleSession={toggleSession}
          onAnalyzeScreenshot={handleAnalyzeScreenshot}
          onThink={startThinkProcess}
          onSaveConversation={saveConversation}
          onClear={clearMessages}
          onToggleRecording={toggleRecording}
        />
        
        <MessageInput 
          isSessionActive={isSessionActive} 
          onSendMessage={sendTextMessage} 
        />
      </div>
    </div>
  )
} 