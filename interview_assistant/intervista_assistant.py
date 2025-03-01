#!/usr/bin/env python3
import sys
import os
import time
import json
import logging
import asyncio
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from openai import OpenAI
from dotenv import load_dotenv

from .realtime_text_thread import RealtimeTextThread
from .utils import ScreenshotManager
from .ui import InterviewAssistantUI

# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

class InterviewAssistant(QMainWindow):
    """Main application for the interview assistant."""
    
    def __init__(self):
        super().__init__()
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            QMessageBox.critical(self, "API Key Error", 
                                 "OpenAI API Key not found. Set the OPENAI_API_KEY environment variable.")
            sys.exit(1)
        self.client = OpenAI(api_key=api_key)
        self.recording = False
        self.text_thread = None
        self.chat_history = []
        self.shutdown_in_progress = False
        self.screenshot_manager = ScreenshotManager()
        
        # Initialize the UI using the InterviewAssistantUI class
        self.central_widget = InterviewAssistantUI(self)
        self.setCentralWidget(self.central_widget)
        
        # Get references to UI widgets
        self.transcription_text = self.central_widget.transcription_text
        self.response_text = self.central_widget.response_text
        self.record_button = self.central_widget.record_button
        self.clear_button = self.central_widget.clear_button
        self.screenshot_button = self.central_widget.screenshot_button
        self.share_button = self.central_widget.share_button
        self.save_button = self.central_widget.save_button
        
        # Configure the main window appearance
        self.setWindowTitle("Software Engineer Interview Assistant")
        self.setGeometry(100, 100, 1200, 800)
        
        # Connect signals to slots
        self.record_button.clicked.connect(self.toggle_recording)
        self.clear_button.clicked.connect(self.clear_text)
        self.screenshot_button.clicked.connect(self.take_screenshot)
        self.share_button.clicked.connect(self.share_screenshot)
        self.save_button.clicked.connect(self.save_conversation)
        
    def toggle_recording(self):
        """Activates or deactivates the connection to the model and immediately starts recording."""
        if not self.recording:
            self.recording = True
            self.record_button.setText("End Session")
            self.record_button.setStyleSheet("background-color: #ff5555;")
            
            self.text_thread = RealtimeTextThread()
            self.text_thread.transcription_signal.connect(self.update_transcription)
            self.text_thread.response_signal.connect(self.update_response)
            self.text_thread.error_signal.connect(self.show_error)
            self.text_thread.connection_status_signal.connect(self.update_connection_status)
            self.text_thread.finished.connect(self.recording_finished)
            self.text_thread.start()
            
            # Automatic start of recording immediately after session initialization
            while not self.text_thread.connected:
                time.sleep(0.1)
            self.text_thread.start_recording()
        else:
            if self.shutdown_in_progress:
                return
                
            self.shutdown_in_progress = True
            self.record_button.setText("Termination in progress...")
            self.record_button.setEnabled(False)
            
            if hasattr(self.text_thread, 'recording') and self.text_thread.recording:
                try:
                    self.text_thread.stop_recording()
                except Exception as e:
                    logger.error("Error during stop_recording: " + str(e))
            
            try:
                if self.text_thread:
                    self.text_thread.stop()
                    self.text_thread.wait(2000)
            except Exception as e:
                logger.error("Error during session termination: " + str(e))
                self.recording_finished()
    
    def recording_finished(self):
        """Called when the thread is finished."""
        self.recording = False
        self.shutdown_in_progress = False
        self.record_button.setText("Start Session")
        self.record_button.setStyleSheet("")
        self.record_button.setEnabled(True)
        self.transcription_text.append("\n[Session ended]")
    
    def update_connection_status(self, connected):
        """Updates the interface based on the connection status."""
        if connected:
            self.record_button.setStyleSheet("background-color: #55aa55;")
        else:
            if self.recording:
                self.record_button.setStyleSheet("background-color: #ff5555;")
    
    def update_transcription(self, text):
        """Updates the transcription field."""
        if text == "Recording in progress...":
            self.transcription_text.setText(text)
            return
        
        if text.startswith('\n[Audio processed at'):
            formatted_timestamp = f"\n--- {text.strip()} ---\n"
            current_text = self.transcription_text.toPlainText()
            if current_text == "Recording in progress...":
                self.transcription_text.setText(formatted_timestamp)
            else:
                self.transcription_text.append(formatted_timestamp)
        else:
            self.transcription_text.append(text)
        
        self.transcription_text.verticalScrollBar().setValue(
            self.transcription_text.verticalScrollBar().maximum()
        )
        
        if text != "Recording in progress...":
            if not self.chat_history or self.chat_history[-1]["role"] != "user" or self.chat_history[-1]["content"] != text:
                self.chat_history.append({"role": "user", "content": text})
    
    def update_response(self, text):
        """Updates the response field with markdown formatting."""
        if not text:
            return
        current_time = datetime.now().strftime("%H:%M:%S")
        html_style = """
        <style>
            body, p, div, span, li, td, th {
                font-family: 'Arial', sans-serif !important;
                font-size: 14px !important;
                line-height: 1.6 !important;
                color: #333333 !important;
            }
            h1 { font-size: 20px !important; margin: 20px 0 10px 0 !important; font-weight: bold !important; }
            h2 { font-size: 18px !important; margin: 18px 0 9px 0 !important; font-weight: bold !important; }
            h3 { font-size: 16px !important; margin: 16px 0 8px 0 !important; font-weight: bold !important; }
            h4 { font-size: 15px !important; margin: 14px 0 7px 0 !important; font-weight: bold !important; }
            pre {
                background-color: #f5f5f5 !important;
                border: 1px solid #cccccc !important;
                border-radius: 4px !important;
                padding: 10px !important;
                margin: 10px 0 !important;
                overflow-x: auto !important;
                font-family: Consolas, 'Courier New', monospace !important;
                font-size: 14px !important;
                line-height: 1.45 !important;
                tab-size: 4 !important;
                white-space: pre !important;
            }
            code {
                font-family: Consolas, 'Courier New', monospace !important;
                font-size: 14px !important;
                background-color: #f5f5f5 !important;
                padding: 2px 4px !important;
                border-radius: 3px !important;
                border: 1px solid #cccccc !important;
                color: #333333 !important;
                white-space: pre !important;
            }
            ul, ol { margin: 10px 0 10px 20px !important; padding-left: 20px !important; }
            li { margin-bottom: 6px !important; }
            p { margin: 10px 0 !important; }
            strong { font-weight: bold !important; }
            em { font-style: italic !important; }
            table {
                border-collapse: collapse !important;
                width: 100% !important;
                margin: 15px 0 !important;
                font-size: 14px !important;
            }
            th, td {
                border: 1px solid #dddddd !important;
                padding: 8px !important;
                text-align: left !important;
            }
            th { background-color: #f2f2f2 !important; font-weight: bold !important; }
            .response-header {
                color: #666666 !important;
                font-size: 13px !important;
                margin: 15px 0 10px 0 !important;
                border-bottom: 1px solid #eeeeee !important;
                padding-bottom: 5px !important;
                font-weight: bold !important;
            }
        </style>
        """
        header = f'<div class="response-header">--- Response at {current_time} ---</div>'
        
        def process_code_blocks(text):
            import re
            def replace_code_block(match):
                language = match.group(1).strip() if match.group(1) else ""
                code = match.group(2)
                code_html = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                return f'<pre><code class="language-{language}">{code_html}</code></pre>'
            def replace_inline_code(match):
                code = match.group(1)
                code_html = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                return f'<code>{code_html}</code>'
            processed = re.sub(r'```([^\n]*)\n([\s\S]*?)\n```', replace_code_block, text)
            processed = re.sub(r'`([^`\n]+?)`', replace_inline_code, processed)
            return processed
        
        def custom_markdown(text):
            import re
            text = process_code_blocks(text)
            text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
            text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
            text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
            text = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
            text = re.sub(r'^(\s*)-\s+(.+)$', r'\1<li>\2</li>', text, flags=re.MULTILINE)
            pattern_ul = r'(<li>.*?</li>)(\n<li>.*?</li>)*'
            text = re.sub(pattern_ul, r'<ul>\g<0></ul>', text)
            text = re.sub(r'^(\s*)\d+\.\s+(.+)$', r'\1<li>\2</li>', text, flags=re.MULTILINE)
            pattern_ol = r'(<li>.*?</li>)(\n<li>.*?</li>)*'
            text = re.sub(pattern_ol, r'<ol>\g<0></ol>', text)
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
            text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
            text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
            lines = text.split('\n')
            in_html_block = False
            for i, line in enumerate(lines):
                if not line.strip() or line.strip().startswith('<'):
                    continue
                if '<pre>' in line or '<ul>' in line or '<ol>' in line or '<h' in line:
                    in_html_block = True
                elif '</pre>' in line or '</ul>' in line or '</ol>' in line or '</h' in line:
                    in_html_block = False
                    continue
                if not in_html_block:
                    lines[i] = f'<p>{line}</p>'
            text = '\n'.join(lines)
            text = re.sub(r'<p>\s*</p>', '', text)
            text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
            return text
        
        html_content = custom_markdown(text)
        formatted_html = f"{html_style}{header}{html_content}"
        self.response_text.setAcceptRichText(True)
        current_html = self.response_text.toHtml()
        if not self.response_text.toPlainText():
            self.response_text.setHtml(formatted_html)
        else:
            closing_index = current_html.rfind("</body>")
            if closing_index > 0:
                new_html = current_html[:closing_index] + f"{header}{html_content}" + current_html[closing_index:]
                self.response_text.setHtml(new_html)
            else:
                self.response_text.setHtml(current_html + formatted_html)
        self.response_text.verticalScrollBar().setValue(
            self.response_text.verticalScrollBar().maximum()
        )
        if (not self.chat_history or self.chat_history[-1]["role"] != "assistant"):
            self.chat_history.append({"role": "assistant", "content": text})
        elif self.chat_history and self.chat_history[-1]["role"] == "assistant":
            previous_content = self.chat_history[-1]["content"]
            self.chat_history[-1]["content"] = f"{previous_content}\n--- Response at {current_time} ---\n{text}"
    
    def take_screenshot(self):
        """Captures and saves a screenshot."""
        try:
            self.showMinimized()
            time.sleep(0.5)
            screenshot_path = self.screenshot_manager.take_screenshot()
            self.showNormal()
            QMessageBox.information(self, "Screenshot", 
                                      f"Screenshot saved in: {screenshot_path}")
        except Exception as e:
            error_msg = f"Error during screenshot capture: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def share_screenshot(self):
        """Captures a screenshot and offers options to share it."""
        try:
            self.showMinimized()
            time.sleep(0.5)
            screenshot_path = self.screenshot_manager.take_screenshot()
            self.showNormal()
            self.screenshot_manager.copy_to_clipboard(screenshot_path)
            QMessageBox.information(self, "Shared Screenshot", 
                                      f"Screenshot saved in: {screenshot_path}\n\nThe path has been copied to the clipboard.")
        except Exception as e:
            error_msg = f"Error during screenshot sharing: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def clear_text(self):
        """Clears the text fields."""
        self.transcription_text.clear()
        self.response_text.clear()
        self.chat_history = []
    
    def save_conversation(self):
        """Saves the conversation to a JSON file."""
        try:
            options = QFileDialog.Options()
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Conversation", "", 
                "JSON Files (*.json);;Text Files (*.txt);;All Files (*)", 
                options=options)
            
            if filename:
                if not filename.endswith('.json'):
                    filename += '.json'
                conversation_data = {
                    "timestamp": datetime.now().isoformat(),
                    "messages": self.chat_history
                }
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(conversation_data, f, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "Save Completed", 
                                          f"Conversation saved in: {filename}")
        except Exception as e:
            error_msg = f"Error during saving: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def show_error(self, message):
        """Shows an error message."""
        if "buffer too small" in message or "Conversation already has an active response" in message:
            logger.warning(f"Error ignored (only log): {message}")
        else:
            QMessageBox.critical(self, "Error", message)
    
    def closeEvent(self, event):
        """Handles application closure."""
        if self.recording and self.text_thread:
            self.transcription_text.append("\n[Closing application in progress...]")
            try:
                self.text_thread.stop()
                self.text_thread.wait(2000)
            except Exception as e:
                logger.error("Error during application closure: " + str(e))
        event.accept()
    
    def toggle_speaking(self):
        """Activates or deactivates voice recording."""
        if not self.recording or not self.text_thread or not self.text_thread.connected:
            self.show_error("Not connected. Start a session first.")
            return
        if not hasattr(self.text_thread, 'recording') or not self.text_thread.recording:
            self.text_thread.start_recording()
        else:
            self.text_thread.stop_recording()
    
    def stop_recording(self):
        """Method preserved for compatibility (recording stop handling occurs in toggle_recording)."""
        logger.info("InterviewAssistant: Stopping recording")
        pass 