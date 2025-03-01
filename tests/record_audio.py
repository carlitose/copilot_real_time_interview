import sounddevice as sd
import soundfile as sf

duration = 20  # Durata in secondi
sample_rate = 44100  # Frequenza di campionamento
filename = 'audio_20sec.wav'

print("Inizio registrazione...")
audio_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
sd.wait()  # aspetta la fine della registrazione
sf.write(filename, audio_data, sample_rate)
print(f"Registrazione salvata in {filename}") 