import asyncio
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI()

    # Apri la connessione con il modello specificato
    async with client.beta.realtime.connect(model="gpt-4o-realtime-preview") as connection:
        
        # Imposta la sessione per usare solo la modalità testo
        await connection.session.update(session={'modalities': ['text']})
        print("Session update inviato.")

        # Invia un messaggio utente
        await connection.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Say hello!"}],
            }
        )
        print("Messaggio utente inviato.")

        # Richiedi la risposta
        await connection.response.create()
        print("Richiesta di risposta inviata.")

        # Gestione degli eventi (inclusi errori)
        async for event in connection:
            if event.type == 'response.text.delta':
                print(event.delta, end="", flush=True)
            elif event.type == 'response.text.done':
                print("\n--- Risposta di testo completata ---")
            elif event.type == "error":
                print("\n--- Evento di errore ricevuto ---")
                print("Tipo errore:", event.error.type)
                print("Codice:", event.error.code)
                print("Event ID:", event.error.event_id)
                print("Messaggio:", event.error.message)
            elif event.type == "response.done":
                print("Risposta completata. Uscita.")
                break

asyncio.run(main()) 