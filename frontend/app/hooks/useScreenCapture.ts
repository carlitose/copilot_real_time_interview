import { useState, useEffect, useCallback } from 'react';
import { getAvailableScreens, captureScreenshot, ScreenInfo } from '@/utils/screenCapture';
import apiClient from '@/utils/api';
import { Message } from '@/app/types/chat';

interface ScreenCaptureHookProps {
  sessionId: string | null;
  isSessionActive: boolean;
  isConnected: boolean;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
}

interface ScreenCaptureHookResult {
  isCapturingScreen: boolean;
  availableScreens: ScreenInfo[];
  selectedScreen: string;
  setSelectedScreen: React.Dispatch<React.SetStateAction<string>>;
  handleAnalyzeScreenshot: () => Promise<void>;
}

export function useScreenCapture({
  sessionId,
  isSessionActive,
  isConnected,
  setMessages
}: ScreenCaptureHookProps): ScreenCaptureHookResult {
  const [isCapturingScreen, setIsCapturingScreen] = useState(false);
  const [selectedScreen, setSelectedScreen] = useState("screen1");
  const [availableScreens, setAvailableScreens] = useState<ScreenInfo[]>([]);

  // Load available screens when component mounts
  useEffect(() => {
    async function loadScreens() {
      const screens = await getAvailableScreens();
      setAvailableScreens(screens);
      
      if (screens.length > 0) {
        setSelectedScreen(screens[0].id);
      }
    }
    
    // Load screens only once on startup
    loadScreens();
  }, []);

  const handleAnalyzeScreenshot = useCallback(async () => {
    if (!sessionId || !isSessionActive) return;
    
    try {
      setIsCapturingScreen(true);
      
      // Add a waiting message with a unique identifier
      const messageId = `screenshot-${Date.now()}`;
      // @ts-ignore - Adding temporary id for tracking this message
      setMessages(prev => [...prev, { 
        role: 'log', 
        content: 'Capturing and analyzing the screen... (please wait a few seconds)',
        id: messageId 
      }]);
      
      // Capture the screenshot from the browser
      const imageData = await captureScreenshot(selectedScreen);
      
      if (imageData) {
        // Show a preview of the captured screenshot (optional)
        setMessages(prev => prev.map(msg => 
          // @ts-ignore - Using temporary id for tracking
          msg.id === messageId ? 
          { ...msg, content: 'Capturing and analyzing the screen... (image sent to server)' } : 
          msg
        ));
        
        // Send the captured screenshot to the backend
        const success = await apiClient.sendScreenshot(sessionId, imageData);
        
        if (!success) {
          throw new Error("Error sending screenshot to backend");
        }
        
        // Let the user know we're waiting for analysis
        setMessages(prev => prev.map(msg => 
          // @ts-ignore - Using temporary id for tracking
          msg.id === messageId ? 
          { ...msg, content: 'Screenshot sent! Waiting for server analysis...' } : 
          msg
        ));
      } else {
        throw new Error("Unable to capture screenshot");
      }
      
      // The response will be handled via SSE events
    } catch (error) {
      console.error("Error capturing screenshot:", error);
      
      // Add an error message
      setMessages(prev => [
        ...prev,
        { role: 'log', content: `An error occurred while capturing the screenshot: ${error instanceof Error ? error.message : 'Unknown error'}` }
      ]);
    } finally {
      setIsCapturingScreen(false);
    }
  }, [sessionId, isSessionActive, selectedScreen, setMessages]);

  return {
    isCapturingScreen,
    availableScreens,
    selectedScreen,
    setSelectedScreen,
    handleAnalyzeScreenshot
  };
} 