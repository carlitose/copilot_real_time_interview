// Types for chat messages
export type MessageRole = 'user' | 'assistant' | 'system' | 'log';

export interface Message {
  role: MessageRole;
  content: string;
  id?: string; // Optional id for tracking specific messages
}

// Types for EventSource updates
export interface TranscriptionUpdate {
  type: 'transcription';
  text: string;
  session_id: string;
}

export interface ResponseUpdate {
  type: 'response';
  text: string;
  session_id: string;
  final: boolean;
}

export interface ErrorUpdate {
  type: 'error';
  message: string;
  session_id: string;
}

export interface ConnectionUpdate {
  type: 'connection';
  connected: boolean;
}

export interface LogUpdate {
  type: 'log';
  text: string;
}

export interface HeartbeatUpdate {
  type: 'heartbeat';
  timestamp: string;
}

export type EventUpdate = 
  | TranscriptionUpdate 
  | ResponseUpdate 
  | ErrorUpdate 
  | ConnectionUpdate 
  | LogUpdate 
  | HeartbeatUpdate;

// Screen capture types
export interface ScreenInfo {
  id: string;
  name: string;
} 