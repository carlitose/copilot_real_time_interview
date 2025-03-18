"use client"

import { createContext, useContext, useEffect, useState } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { supabase } from '@/utils/supabase';

type AuthContextType = {
  user: User | null;
  session: Session | null;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: any }>;
  signUp: (email: string, password: string) => Promise<{ error: any, user: User | null }>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Recupera la sessione iniziale e configura listener
    let subscription: { unsubscribe: () => void } | undefined;
    
    const initAuth = async () => {
      try {
        setIsLoading(true);
        
        // Recupera la sessione corrente
        const { data: { session: currentSession } } = await supabase.auth.getSession();
        console.log("Sessione iniziale:", currentSession ? "Presente" : "Assente");
        
        if (currentSession) {
          setSession(currentSession);
          setUser(currentSession.user);
        }
        
        // Configura listener per i cambiamenti di auth
        const { data } = supabase.auth.onAuthStateChange(
          (_event, session) => {
            console.log("Cambiamento stato auth:", _event, session ? "Sessione presente" : "Sessione assente");
            setSession(session);
            setUser(session?.user ?? null);
          }
        );
        
        subscription = data.subscription;
      } catch (error) {
        console.error("Errore durante l'inizializzazione dell'autenticazione:", error);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
    
    // Funzione di cleanup
    return () => {
      if (subscription) {
        subscription.unsubscribe();
      }
    };
  }, []);

  const signIn = async (email: string, password: string) => {
    try {
      console.log("Tentativo di login con:", email);
      const { data, error } = await supabase.auth.signInWithPassword({ 
        email, 
        password 
      });
      
      if (error) {
        console.error("Errore di autenticazione:", error);
        return { error };
      }
      
      console.log("Login riuscito, sessione:", data.session ? "Valida" : "Non valida");
      
      if (data.session) {
        // Esplicita impostazione della sessione e dell'utente
        setSession(data.session);
        setUser(data.user);
      }
      
      return { error: null };
    } catch (error) {
      console.error("Errore imprevisto durante il login:", error);
      return { error };
    }
  };

  const signUp = async (email: string, password: string) => {
    try {
      const { data, error } = await supabase.auth.signUp({ 
        email, 
        password,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        }
      });
      
      if (!error && data.user) {
        return { error: null, user: data.user };
      }
      
      return { error, user: data.user };
    } catch (error) {
      console.error("Errore durante la registrazione:", error);
      return { error, user: null };
    }
  };

  const signOut = async () => {
    try {
      await supabase.auth.signOut();
      setSession(null);
      setUser(null);
      window.location.href = "/login";
    } catch (error) {
      console.error("Errore durante il logout:", error);
    }
  };

  const value = {
    user,
    session,
    isLoading,
    signIn,
    signUp,
    signOut,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
} 