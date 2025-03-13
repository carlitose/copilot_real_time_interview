import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface MessageInputProps {
  isSessionActive: boolean;
  onSendMessage: (message: string) => void;
}

export default function MessageInput({ isSessionActive, onSendMessage }: MessageInputProps) {
  const [inputMessage, setInputMessage] = useState("");

  const handleSendMessage = () => {
    if (!inputMessage.trim() || !isSessionActive) return;
    onSendMessage(inputMessage);
    setInputMessage("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex space-x-2">
      <Input
        value={inputMessage}
        onChange={(e) => setInputMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message..."
        disabled={!isSessionActive}
        className="bg-slate-800 border-slate-700"
      />
      <Button 
        onClick={handleSendMessage} 
        disabled={!isSessionActive || !inputMessage.trim()}
      >
        Send
      </Button>
    </div>
  );
} 