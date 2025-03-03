#!/bin/bash

# Verifica se ci sono processi Node.js in esecuzione sulla porta 3000
if lsof -i:3000 -t &> /dev/null; then
  echo "La porta 3000 è già in uso. Chiudi il processo prima di avviare l'applicazione."
  exit 1
fi

# Verifica se ci sono processi Python in esecuzione sulla porta 8000
if lsof -i:8000 -t &> /dev/null; then
  echo "La porta 8000 è già in uso. Chiudi il processo prima di avviare l'applicazione."
  exit 1
fi

# Determina il percorso della directory corrente (dove si trova lo script)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/intervista_assistant"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Verifica che le directory esistano
if [ ! -d "$BACKEND_DIR" ]; then
  echo "Directory backend non trovata: $BACKEND_DIR"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "Directory frontend non trovata: $FRONTEND_DIR"
  exit 1
fi

# Avvia il backend
echo "Avvio del backend API (FastAPI)..."
cd "$BACKEND_DIR" 
# Imposto PYTHONPATH per includere la directory corrente
PYTHONPATH="$BACKEND_DIR:$PYTHONPATH" python api_launcher.py &
BACKEND_PID=$!
echo "Backend avviato con PID: $BACKEND_PID"

# Attendi che il backend sia pronto (5 secondi)
echo "Attendi che il backend sia pronto..."
sleep 5

# Avvia il frontend
echo "Avvio del frontend (Next.js)..."
cd "$FRONTEND_DIR" 
npm run dev &
FRONTEND_PID=$!
echo "Frontend avviato con PID: $FRONTEND_PID"

# Gestione chiusura con Ctrl+C
trap "echo 'Chiusura dei processi...'; kill $BACKEND_PID; kill $FRONTEND_PID; exit 0" INT

# Mantieni lo script in esecuzione
echo "L'applicazione è in esecuzione. Premi Ctrl+C per terminare."
wait 