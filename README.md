# Intervista Assistant

Un assistente per i colloqui di lavoro per sviluppatori software che utilizza GPT-4o Audio di OpenAI.

## Descrizione

Intervista Assistant è un'applicazione desktop che aiuta gli sviluppatori software durante i colloqui di lavoro tecnici. L'applicazione registra l'audio dell'intervista, lo trascrive usando GPT-4o Audio, rileva le domande tecniche e genera risposte dettagliate utilizzando GPT-4o.

Le risposte vengono mostrate sia nell'interfaccia principale che in popup facilmente consultabili durante l'intervista.

## Caratteristiche Principali

- **Trascrizione Audio in Tempo Reale**: Registra e trascrive l'audio durante le interviste.
- **Rilevamento Automatico di Domande**: Rileva automaticamente quando viene posta una domanda.
- **Risposte Tecniche Dettagliate**: Genera risposte tecniche utilizzando GPT-4o.
- **Popup con Risposte**: Mostra le risposte in popup per facile consultazione durante l'intervista.
- **Funzionalità Screenshot**: Permette di catturare, salvare e condividere schermate dell'intervista.
- **Salvataggio delle Conversazioni**: Salva l'intera conversazione in formato JSON.

## Requisiti

- Python 3.8 o superiore
- API key OpenAI (per utilizzare GPT-4o)
- Le dipendenze elencate in `requirements.txt`

## Installazione

1. Clona il repository o scarica i file:
   ```
   git clone https://github.com/tuo-username/intervista-assistant.git
   cd intervista-assistant
   ```

2. Installa le dipendenze:
   ```
   pip install -r intervista_assistant/requirements.txt
   ```

3. Crea un file `.env` nella directory `intervista_assistant` basato sul file `.env.example`:
   ```
   cp intervista_assistant/.env.example intervista_assistant/.env
   ```

4. Modifica il file `.env` inserendo la tua API key OpenAI:
   ```
   OPENAI_API_KEY=your-openai-api-key-here
   ```

## Utilizzo

Puoi avviare l'applicazione in uno dei seguenti modi:

1. Eseguendo lo script principale:
   ```
   python run.py
   ```

2. Eseguendo il launcher dall'interno della directory intervista_assistant:
   ```
   cd intervista_assistant
   python launcher.py
   ```

## Guida all'Uso

1. Premi il pulsante "Inizia Registrazione" per iniziare a registrare l'audio.
2. Parla chiaramente, facendo domande tecniche relative allo sviluppo software.
3. L'applicazione rileverà automaticamente le domande e genererà risposte.
4. Le risposte appariranno nell'area "Risposta" e in un popup.
5. Usa il pulsante "Screenshot" per catturare lo schermo durante l'intervista.
6. Il pulsante "Condividi Screenshot" permette di salvare e copiare il percorso dell'immagine.
7. Alla fine dell'intervista, usa "Salva Conversazione" per salvare la conversazione in JSON.

## Struttura del Progetto

```
intervista_assistant/
├── __init__.py
├── main.py           # Applicazione principale
├── launcher.py       # Script di avvio
├── requirements.txt  # Dipendenze
├── setup.py          # Script di installazione
├── .env.example      # Esempio per configurazione
├── README.md         # Documentazione
└── utils/            # Moduli di utilità
    ├── __init__.py
    ├── question_detector.py  # Rilevatore di domande
    └── screenshot_utils.py   # Utilità per screenshot
```

## Licenza

MIT

## Riconoscimenti

Questo progetto è basato su:
- OpenAI GPT-4o per la generazione delle risposte
- OpenAI Whisper per la trascrizione audio
- PyQt5 per l'interfaccia grafica
