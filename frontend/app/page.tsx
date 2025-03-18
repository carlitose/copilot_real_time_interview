"use client";

import ChatGPTInterface from "./chatgpt-interface"
import { useAuth } from "./context/AuthContext"
import { useEffect } from "react"

export default function Home() {
  const { user, isLoading } = useAuth();

  useEffect(() => {
    // Se l'utente non è autenticato, reindirizza al login
    if (!isLoading && !user) {
      console.log("Home: utente non autenticato, reindirizzamento al login...");
      window.location.href = "/login";
    }
  }, [user, isLoading]);

  // Mostra un loader durante il caricamento
  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-screen bg-slate-950 text-slate-50">
        <div className="text-center">
          <div className="w-16 h-16 border-t-4 border-blue-500 border-solid rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-xl">Caricamento...</p>
        </div>
      </div>
    );
  }

  // Se l'utente è autenticato, mostra l'interfaccia della chat
  if (user) {
    return (
      <main>
        <ChatGPTInterface />
      </main>
    );
  }

  // Questo non dovrebbe mai essere renderizzato grazie all'useEffect, ma per sicurezza
  return null;
}

