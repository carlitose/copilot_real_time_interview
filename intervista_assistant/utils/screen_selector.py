#!/usr/bin/env python3
import sys
import logging
import mss

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QListWidget, QListWidgetItem, 
                            QSizePolicy, QScrollArea, QWidget, QFrame)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QSize

logger = logging.getLogger(__name__)

class ScreenSelectorDialog(QDialog):
    """Finestra di dialogo per selezionare uno schermo da catturare."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Schermo")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        # Inizializza mss per gli screenshot
        self.sct = mss.mss()
        
        # Ottieni l'elenco dei monitor
        self.monitors = self.sct.monitors[1:]  # Escludiamo il monitor virtuale che è l'unione di tutti
        
        # Valore selezionato (indice del monitor)
        self.selected_monitor_index = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura l'interfaccia utente."""
        # Layout principale
        main_layout = QVBoxLayout(self)
        
        # Etichetta istruzioni
        instructions = QLabel("Seleziona lo schermo di cui vuoi catturare lo screenshot:")
        instructions.setWordWrap(True)
        main_layout.addWidget(instructions)
        
        # Contenitore per i monitor
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Aggiungi opzione per schermo intero
        full_screen_button = QPushButton("Schermo Intero (tutti i monitor)")
        full_screen_button.clicked.connect(lambda: self._on_monitor_selected(None))
        scroll_layout.addWidget(full_screen_button)
        
        # Aggiungi un separatore
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        scroll_layout.addWidget(separator)
        
        # Aggiungi i pulsanti per ogni monitor
        for i, monitor in enumerate(self.monitors):
            monitor_frame = QFrame()
            monitor_frame.setFrameShape(QFrame.StyledPanel)
            monitor_layout = QHBoxLayout(monitor_frame)
            
            # Info sul monitor
            info_label = QLabel(f"Monitor {i+1}: {monitor['width']}x{monitor['height']} "
                              f"({monitor['left']},{monitor['top']})")
            monitor_layout.addWidget(info_label, 1)
            
            # Pulsante per selezionare
            select_button = QPushButton("Seleziona")
            select_button.clicked.connect(lambda checked, idx=i: self._on_monitor_selected(idx))
            monitor_layout.addWidget(select_button)
            
            scroll_layout.addWidget(monitor_frame)
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)
        
        # Pulsanti di azione
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Annulla")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def _on_monitor_selected(self, index):
        """Gestisce la selezione di un monitor.
        
        Args:
            index: Indice del monitor selezionato (None per schermo intero)
        """
        self.selected_monitor_index = index
        self.accept()
    
    @staticmethod
    def get_selected_monitor(parent=None):
        """Mostra la finestra di dialogo e restituisce l'indice del monitor selezionato.
        
        Args:
            parent: Widget genitore
            
        Returns:
            int or None: Indice del monitor selezionato (None = schermo intero)
        """
        dialog = ScreenSelectorDialog(parent)
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            return dialog.selected_monitor_index
        else:
            return None 