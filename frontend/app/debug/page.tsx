"use client";

import { useAuth } from "../context/AuthContext";
import { useEffect, useState } from "react";
import Link from "next/link";

export default function DebugPage() {
  const { user, session, isLoading, signOut } = useAuth();
  const [pageLoads, setPageLoads] = useState(0);

  useEffect(() => {
    // Incrementa il contatore delle volte che la pagina è stata caricata
    setPageLoads(prev => prev + 1);
  }, []);

  return (
    <div className="p-8 bg-slate-950 text-slate-100 min-h-screen">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">Authentication Debug</h1>
        
        <div className="bg-slate-900 p-6 rounded-lg shadow mb-6">
          <h2 className="text-xl font-semibold mb-4">Current State</h2>
          
          <div className="grid gap-4">
            <div>
              <span className="font-medium">Page loads:</span> {pageLoads}
            </div>
            <div>
              <span className="font-medium">Loading:</span>{" "}
              <span className={isLoading ? "text-yellow-400" : "text-green-400"}>
                {isLoading ? "Yes" : "No"}
              </span>
            </div>
            <div>
              <span className="font-medium">Authenticated:</span>{" "}
              <span className={user ? "text-green-400" : "text-red-400"}>
                {user ? "Yes" : "No"}
              </span>
            </div>
            {user && (
              <div>
                <div className="font-medium mb-1">User:</div>
                <pre className="bg-slate-800 p-3 rounded overflow-auto text-xs">
                  {JSON.stringify({
                    id: user.id,
                    email: user.email,
                    role: user.role,
                    created_at: user.created_at,
                  }, null, 2)}
                </pre>
              </div>
            )}
            {session && (
              <div>
                <div className="font-medium mb-1">Session:</div>
                <pre className="bg-slate-800 p-3 rounded overflow-auto text-xs">
                  {JSON.stringify({
                    expires_at: session.expires_at,
                    token_type: session.token_type,
                  }, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
        
        <div className="bg-slate-900 p-6 rounded-lg shadow mb-6">
          <h2 className="text-xl font-semibold mb-4">Actions</h2>
          
          <div className="flex flex-wrap gap-4">
            <Link
              href="/"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-md transition-colors"
            >
              Home
            </Link>
            
            <Link
              href="/login"
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors"
            >
              Login Page
            </Link>
            
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-md transition-colors"
            >
              Reload Page
            </button>
            
            {user && (
              <button
                onClick={signOut}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-md transition-colors"
              >
                Logout
              </button>
            )}
          </div>
        </div>
        
        <div className="bg-slate-900 p-6 rounded-lg shadow">
          <h2 className="text-xl font-semibold mb-4">URL and Environment</h2>
          
          <div className="grid gap-4">
            <div>
              <span className="font-medium">Current URL:</span>{" "}
              {typeof window !== "undefined" ? window.location.href : "N/A"}
            </div>
            <div>
              <span className="font-medium">User Agent:</span>{" "}
              <span className="text-xs break-all">
                {typeof navigator !== "undefined" ? navigator.userAgent : "N/A"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
} 