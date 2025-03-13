"use client"
import { useEffect } from "react"
import Link from 'next/link'

// Importing components
import MessageList from '@/app/components/chat/MessageList'
import MessageInput from '@/app/components/chat/MessageInput'
import ControlBar from '@/app/components/chat/ControlBar'

// Importing hooks
import { useSession } from '@/app/hooks/useSession'
import { useEventStream } from '@/app/hooks/useEventStream'
import { useScreenCapture } from '@/app/hooks/useScreenCapture'
import { useAuth } from '@/app/context/AuthContext'
import { useConversations } from '@/app/hooks/useConversations'
import { useUserSettings } from '@/app/hooks/useUserSettings'

// Constant for the API base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';
console.log("API base URL:", API_BASE_URL);

export default function ChatGPTInterface() {
  // Use auth hooks
  const { user, signOut } = useAuth();
  const { conversations, createConversation, saveMessages } = useConversations();
  const { settings } = useUserSettings();

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

  // Save conversation to Supabase when user clicks save
  const handleSaveConversation = async () => {
    if (!user || messages.length === 0) return;
    
    try {
      // First create a conversation
      const title = messages[0]?.content.substring(0, 50) + '...';
      const conversation = await createConversation(title);
      
      if (conversation) {
        // Then save all messages
        await saveMessages(
          conversation.id,
          messages.map(msg => ({
            content: msg.content,
            role: msg.role as 'user' | 'assistant' | 'system'
          }))
        );
        
        // Call the original save function as well (if needed)
        saveConversation();
        
        alert('Conversation saved successfully!');
      }
    } catch (error) {
      console.error('Error saving conversation:', error);
      alert('Failed to save conversation. Please try again.');
    }
  };

  // Inject OpenAI key from settings if available
  useEffect(() => {
    if (settings?.openai_key) {
      // Here you would typically set the key for your API calls
      console.log('OpenAI key is available');
      // You could store this in a context or send with each request
    }
  }, [settings]);

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
      <header className="p-4 border-b border-slate-800 flex justify-between items-center">
        <h1 className="text-xl font-bold">AI Assistant Audio</h1>
        <div className="flex items-center space-x-4">
          <Link href="/settings" className="px-4 py-2 bg-slate-800 rounded-md hover:bg-slate-700 text-sm">
            Settings
          </Link>
        </div>
      </header>
      
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
          onSaveConversation={handleSaveConversation}
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