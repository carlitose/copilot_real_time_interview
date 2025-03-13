"use client";

import { useState, useEffect } from 'react';
import supabase from '@/utils/supabase';
import { useAuth } from '../context/AuthContext';

export type Prompt = {
  id: string;
  user_id: string;
  title: string;
  content: string;
  created_at: string;
};

export const usePrompts = () => {
  const { user } = useAuth();
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch user prompts
  const fetchPrompts = async () => {
    if (!user) return;

    setIsLoading(true);
    setError(null);

    try {
      const { data, error } = await supabase
        .from('prompts')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false });

      if (error) throw error;
      setPrompts(data || []);
    } catch (err) {
      console.error('Error fetching prompts:', err);
      setError('Failed to load prompts');
    } finally {
      setIsLoading(false);
    }
  };

  // Create a new prompt
  const createPrompt = async (title: string, content: string) => {
    if (!user) return null;

    try {
      const { data, error } = await supabase
        .from('prompts')
        .insert([{ user_id: user.id, title, content }])
        .select()
        .single();

      if (error) throw error;
      
      setPrompts(prev => [data, ...prev]);
      return data;
    } catch (err) {
      console.error('Error creating prompt:', err);
      setError('Failed to create prompt');
      return null;
    }
  };

  // Update existing prompt
  const updatePrompt = async (id: string, title: string, content: string) => {
    if (!user) return;

    try {
      const { error } = await supabase
        .from('prompts')
        .update({ title, content })
        .eq('id', id)
        .eq('user_id', user.id);

      if (error) throw error;
      
      // Update local state
      setPrompts(prev => 
        prev.map(p => p.id === id ? { ...p, title, content } : p)
      );
    } catch (err) {
      console.error('Error updating prompt:', err);
      setError('Failed to update prompt');
    }
  };

  // Delete a prompt
  const deletePrompt = async (id: string) => {
    if (!user) return;

    try {
      const { error } = await supabase
        .from('prompts')
        .delete()
        .eq('id', id)
        .eq('user_id', user.id);

      if (error) throw error;
      
      // Update local state
      setPrompts(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      console.error('Error deleting prompt:', err);
      setError('Failed to delete prompt');
    }
  };

  // Load prompts when user changes
  useEffect(() => {
    if (user) {
      fetchPrompts();
    } else {
      setPrompts([]);
    }
  }, [user]);

  return {
    prompts,
    isLoading,
    error,
    fetchPrompts,
    createPrompt,
    updatePrompt,
    deletePrompt
  };
}; 