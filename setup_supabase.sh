#!/bin/bash

# Script per configurare Supabase
echo "Configurazione del database Supabase locale..."

# Percorso dello script SQL temporaneo
TEMP_SQL_FILE="/tmp/supabase_setup.sql"

# Variabili per la connessione a PostgreSQL
PGHOST="127.0.0.1"
PGPORT="54322"  # Porta di default per PostgreSQL in Supabase locale
PGUSER="postgres"
PGPASSWORD="postgres"  # Password di default per Supabase locale
PGDATABASE="postgres"

echo "Host: $PGHOST, Port: $PGPORT, User: $PGUSER, Database: $PGDATABASE"

# SQL per la creazione delle tabelle e delle policy
cat > $TEMP_SQL_FILE << 'EOL'
-- Create user_settings table
CREATE TABLE IF NOT EXISTS public.user_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    openai_key TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(user_id)
);

-- Create prompts table
CREATE TABLE IF NOT EXISTS public.prompts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Create conversations table
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Create messages table
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE CASCADE NOT NULL,
    content TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Create Row Level Security (RLS) policies
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

-- Drop existing policies (to prevent errors if they already exist)
DO $$ 
BEGIN
    -- Drop user_settings policies if they exist
    BEGIN
        DROP POLICY IF EXISTS "Users can view their own settings" ON public.user_settings;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can insert their own settings" ON public.user_settings;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can update their own settings" ON public.user_settings;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    -- Drop prompts policies if they exist
    BEGIN
        DROP POLICY IF EXISTS "Users can view their own prompts" ON public.prompts;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can insert their own prompts" ON public.prompts;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can update their own prompts" ON public.prompts;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can delete their own prompts" ON public.prompts;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    -- Drop conversations policies if they exist
    BEGIN
        DROP POLICY IF EXISTS "Users can view their own conversations" ON public.conversations;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can insert their own conversations" ON public.conversations;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can delete their own conversations" ON public.conversations;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    -- Drop messages policies if they exist
    BEGIN
        DROP POLICY IF EXISTS "Users can view messages from their conversations" ON public.messages;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can insert messages to their conversations" ON public.messages;
    EXCEPTION WHEN OTHERS THEN
    END;
    
    BEGIN
        DROP POLICY IF EXISTS "Users can delete messages from their conversations" ON public.messages;
    EXCEPTION WHEN OTHERS THEN
    END;
END $$;

-- User settings policies
CREATE POLICY "Users can view their own settings" 
ON public.user_settings FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own settings" 
ON public.user_settings FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own settings" 
ON public.user_settings FOR UPDATE 
USING (auth.uid() = user_id);

-- Prompts policies
CREATE POLICY "Users can view their own prompts" 
ON public.prompts FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own prompts" 
ON public.prompts FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own prompts" 
ON public.prompts FOR UPDATE 
USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own prompts" 
ON public.prompts FOR DELETE 
USING (auth.uid() = user_id);

-- Conversations policies
CREATE POLICY "Users can view their own conversations" 
ON public.conversations FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own conversations" 
ON public.conversations FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own conversations" 
ON public.conversations FOR DELETE 
USING (auth.uid() = user_id);

-- Messages policies
CREATE POLICY "Users can view messages from their conversations" 
ON public.messages FOR SELECT 
USING (
  conversation_id IN (
    SELECT id FROM public.conversations WHERE user_id = auth.uid()
  )
);

CREATE POLICY "Users can insert messages to their conversations" 
ON public.messages FOR INSERT 
WITH CHECK (
  conversation_id IN (
    SELECT id FROM public.conversations WHERE user_id = auth.uid()
  )
);

CREATE POLICY "Users can delete messages from their conversations" 
ON public.messages FOR DELETE 
USING (
  conversation_id IN (
    SELECT id FROM public.conversations WHERE user_id = auth.uid()
  )
);
EOL

echo "Script SQL creato in $TEMP_SQL_FILE"

# Nome del container del database Supabase
DB_CONTAINER="supabase_db_supabase-local"

# Verifico se il container è in esecuzione
if docker ps | grep -q "$DB_CONTAINER"; then
  echo "Database Supabase trovato in esecuzione..."
  
  echo "Container del database: $DB_CONTAINER"
  
  # Copia il file SQL nel container
  docker cp $TEMP_SQL_FILE $DB_CONTAINER:/tmp/setup.sql
  
  # Esegui lo script SQL
  echo "Esecuzione dello script SQL su Supabase..."
  docker exec -i $DB_CONTAINER psql -U postgres -d postgres -f /tmp/setup.sql
  
  # Elimina il file SQL dal container
  docker exec -i $DB_CONTAINER rm /tmp/setup.sql
else
  echo "ERRORE: Container $DB_CONTAINER non trovato in esecuzione."
  echo "Per favore, assicurati che Supabase sia avviato utilizzando 'supabase start' o 'docker-compose up' prima di eseguire questo script."
  exit 1
fi

# Elimina il file SQL temporaneo
rm $TEMP_SQL_FILE

echo "Configurazione di Supabase completata." 