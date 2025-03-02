# Intervista Assistant

Un assistente AI per colloqui tecnici con frontend React/Next.js.

## Struttura del progetto

Il progetto è organizzato in due parti principali:

1. **Backend API** (Python/FastAPI): Gestisce la logica dell'applicazione e le connessioni con l'API di OpenAI
2. **Frontend** (React/Next.js): Interfaccia utente moderna e reattiva

## Prerequisiti

- Python 3.8+
- [Poetry](https://python-poetry.org/docs/#installation) per la gestione delle dipendenze Python
- Node.js 18+
- npm o yarn
- Un account OpenAI con una chiave API valida

## Configurazione

### Backend (Python)

1. Clonare il repository
2. Installare le dipendenze con Poetry:
   ```bash
   poetry install
   ```
3. Creare un file `.env` nella directory principale con il seguente contenuto:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   ```

### Frontend (Next.js)

1. Accedere alla directory del frontend:
   ```bash
   cd frontend
   ```
2. Installare le dipendenze:
   ```bash
   npm install
   # oppure
   yarn install
   ```
3. Creare un file `.env.local` con il seguente contenuto:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

## Avvio dell'applicazione

### Avvio del Backend API

```bash
# Dalla directory principale del progetto
poetry run start-api
# oppure
poetry run python -m intervista_assistant.api_launcher
```

Il server API sarà disponibile all'indirizzo `http://localhost:8000`.

### Avvio del Frontend Next.js

```bash
# Dalla directory frontend
npm run dev
# oppure
yarn dev
```

L'applicazione frontend sarà disponibile all'indirizzo `http://localhost:3000`.

## Funzionalità

- Invio di messaggi testuali
- Registrazione e trascrizione audio
- Analisi di screenshot
- Supporto per analisi avanzata ("Think")
- Interfaccia utente moderna e reattiva

## Description

Interview Assistant is a desktop application that helps software developers during technical job interviews. The application records the interview audio, transcribes it using GPT-4o Audio, detects technical questions, and generates detailed answers using GPT-4o.

The answers are displayed both in the main interface and in easily accessible popups during the interview.

## Main Features

- **Real-Time Audio Transcription**: Records and transcribes audio during interviews.
- **Automatic Question Detection**: Automatically detects when a question is asked.
- **Detailed Technical Answers**: Generates technical answers using GPT-4o.
- **Answer Popups**: Displays answers in popups for easy consultation during the interview.
- **Screenshot Functionality**: Allows capturing, saving, and sharing screenshots of the interview.
- **Conversation Saving**: Saves the entire conversation in JSON format.

## Requirements

- Python 3.8 or higher
- OpenAI API key (to use GPT-4o)
- Dependencies listed in `requirements.txt`

## Installation

1. Clone the repository or download the files:
   ```
   git clone https://github.com/your-username/intervista-assistant.git
   cd intervista-assistant
   ```

2. Install the dependencies:
   ```
   pip install -r intervista_assistant/requirements.txt
   ```

3. Create a `.env` file in the `intervista_assistant` directory based on the `.env.example` file:
   ```
   cp intervista_assistant/.env.example intervista_assistant/.env
   ```

4. Edit the `.env` file by inserting your OpenAI API key:
   ```
   OPENAI_API_KEY=your-openai-api-key-here
   ```

## Usage

You can start the application in one of the following ways:

1. Running the main script:
   ```
   python run.py
   ```

2. Running the launcher from within the intervista_assistant directory:
   ```
   cd intervista_assistant
   python launcher.py
   ```

## User Guide

1. Press the "Start Recording" button to begin recording audio.
2. Speak clearly, asking technical questions related to software development.
3. The application will automatically detect questions and generate answers.
4. Answers will appear in the "Answer" area and in a popup.
5. Use the "Screenshot" button to capture the screen during the interview.
6. The "Share Screenshot" button allows saving and copying the image path.
7. At the end of the interview, use "Save Conversation" to save the conversation in JSON.

## Project Structure
