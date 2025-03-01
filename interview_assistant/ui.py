#!/usr/bin/env python3

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, QLabel, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import time


class InterviewAssistantUI(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Set up the overall widget layout
        self.main_layout = QVBoxLayout(self)

        # Create the splitter for input and response areas
        self.splitter = QSplitter(Qt.Vertical, self)

        # Input container
        self.input_container = QWidget(self)
        self.input_layout = QVBoxLayout(self.input_container)
        self.input_label = QLabel("User input (audio):", self.input_container)
        self.input_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.transcription_text = QTextEdit(self.input_container)
        self.transcription_text.setReadOnly(True)
        self.transcription_text.setFont(QFont("Arial", 13))
        self.transcription_text.setMinimumHeight(150)
        self.input_layout.addWidget(self.input_label)
        self.input_layout.addWidget(self.transcription_text)

        # Response container
        self.response_container = QWidget(self)
        self.response_layout = QVBoxLayout(self.response_container)
        self.response_label = QLabel("Response:", self.response_container)
        self.response_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.response_text = QTextEdit(self.response_container)
        self.response_text.setReadOnly(True)
        self.response_text.setFont(QFont("Arial", 13))
        self.response_text.setAcceptRichText(True)
        self.response_layout.addWidget(self.response_label)
        self.response_layout.addWidget(self.response_text)

        # Add input and response containers to splitter
        self.splitter.addWidget(self.input_container)
        self.splitter.addWidget(self.response_container)
        self.splitter.setSizes([300, 500])

        # Controls layout
        self.controls_layout = QHBoxLayout()
        self.record_button = QPushButton("Start Session", self)
        self.record_button.setFont(QFont("Arial", 13))
        self.clear_button = QPushButton("Clear", self)
        self.clear_button.setFont(QFont("Arial", 13))
        self.screenshot_button = QPushButton("Screenshot", self)
        self.screenshot_button.setFont(QFont("Arial", 13))
        self.share_button = QPushButton("Share Screenshot", self)
        self.share_button.setFont(QFont("Arial", 13))
        self.save_button = QPushButton("Save Conversation", self)
        self.save_button.setFont(QFont("Arial", 13))

        # Add controls to layout
        self.controls_layout.addWidget(self.record_button)
        self.controls_layout.addWidget(self.clear_button)
        self.controls_layout.addWidget(self.screenshot_button)
        self.controls_layout.addWidget(self.share_button)
        self.controls_layout.addWidget(self.save_button)

        # Add splitter and controls layout to main layout
        self.main_layout.addWidget(self.splitter)
        self.main_layout.addLayout(self.controls_layout)

        # Optional: Set a margin or spacing if desired
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(10) 