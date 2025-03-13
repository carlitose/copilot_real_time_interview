"use client";

import { useEffect, useState } from 'react';
import supabase from '@/utils/supabase';
import { useAuth } from '../context/AuthContext';

// Types for conversation data
export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  user_id: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  content: string;
  role: 'user' | 'assistant' | 'system';
  created_at: string;
};

export const useConversations = () => {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch user's conversations
  const fetchConversations = async () => {
    if (!user) return;

    setIsLoading(true);
    setError(null);

    try {
      const { data, error } = await supabase
        .from('conversations')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false });

      if (error) throw error;
      setConversations(data || []);
    } catch (err) {
      console.error('Error fetching conversations:', err);
      setError('Failed to load conversations');
    } finally {
      setIsLoading(false);
    }
  };

  // Create a new conversation
  const createConversation = async (title: string) => {
    if (!user) return null;

    try {
      const { data, error } = await supabase
        .from('conversations')
        .insert([{ user_id: user.id, title }])
        .select()
        .single();

      if (error) throw error;
      
      setConversations(prev => [data, ...prev]);
      return data;
    } catch (err) {
      console.error('Error creating conversation:', err);
      setError('Failed to create conversation');
      return null;
    }
  };

  // Save messages to a conversation
  const saveMessages = async (conversationId: string, messages: Omit<Message, 'id' | 'conversation_id' | 'created_at'>[]) => {
    if (!user) return;

    try {
      const { error } = await supabase
        .from('messages')
        .insert(
          messages.map(msg => ({
            conversation_id: conversationId,
            content: msg.content,
            role: msg.role
          }))
        );

      if (error) throw error;
    } catch (err) {
      console.error('Error saving messages:', err);
      setError('Failed to save messages');
    }
  };

  // Get messages for a conversation
  const getMessages = async (conversationId: string): Promise<Message[]> => {
    if (!user) return [];

    try {
      const { data, error } = await supabase
        .from('messages')
        .select('*')
        .eq('conversation_id', conversationId)
        .order('created_at', { ascending: true });

      if (error) throw error;
      return data || [];
    } catch (err) {
      console.error('Error fetching messages:', err);
      setError('Failed to load messages');
      return [];
    }
  };

  // Delete a conversation
  const deleteConversation = async (conversationId: string) => {
    if (!user) return;

    try {
      // First delete all messages
      const { error: messagesError } = await supabase
        .from('messages')
        .delete()
        .eq('conversation_id', conversationId);

      if (messagesError) throw messagesError;

      // Then delete the conversation
      const { error } = await supabase
        .from('conversations')
        .delete()
        .eq('id', conversationId);

      if (error) throw error;

      // Update state
      setConversations(prev => prev.filter(c => c.id !== conversationId));
    } catch (err) {
      console.error('Error deleting conversation:', err);
      setError('Failed to delete conversation');
    }
  };

  // Fetch conversations when user changes
  useEffect(() => {
    if (user) {
      fetchConversations();
    } else {
      setConversations([]);
    }
  }, [user]);

  return {
    conversations,
    isLoading,
    error,
    fetchConversations,
    createConversation,
    saveMessages,
    getMessages,
    deleteConversation
  };
}; 