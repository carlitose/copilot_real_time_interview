#!/usr/bin/env python3
import os
import time
import requests
import tempfile
from pathlib import Path
from datetime import datetime
import logging

import mss
import mss.tools
import pyautogui
from PIL import Image
import pyperclip

logger = logging.getLogger(__name__)

class ScreenshotManager:
    """Classe per gestire screenshot e condivisione."""
    
    def __init__(self, base_dir=None):
        """Inizializza il gestore di screenshot.
        
        Args:
            base_dir: Directory di base per salvare gli screenshot
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path.cwd() / "screenshots"
            
        # Crea la directory se non esiste
        self.base_dir.mkdir(exist_ok=True)
        
        # Inizializza mss per gli screenshot
        self.sct = mss.mss()
    
    def get_monitors(self):
        """Ottiene l'elenco dei monitor disponibili.
        
        Returns:
            list: Lista dei monitor disponibili con le loro dimensioni
        """
        try:
            monitors = self.sct.monitors
            # Il primo elemento (index 0) è l'unione di tutti i monitor
            # Ritorniamo i monitor individuali a partire da index 1
            return monitors[1:]
        except Exception as e:
            logger.error(f"Errore nel recupero dei monitor: {str(e)}")
            return []
    
    def take_screenshot(self, delay=0.5, monitor_index=None):
        """Cattura uno screenshot dello schermo selezionato o dello schermo intero.
        
        Args:
            delay: Ritardo in secondi prima di catturare lo screenshot
            monitor_index: Indice del monitor da catturare (None = schermo intero)
        
        Returns:
            Path: Percorso del file screenshot salvato
        """
        try:
            # Attendi per il ritardo specificato
            time.sleep(delay)
            
            # Genera nome file con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = self.base_dir / filename
            
            # Cattura e salva lo screenshot
            if monitor_index is not None:
                # Ottieni l'elenco dei monitor
                monitors = self.get_monitors()
                if 0 <= monitor_index < len(monitors):
                    # Cattura lo screenshot del monitor specificato
                    monitor = monitors[monitor_index]
                    screenshot = self.sct.grab(monitor)
                    mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))
                else:
                    logger.warning(f"Indice monitor non valido: {monitor_index}, utilizzo schermo intero")
                    screenshot = pyautogui.screenshot()
                    screenshot.save(str(filepath))
            else:
                # Cattura lo screenshot dello schermo intero
                screenshot = pyautogui.screenshot()
                screenshot.save(str(filepath))
            
            logger.info(f"Screenshot salvato in: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Errore durante la cattura dello screenshot: {str(e)}")
            raise
    
    def upload_to_temp_service(self, filepath):
        """Carica l'immagine su un servizio temporaneo.
        
        Args:
            filepath: Percorso del file da caricare
            
        Returns:
            str: URL dell'immagine caricata
        """
        try:
            # Per questo esempio, utilizziamo imgbb.com
            # In un'applicazione reale, potrebbe essere necessario un account API
            # o un servizio diverso
            
            # Apri il file in modalità binaria
            with open(filepath, "rb") as file:
                # Prepara i dati per la richiesta
                files = {"image": (filepath.name, file, "image/png")}
                
                # Invia la richiesta al servizio
                response = requests.post(
                    "https://api.imgbb.com/1/upload",
                    files=files,
                    params={"key": os.getenv("IMGBB_API_KEY", "")}
                )
                
                # Verifica la risposta
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        url = data["data"]["url"]
                        logger.info(f"Immagine caricata con successo: {url}")
                        return url
                
                logger.error(f"Errore nel caricamento dell'immagine: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Errore durante il caricamento dell'immagine: {str(e)}")
            return None
    
    def copy_to_clipboard(self, filepath):
        """Copia l'immagine negli appunti.
        
        Args:
            filepath: Percorso del file da copiare negli appunti
            
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        try:
            # Apri l'immagine
            image = Image.open(filepath)
            
            # Copia negli appunti
            # Nota: questo funziona in modo diverso su diverse piattaforme
            # Potrebbe richiedere implementazioni specifiche per sistema operativo
            
            # Su macOS, possiamo usare pyperclip per copiare il percorso del file
            pyperclip.copy(str(filepath))
            
            logger.info(f"Percorso immagine copiato negli appunti: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Errore durante la copia negli appunti: {str(e)}")
            return False 