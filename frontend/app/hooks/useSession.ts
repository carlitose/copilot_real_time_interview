import { useState, useCallback, useEffect } from 'react';
import apiClient from '@/utils/api';
import { Message } from '@/app/types/chat';
import { AudioStreamControl, useAudioStream } from '@/utils/socketio';

interface SessionHookResult {
  sessionId: string | null;
  isSessionActive: boolean;
  isRecording: boolean;
  audioStreamControl: AudioStreamControl | null;
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  toggleSession: () => Promise<void>;
  sendTextMessage: (text: string) => Promise<void>;
  startThinkProcess: () => Promise<void>;
  saveConversation: () => Promise<void>;
  clearMessages: () => void;
  deleteMessage: (index: number) => void;
  toggleRecording: () => void;
}

export function useSession(): SessionHookResult {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSessionActive, setIsSessionActive] = useState(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [messages, setMessages] = useState<Message[]>([]);
  
  // Initialize audio control with the useAudioStream hook
  const audioStreamControl = useAudioStream(sessionId || '');
  
  // Initialize session on component mount
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

  // Toggle session (start/stop)
  const toggleSession = useCallback(async () => {
    if (isSessionActive) {
      // Stop the session
      console.log("Stopping the session...");
      
      // Stop audio recording if active
      if (isRecording) {
        audioStreamControl.stop();
        setIsRecording(false);
      }
      
      // End the session on the server
      if (sessionId) {
        try {
          await apiClient.endSession(sessionId);
        } catch (error) {
          console.error("Error ending session:", error);
        } finally {
          // Indicate session is inactive
          setIsSessionActive(false);
          // Keep the sessionId for history, but mark as ended
          console.log(`Session ${sessionId} ended.`);
          
          // Add a system message indicating the session has ended
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
        
        // Add a system message indicating the start of a new session
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
        alert("Unable to start a new session. Please reload the page and try again.");
      }
    }
  }, [isSessionActive, isRecording, sessionId, audioStreamControl, setMessages]);

  // Send text message
  const sendTextMessage = useCallback(async (text: string) => {
    if (!text.trim() || !sessionId || !isSessionActive) return;
    
    try {
      // Add the user's message
      setMessages(prev => [...prev, { role: 'user', content: text }]);
      
      // Add a waiting message from the assistant
      setMessages(prev => [...prev, { role: 'log', content: 'Processing your request...' }]);
      
      // Send the text message
      const result = await apiClient.sendTextMessage(sessionId, text);
      
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
  }, [sessionId, isSessionActive]);

  // Start think process
  const startThinkProcess = useCallback(async () => {
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
  }, [sessionId, isSessionActive]);

  // Save conversation
  const saveConversation = useCallback(async () => {
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
  }, [sessionId]);

  // Clear all messages
  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  // Delete a specific message
  const deleteMessage = useCallback((indexToDelete: number) => {
    setMessages(prevMessages => prevMessages.filter((_, index) => index !== indexToDelete));
  }, []);

  // Toggle recording
  const toggleRecording = useCallback(() => {
    if (!isSessionActive || !sessionId) {
      alert('Please start a session first.');
      return;
    }
    
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
  }, [isSessionActive, sessionId, isRecording, audioStreamControl]);

  return {
    sessionId,
    isSessionActive,
    isRecording,
    audioStreamControl,
    messages,
    setMessages,
    toggleSession,
    sendTextMessage,
    startThinkProcess,
    saveConversation,
    clearMessages,
    deleteMessage,
    toggleRecording
  };
} 