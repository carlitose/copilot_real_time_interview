import asyncio
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI()

    async with client.beta.realtime.connect(model="gpt-4o-realtime-preview") as connection:
        # Aggiorna la sessione in modalità solo testo
        await connection.session.update(session={'modalities': ['text']})
        
        # Crea e invia un messaggio utente
        await connection.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Ciao, come va?"}],
            }
        )
        
        # Richiedi la risposta
        await connection.response.create()

        # Itera sugli eventi ricevuti
        async for event in connection:
            if event.type == 'response.text.delta':
                print(event.delta, end="", flush=True)
            elif event.type == 'response.text.done':
                print("\n--- Risposta completata ---\n")
            elif event.type == 'response.done':
                break

if __name__ == "__main__":
    asyncio.run(main()) 