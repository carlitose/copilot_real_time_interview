#!/usr/bin/env python3
"""
Script di test per inviare l'intero audio (da file) in modalità streaming in un unico messaggio,
ispirato al funzionamento di push_to_talk_app.py.
"""

import asyncio
import base64
import sys

from openai import AsyncOpenAI
from tests.audio_util import audio_to_pcm16_base64, SAMPLE_RATE

async def receiver(conn):
    """Task per ricevere e stampare i messaggi dal server finché la connessione è aperta."""
    try:
        async for message in conn:
            print("Ricevuto:", message)
    except Exception as e:
        print("Errore nel receiver:", e)

async def send_audio_file():
    client = AsyncOpenAI()
    async with client.beta.realtime.connect(model="gpt-4o-realtime-preview") as conn:
        # Avvia il task di ricezione per mantenere la connessione attiva
        recv_task = asyncio.create_task(receiver(conn))

        try:
            # 1. Aggiorna la sessione per abilitare audio e testo
            session_update = {
                "type": "session.update",
                "session": {"modalities": ["audio", "text"]}
            }
            await conn.send(session_update)
            print("Session update (audio, text) inviato.")
            await asyncio.sleep(0.5)

            # 2. Invia il messaggio di sistema con le istruzioni
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
            await conn.send(system_message)
            print("Messaggio di sistema inviato.")
            await asyncio.sleep(0.5)

            # 3. Leggi e converti il file audio
            audio_file_path = "audio_20sec.wav"
            try:
                with open(audio_file_path, "rb") as f:
                    audio_bytes = f.read()
            except Exception as e:
                print(f"Errore nella lettura del file audio: {e}")
                return

            pcm_audio = audio_to_pcm16_base64(audio_bytes)
            print("Conversione audio completata, lunghezza (byte):", len(pcm_audio))

            # 4. Invia l'intero audio in un unico messaggio
            audio_b64 = base64.b64encode(pcm_audio).decode("utf-8")
            audio_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_audio", "audio": audio_b64}]
                }
            }
            try:
                await conn.send(audio_message)
                print("Messaggio audio inviato.")
            except Exception as e:
                print("Errore durante l'invio del messaggio audio:", e)

            # 5. (Facoltativo) Invia un breve chunk di silenzio per chiarire la fine dell'input
            silence_duration = 0.5  # secondi
            silence_samples = int(SAMPLE_RATE * silence_duration)
            silence_bytes = b"\x00\x00" * silence_samples
            silence_b64 = base64.b64encode(silence_bytes).decode("utf-8")
            silence_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_audio", "audio": silence_b64}]
                }
            }
            try:
                await conn.send(silence_message)
                print("Chunk di silenzio inviato.")
            except Exception as e:
                print("Errore durante l'invio del chunk di silenzio:", e)

            # 6. Invia il commit per segnalare la fine dell'input audio
            commit_message = {"type": "input_audio_buffer.commit"}
            try:
                await conn.send(commit_message)
                print("Commit dell'audio inviato.")
            except Exception as e:
                print("Errore durante l'invio del commit:", e)

            # 7. Invia la richiesta per la risposta (se prevista dalla logica della sessione)
            response_request = {
                "type": "response.create",
                "response": {"modalities": ["text"]}
            }
            try:
                await conn.send(response_request)
                print("Richiesta di risposta inviata.")
            except Exception as e:
                print("Errore nell'invio della richiesta di risposta:", e)

            # 8. Attendi alcuni secondi per ricevere la risposta prima di terminare la sessione
            await asyncio.sleep(5)
        except Exception as e:
            print("Errore nel flusso di comunicazione:", e)
        finally:
            # Termina il task di ricezione e chiudi la connessione
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass
            print("Sessione terminata.")

if __name__ == "__main__":
    try:
        asyncio.run(send_audio_file())
    except KeyboardInterrupt:
        sys.exit(0) 