"use client";

import { useState, useEffect } from 'react';
import supabase from '@/utils/supabase';
import { useAuth } from '../context/AuthContext';

export type UserSettings = {
  id: string;
  user_id: string;
  openai_key: string | null;
  created_at: string;
  updated_at: string;
};

export const useUserSettings = () => {
  const { user } = useAuth();
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch user settings
  const fetchSettings = async () => {
    if (!user) return;

    setIsLoading(true);
    setError(null);

    try {
      const { data, error } = await supabase
        .from('user_settings')
        .select('*')
        .eq('user_id', user.id)
        .single();

      if (error && error.code !== 'PGRST116') { // No rows returned is not an error in this case
        throw error;
      }
      
      setSettings(data);
    } catch (err) {
      console.error('Error fetching settings:', err);
      setError('Failed to load user settings');
    } finally {
      setIsLoading(false);
    }
  };

  // Update OpenAI API key
  const updateOpenAIKey = async (key: string) => {
    if (!user) return;

    setIsLoading(true);
    setError(null);

    try {
      // Use upsert to create or update
      const { data, error } = await supabase
        .from('user_settings')
        .upsert(
          { 
            user_id: user.id, 
            openai_key: key,
            updated_at: new Date().toISOString()
          },
          { onConflict: 'user_id' }
        )
        .select();

      if (error) throw error;
      
      if (data && data.length > 0) {
        setSettings(data[0]);
      }
    } catch (err) {
      console.error('Error updating OpenAI key:', err);
      setError('Failed to update OpenAI key');
    } finally {
      setIsLoading(false);
    }
  };

  // Clear OpenAI API key
  const clearOpenAIKey = async () => {
    if (!user || !settings) return;

    setIsLoading(true);
    setError(null);

    try {
      const { data, error } = await supabase
        .from('user_settings')
        .update({ 
          openai_key: null,
          updated_at: new Date().toISOString()
        })
        .eq('user_id', user.id)
        .select();

      if (error) throw error;
      
      if (data && data.length > 0) {
        setSettings(data[0]);
      }
    } catch (err) {
      console.error('Error clearing OpenAI key:', err);
      setError('Failed to clear OpenAI key');
    } finally {
      setIsLoading(false);
    }
  };

  // Load settings when user changes
  useEffect(() => {
    if (user) {
      fetchSettings();
    } else {
      setSettings(null);
    }
  }, [user]);

  return {
    settings,
    isLoading,
    error,
    fetchSettings,
    updateOpenAIKey,
    clearOpenAIKey,
    hasOpenAIKey: !!settings?.openai_key
  };
}; 