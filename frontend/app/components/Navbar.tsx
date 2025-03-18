"use client";

import { useAuth } from "@/app/context/AuthContext";

export default function Navbar() {
  const { user, signOut } = useAuth();

  return (
    <div className="p-4 border-b border-slate-800 flex justify-between items-center">
      <h1 className="text-xl font-bold">AI Assistant Audio</h1>
      {user && (
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-400">{user.email}</span>
          <button
            onClick={signOut}
            className="px-3 py-1 text-sm bg-slate-800 hover:bg-slate-700 rounded-md transition"
          >
            Logout
          </button>
        </div>
      )}
    </div>
  );
} 