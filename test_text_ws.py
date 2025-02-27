import os
import json
import time
import threading
import websocket

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv('OPENAI_API_KEY')
if not API_KEY:
    raise Exception("Per favore imposta la variabile d'ambiente OPENAI_API_KEY")

# Aggiorna l'URL per usare il modello coerente con gli esempi asincroni
url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
headers = [
    "Authorization: Bearer " + API_KEY,
    "OpenAI-Beta: realtime=v1",
    "Content-Type: application/json"
]

def on_open(ws):
    print("Connessione WebSocket aperta.")
    
    # Aggiorna la sessione in modalità solo testo
    session_config = {
        "type": "session.update",
        "session": {
            "modalities": ["text"]
        }
    }
    ws.send(json.dumps(session_config))
    print("Session update inviato.")
    
    # Breve pausa per garantire il setup
    time.sleep(0.5)
    
    # Invio di un messaggio di sistema (opzionale ma consigliato)
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
    
    # Invio del messaggio utente
    user_message = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Ciao, come va?"}]
        }
    }
    ws.send(json.dumps(user_message))
    print("Messaggio utente inviato.")
    
    # Richiesta della risposta
    response_request = {
        "type": "response.create",
        "response": { "modalities": ["text"] }
    }
    ws.send(json.dumps(response_request))
    print("Richiesta di risposta inviata.")

def on_message(ws, message):
    try:
        event = json.loads(message)
        event_type = event.get("type", "")
        if event_type == "response.text.delta":
            delta = event.get("delta", "")
            print(delta, end="", flush=True)
        elif event_type == "response.text.done":
            print("\n--- Risposta di testo completata ---\n")
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
    # Abilita il tracing, se necessario
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