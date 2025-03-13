import { Play, Square, Trash2, Save, Brain, Camera, Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ControlBarProps {
  isSessionActive: boolean;
  isConnected: boolean;
  isStreamError: boolean;
  isRecording: boolean;
  isCapturingScreen: boolean;
  onToggleSession: () => void;
  onAnalyzeScreenshot: () => void;
  onThink: () => void;
  onSaveConversation: () => void;
  onClear: () => void;
  onToggleRecording: () => void;
}

export default function ControlBar({
  isSessionActive,
  isConnected,
  isStreamError,
  isRecording,
  isCapturingScreen,
  onToggleSession,
  onAnalyzeScreenshot,
  onThink,
  onSaveConversation,
  onClear,
  onToggleRecording
}: ControlBarProps) {
  return (
    <div className="flex items-center space-x-2 mb-2">
      <Button 
        variant="ghost"
        size="sm"
        onClick={onToggleSession}
        title={isSessionActive ? "End session" : "Start session"}
      >
        {isSessionActive ? <Square size={16} /> : <Play size={16} />}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={onAnalyzeScreenshot}
        disabled={!isSessionActive || isCapturingScreen}
        title="Capture and analyze screen"
      >
        <Camera className="h-4 w-4" />
        {isCapturingScreen && <span className="ml-2">Capturing...</span>}
      </Button>
      <Button 
        variant="ghost" 
        size="sm"
        onClick={onThink}
        disabled={!isSessionActive}
        title="Think"
      >
        <Brain size={16} />
      </Button>
      <Button 
        variant="ghost" 
        size="sm"
        onClick={onSaveConversation}
        title="Save conversation"
        disabled={!isSessionActive}
      >
        <Save size={16} />
      </Button>
      <Button 
        variant="ghost" 
        size="sm"
        onClick={onClear}
        title="Clear chat"
      >
        <Trash2 size={16} />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={onToggleRecording}
        disabled={!isSessionActive}
        title={isRecording ? "Stop recording" : "Start recording"}
      >
        {isRecording ? <MicOff size={16} /> : <Mic size={16} />}
      </Button>
      <div className="ml-auto text-xs text-slate-400">
        {isConnected ? 'Connected' : 'Disconnected'}
        {isStreamError && ' - Streaming error'}
        {isRecording && ' - 🎤 Recording active'}
      </div>
    </div>
  );
} 