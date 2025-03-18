"use client";

import { useAuth } from "@/app/context/AuthContext";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const pathname = usePathname() || "";
  const [isRedirecting, setIsRedirecting] = useState(false);
  
  // Unico effetto per gestire tutti i reindirizzamenti
  useEffect(() => {
    // Non fare nulla se stiamo già reindirizzando o se è ancora in caricamento
    if (isRedirecting || isLoading) {
      return;
    }
    
    const isAuthPage = pathname === "/login" || pathname === "/signup" || pathname.startsWith("/auth/");
    
    // Caso 1: Utente non autenticato che tenta di accedere a una pagina protetta
    if (!user && !isAuthPage) {
      console.log("Accesso non autorizzato, reindirizzamento al login...");
      setIsRedirecting(true);
      window.location.href = "/login";
      return;
    }
    
    // Caso 2: Utente autenticato che tenta di accedere a pagine di login/signup
    if (user && isAuthPage && !pathname.startsWith("/auth/callback")) {
      console.log("Utente già autenticato su pagina di auth, reindirizzamento...");
      setIsRedirecting(true);
      window.location.href = "/";
      return;
    }
  }, [user, isLoading, pathname, isRedirecting]);

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

  // Non renderizzare i figli se stiamo reindirizzando
  if (isRedirecting) {
    return (
      <div className="flex justify-center items-center h-screen bg-slate-950 text-slate-50">
        <div className="text-center">
          <div className="w-16 h-16 border-t-4 border-blue-500 border-solid rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-xl">Reindirizzamento...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
} 