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
    """Dialog window to select a screen to capture."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Screen")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        # Initialize mss for screenshots
        self.sct = mss.mss()
        
        # Get the list of monitors
        self.monitors = self.sct.monitors[1:]  # Exclude the virtual monitor which is the union of all
        
        # Selected value (monitor index)
        self.selected_monitor_index = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the user interface."""
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Instructions label
        instructions = QLabel("Select the screen you want to capture a screenshot of:")
        instructions.setWordWrap(True)
        main_layout.addWidget(instructions)
        
        # Container for monitors
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Add option for full screen
        full_screen_button = QPushButton("Full Screen (all monitors)")
        full_screen_button.clicked.connect(lambda: self._on_monitor_selected(None))
        scroll_layout.addWidget(full_screen_button)
        
        # Add a separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        scroll_layout.addWidget(separator)
        
        # Add buttons for each monitor
        for i, monitor in enumerate(self.monitors):
            monitor_frame = QFrame()
            monitor_frame.setFrameShape(QFrame.StyledPanel)
            monitor_layout = QHBoxLayout(monitor_frame)
            
            # Monitor info
            info_label = QLabel(f"Monitor {i+1}: {monitor['width']}x{monitor['height']} "
                              f"({monitor['left']},{monitor['top']})")
            monitor_layout.addWidget(info_label, 1)
            
            # Button to select
            select_button = QPushButton("Select")
            select_button.clicked.connect(lambda checked, idx=i: self._on_monitor_selected(idx))
            monitor_layout.addWidget(select_button)
            
            scroll_layout.addWidget(monitor_frame)
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)
        
        # Action buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def _on_monitor_selected(self, index):
        """Handles the selection of a monitor.
        
        Args:
            index: Index of the selected monitor (None for full screen)
        """
        self.selected_monitor_index = index
        self.accept()
    
    @staticmethod
    def get_selected_monitor(parent=None):
        """Displays the dialog and returns the index of the selected monitor.
        
        Args:
            parent: Parent widget
            
        Returns:
            int or None: Index of the selected monitor (None = full screen)
        """
        dialog = ScreenSelectorDialog(parent)
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            return dialog.selected_monitor_index
        else:
            return None 