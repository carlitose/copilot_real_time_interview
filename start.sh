#!/bin/bash

# Uccidi eventuali processi precedenti sulle porte richieste
echo "Controllo e pulizia di processi esistenti..."
if lsof -i:3000 -t &> /dev/null; then
  echo "Terminazione dei processi sulla porta 3000..."
  kill $(lsof -i:3000 -t) 2>/dev/null || true
  sleep 1
fi

if lsof -i:8000 -t &> /dev/null; then
  echo "Terminazione dei processi sulla porta 8000..."
  kill $(lsof -i:8000 -t) 2>/dev/null || true
  sleep 1
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
echo "Avvio del backend API..."
cd "$BACKEND_DIR" 
# Imposto PYTHONPATH per includere la directory corrente
export PYTHONPATH="$SCRIPT_DIR:$BACKEND_DIR:$PYTHONPATH"
python api_launcher.py &
BACKEND_PID=$!
echo "Backend avviato con PID: $BACKEND_PID"

# Attendi che il backend sia pronto
echo "Attendi che il backend sia pronto..."
sleep 5

# Avvia il frontend
echo "Avvio del frontend (Next.js)..."
cd "$FRONTEND_DIR" 
npm run dev &
FRONTEND_PID=$!
echo "Frontend avviato con PID: $FRONTEND_PID"

# Funzione per terminare tutti i processi
cleanup() {
  echo 'Chiusura dei processi...'
  # Termina tutti i processi figlio
  pkill -P $$ || true
  # Termina esplicitamente i processi noti
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  exit 0
}

# Gestione chiusura con Ctrl+C e altri segnali
trap cleanup INT TERM

# Mantieni lo script in esecuzione
echo "L'applicazione è in esecuzione. Premi Ctrl+C per terminare."
wait 