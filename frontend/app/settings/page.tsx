"use client";

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../context/AuthContext';
import { useUserSettings } from '../hooks/useUserSettings';
import { usePrompts } from '../hooks/usePrompts';

export default function SettingsPage() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const { settings, updateOpenAIKey, clearOpenAIKey, isLoading: isSettingsLoading } = useUserSettings();
  const { prompts, createPrompt, updatePrompt, deletePrompt, isLoading: isPromptsLoading } = usePrompts();
  
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [savingApiKey, setSavingApiKey] = useState(false);
  
  const [promptTitle, setPromptTitle] = useState('');
  const [promptContent, setPromptContent] = useState('');
  const [editingPromptId, setEditingPromptId] = useState<string | null>(null);
  const [savingPrompt, setSavingPrompt] = useState(false);

  // Redirect if not logged in
  useEffect(() => {
    if (!user && !isSettingsLoading) {
      router.push('/login');
    }
  }, [user, isSettingsLoading, router]);

  // Set API key from settings
  useEffect(() => {
    if (settings?.openai_key) {
      setApiKey(settings.openai_key);
    }
  }, [settings]);

  // Handle API key save
  const handleSaveApiKey = async () => {
    if (!apiKey.trim()) return;

    setSavingApiKey(true);
    try {
      await updateOpenAIKey(apiKey);
      alert('API key saved successfully!');
      setShowApiKey(false);
    } catch (error) {
      console.error('Error saving API key:', error);
      alert('Failed to save API key. Please try again.');
    } finally {
      setSavingApiKey(false);
    }
  };

  // Handle API key clear
  const handleClearApiKey = async () => {
    if (!confirm('Are you sure you want to remove your API key?')) return;

    try {
      await clearOpenAIKey();
      setApiKey('');
      alert('API key removed successfully!');
    } catch (error) {
      console.error('Error clearing API key:', error);
      alert('Failed to remove API key. Please try again.');
    }
  };

  // Handle prompt save
  const handleSavePrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptTitle.trim() || !promptContent.trim()) return;

    setSavingPrompt(true);
    try {
      if (editingPromptId) {
        await updatePrompt(editingPromptId, promptTitle, promptContent);
        alert('Prompt updated successfully!');
      } else {
        await createPrompt(promptTitle, promptContent);
        alert('Prompt created successfully!');
      }
      setPromptTitle('');
      setPromptContent('');
      setEditingPromptId(null);
    } catch (error) {
      console.error('Error saving prompt:', error);
      alert('Failed to save prompt. Please try again.');
    } finally {
      setSavingPrompt(false);
    }
  };

  // Start editing a prompt
  const handleEditPrompt = (id: string, title: string, content: string) => {
    setEditingPromptId(id);
    setPromptTitle(title);
    setPromptContent(content);
  };

  // Handle prompt delete
  const handleDeletePrompt = async (id: string) => {
    if (!confirm('Are you sure you want to delete this prompt?')) return;

    try {
      await deletePrompt(id);
      if (editingPromptId === id) {
        setEditingPromptId(null);
        setPromptTitle('');
        setPromptContent('');
      }
    } catch (error) {
      console.error('Error deleting prompt:', error);
      alert('Failed to delete prompt. Please try again.');
    }
  };

  // Handle logout
  const handleLogout = async () => {
    await signOut();
    router.push('/login');
  };

  if (!user) {
    return <div className="flex h-screen items-center justify-center">Loading...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-slate-800 bg-slate-900 p-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <h1 className="text-xl font-bold">Settings</h1>
          <div className="flex space-x-4">
            <button
              onClick={() => router.push('/')}
              className="rounded-md bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700"
            >
              Back to Chat
            </button>
            <button
              onClick={handleLogout}
              className="rounded-md bg-red-600 px-4 py-2 text-sm hover:bg-red-700"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl p-6">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          {/* API Key Section */}
          <section className="rounded-lg bg-slate-900 p-6 shadow-lg">
            <h2 className="mb-4 text-xl font-semibold">OpenAI API Key</h2>
            <div className="space-y-4">
              <div>
                <label htmlFor="apiKey" className="block text-sm font-medium text-slate-300">
                  API Key
                </label>
                <div className="mt-1 flex">
                  <input
                    id="apiKey"
                    type={showApiKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="block w-full rounded-md border-slate-700 bg-slate-800 px-3 py-2 text-white shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm"
                    placeholder="sk-..."
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="ml-2 rounded-md bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700"
                  >
                    {showApiKey ? "Hide" : "Show"}
                  </button>
                </div>
              </div>
              <div className="flex space-x-4">
                <button
                  type="button"
                  onClick={handleSaveApiKey}
                  disabled={savingApiKey}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {savingApiKey ? "Saving..." : "Save Key"}
                </button>
                {settings?.openai_key && (
                  <button
                    type="button"
                    onClick={handleClearApiKey}
                    className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium hover:bg-red-700"
                  >
                    Remove Key
                  </button>
                )}
              </div>
            </div>
          </section>

          {/* Prompt Templates Section */}
          <section className="rounded-lg bg-slate-900 p-6 shadow-lg">
            <h2 className="mb-4 text-xl font-semibold">Prompt Templates</h2>
            <form onSubmit={handleSavePrompt} className="mb-6 space-y-4">
              <div>
                <label htmlFor="promptTitle" className="block text-sm font-medium text-slate-300">
                  Title
                </label>
                <input
                  id="promptTitle"
                  type="text"
                  value={promptTitle}
                  onChange={(e) => setPromptTitle(e.target.value)}
                  className="mt-1 block w-full rounded-md border-slate-700 bg-slate-800 px-3 py-2 text-white shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm"
                  placeholder="E.g., Code Review"
                />
              </div>
              <div>
                <label htmlFor="promptContent" className="block text-sm font-medium text-slate-300">
                  Content
                </label>
                <textarea
                  id="promptContent"
                  value={promptContent}
                  onChange={(e) => setPromptContent(e.target.value)}
                  rows={4}
                  className="mt-1 block w-full rounded-md border-slate-700 bg-slate-800 px-3 py-2 text-white shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm"
                  placeholder="Enter your prompt template..."
                />
              </div>
              <div className="flex space-x-4">
                <button
                  type="submit"
                  disabled={savingPrompt}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {savingPrompt ? "Saving..." : editingPromptId ? "Update Prompt" : "Save Prompt"}
                </button>
                {editingPromptId && (
                  <button
                    type="button"
                    onClick={() => {
                      setEditingPromptId(null);
                      setPromptTitle('');
                      setPromptContent('');
                    }}
                    className="rounded-md bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>

            <div className="space-y-4">
              <h3 className="text-lg font-medium">Your Prompts</h3>
              {isPromptsLoading ? (
                <p>Loading prompts...</p>
              ) : prompts.length === 0 ? (
                <p className="text-slate-400">No prompt templates yet. Create your first one!</p>
              ) : (
                <ul className="space-y-3">
                  {prompts.map((prompt) => (
                    <li key={prompt.id} className="rounded-md border border-slate-800 p-3">
                      <div className="flex justify-between">
                        <h4 className="font-medium">{prompt.title}</h4>
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleEditPrompt(prompt.id, prompt.title, prompt.content)}
                            className="text-sm text-blue-400 hover:text-blue-300"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeletePrompt(prompt.id)}
                            className="text-sm text-red-400 hover:text-red-300"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      <p className="mt-1 text-sm text-slate-300">{prompt.content.length > 100 ? `${prompt.content.substring(0, 100)}...` : prompt.content}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
} 