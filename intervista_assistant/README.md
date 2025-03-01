# Intervista Assistant

Un assistente per i colloqui di lavoro per sviluppatori software che utilizza GPT-4o di OpenAI.

## Caratteristiche

- **Trascrizione Audio in Tempo Reale**: Registra e trascrive l'audio durante le interviste.
- **Rilevamento Domande**: Rileva automaticamente quando viene posta una domanda.
- **Generazione Risposte**: Genera risposte tecniche dettagliate utilizzando GPT-4o.
- **Popup con Risposte**: Mostra le risposte in popup facilmente consultabili durante l'intervista.
- **Cattura Screenshot**: Permette di catturare e salvare schermate dell'intervista.
- **Salvataggio Conversazioni**: Salva l'intera conversazione in formato JSON.

## Requisiti

- Python 3.8+
- OpenAI API key (per utilizzare GPT-4o)
- Le dipendenze elencate in `requirements.txt`

## Installazione

1. Clona il repository o scarica i file
2. Installa le dipendenze:
   ```
   pip install -r requirements.txt
   ```
3. Crea un file `.env` nella directory principale con la tua API key OpenAI:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

## Utilizzo

1. Avvia l'applicazione:
   ```
   python main.py
   ```
2. Premi il pulsante "Inizia Registrazione" per iniziare a registrare l'audio
3. Parla chiaramente, facendo domande pertinenti a tematiche di sviluppo software
4. L'app rileverà automaticamente le domande e genererà risposte
5. Utilizza il pulsante "Screenshot" per catturare lo schermo durante l'intervista
6. Alla fine, salva la conversazione con il pulsante "Salva Conversazione"

## Note

- Le risposte vengono generate utilizzando GPT-4o, quindi potrebbero richiedere alcuni secondi
- Per risultati ottimali, fai domande chiare e specifiche su argomenti di sviluppo software
- Le risposte sono ottimizzate per colloqui tecnici di programmazione

## Licenza

MIT 