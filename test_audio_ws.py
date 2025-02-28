import os
import json
import time
import base64
import websocket

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv('OPENAI_API_KEY')
if not API_KEY:
    raise Exception("Per favore imposta la variabile d'ambiente OPENAI_API_KEY")

# URL del servizio Realtime API (verifica che l'endpoint supporti il modello)
url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
headers = [
    "Authorization: Bearer " + API_KEY,
    "OpenAI-Beta: realtime=v1",
    "Content-Type: application/json"
]

# Importa il convertitore dall'audio_util
from audio_util import audio_to_pcm16_base64

def on_open(ws):
    print("Connessione WebSocket aperta.")
    
    # Aggiorna la configurazione della sessione per abilitare entrambe le modalità: audio e text
    session_config = {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"]
        }
    }
    ws.send(json.dumps(session_config))
    print("Session update (audio, text) inviato.")
    
    time.sleep(0.5)
    
    # Invia il messaggio di sistema per impostare il contesto della conversazione
    system_instructions = (
        "Sei un assistente AI per interviste di lavoro, specializzato in domande per software engineer.\n"
        "Rispondi in modo conciso e strutturato con elenchi puntati dove appropriato.\n"
        "Focalizzati sugli aspetti tecnici, i principi di design, le best practice e gli algoritmi.\n"
        "Non essere prolisso. Fornisci esempi pratici dove utile.\n"
        "Le tue risposte saranno mostrate a schermo durante un'intervista, quindi sii chiaro e diretto."
    )
    system_message = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": system_instructions}]
        }
    }
    ws.send(json.dumps(system_message))
    print("Messaggio di sistema inviato.")
    
    time.sleep(0.5)
    
    # Legge il file audio di 20 secondi, lo converte in PCM16 e poi lo codifica in base64
    audio_file_path = "audio_20sec.wav"
    try:
        with open(audio_file_path, "rb") as f:
            audio_bytes = f.read()
    except Exception as e:
        print(f"Errore nella lettura del file audio: {e}")
        ws.close()
        return
    
    # Converte l'audio nel formato PCM16 (24 kHz, mono, 16 bit)
    pcm_audio = audio_to_pcm16_base64(audio_bytes)
    # Codifica i dati PCM16 in base64
    audio_b64 = base64.b64encode(pcm_audio).decode('utf-8')
    
    # Invia il messaggio utente contenente l'audio convertito
    audio_message = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{
                "type": "input_audio",
                "audio": audio_b64,
                "mime": "audio/wav"
            }]
        }
    }
    ws.send(json.dumps(audio_message))
    print("Messaggio audio utente inviato.")
    
    # Invia la richiesta per ottenere la risposta (modalità audio e text)
    response_request = {
        "type": "response.create",
        "response": {"modalities": ["audio", "text"]}
    }
    ws.send(json.dumps(response_request))
    print("Richiesta di risposta inviata.")

def on_message(ws, message):
    try:
        event = json.loads(message)
        event_type = event.get("type", "")
        
        if event_type == "response.audio.delta":
            # Ricezione della risposta audio in streaming
            delta = event.get("delta", "")
            print("Audio in streaming ricevuto...", flush=True)
        
        elif event_type == "response.audio_transcript.delta":
            # Ricezione della trascrizione parziale dell'audio
            delta = event.get("delta", "")
            print(delta, end="", flush=True)
            
        elif event_type == "response.audio_transcript.done":
            transcript = event.get("transcript", "")
            print("\n--- Trascrizione completata ---")
            print("Transcript:", transcript)
        
        elif event_type == "response.text.delta":
            # Ricezione della risposta testuale in streaming
            delta = event.get("delta", "")
            print(delta, end="", flush=True)
        
        elif event_type == "response.text.done":
            print("\n--- Risposta testuale completata ---\n")
        
        elif event_type == "response.done":
            print("Risposta completata. Chiudo la connessione.")
            ws.close()
            
    except Exception as e:
        print("Eccezione in on_message:", e)

def on_error(ws, error):
    print("Errore:", error)

def on_close(ws, close_status_code, close_msg):
    print("Connessione WebSocket chiusa:", close_status_code, close_msg)

if __name__ == "__main__":
    # Abilita il tracing per il debug se necessario
    websocket.enableTrace(True)
    ws = websocket.WebSocketApp(
        url,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever() 