"use client";

import { useAuth } from "../context/AuthContext";
import { useState } from "react";
import Link from "next/link";

export default function AuthDebugPage() {
  const { user, session, isLoading, signOut } = useAuth();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-50 p-4">
      <div className="max-w-3xl mx-auto w-full">
        <h1 className="text-2xl font-bold mb-6">Debug Autenticazione</h1>
        
        <div className="p-4 mb-4 bg-slate-900 rounded-lg border border-slate-800">
          <h2 className="text-xl font-semibold mb-2">Stato</h2>
          <p className="mb-2">
            <span className="font-medium">In caricamento:</span>{" "}
            <span className={isLoading ? "text-yellow-500" : "text-green-500"}>
              {isLoading ? "Sì" : "No"}
            </span>
          </p>
          <p className="mb-2">
            <span className="font-medium">Autenticato:</span>{" "}
            <span className={user ? "text-green-500" : "text-red-500"}>
              {user ? "Sì" : "No"}
            </span>
          </p>
          {user && (
            <div className="mb-2">
              <p className="font-medium mb-1">Utente:</p>
              <pre className="bg-slate-800 p-2 rounded overflow-auto text-sm">
                {JSON.stringify({ id: user.id, email: user.email }, null, 2)}
              </pre>
            </div>
          )}
          
          <div className="mt-4">
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-blue-500 hover:underline text-sm"
            >
              {expanded ? "Nascondi dettagli" : "Mostra tutti i dettagli"}
            </button>
          </div>
          
          {expanded && session && (
            <div className="mt-4">
              <p className="font-medium mb-1">Sessione completa:</p>
              <pre className="bg-slate-800 p-2 rounded overflow-auto text-xs max-h-96">
                {JSON.stringify(session, null, 2)}
              </pre>
            </div>
          )}
        </div>
        
        <div className="flex gap-4">
          <Link
            href="/"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-md"
          >
            Torna alla Home
          </Link>
          
          {user && (
            <button
              onClick={signOut}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-md"
            >
              Logout
            </button>
          )}
          
          {!user && (
            <Link
              href="/login"
              className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-md"
            >
              Login
            </Link>
          )}
        </div>
      </div>
    </div>
  );
} 