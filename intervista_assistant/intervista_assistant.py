#!/usr/bin/env python3
import sys
import os
import time
import json
import logging
import asyncio
from datetime import datetime
import base64

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from openai import OpenAI
from dotenv import load_dotenv

from .realtime_text_thread import RealtimeTextThread
from .utils import ScreenshotManager, ScreenSelectorDialog
from .ui import IntervistaAssistantUI

# Logging configuration
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='app.log')
logger = logging.getLogger(__name__)

class IntervistaAssistant(QMainWindow):
    """Main application for the interview assistant."""
    
    def __init__(self):
        super().__init__()
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            QMessageBox.critical(self, "API Key Error", 
                                 "OpenAI API Key not found. Set the environment variable OPENAI_API_KEY.")
            sys.exit(1)
        self.client = OpenAI(api_key=api_key)
        self.recording = False
        self.text_thread = None
        self.chat_history = []
        self.shutdown_in_progress = False
        self.screenshot_manager = ScreenshotManager()
        
        # Initialize the UI using the IntervistaAssistantUI class
        self.central_widget = IntervistaAssistantUI(self)
        self.setCentralWidget(self.central_widget)
        
        # Get references to the UI widgets
        self.transcription_text = self.central_widget.transcription_text
        self.response_text = self.central_widget.response_text
        self.record_button = self.central_widget.record_button
        self.clear_button = self.central_widget.clear_button
        self.analyze_screenshot_button = self.central_widget.analyze_screenshot_button
        self.save_button = self.central_widget.save_button
        self.screen_selector_combo = self.central_widget.screen_selector_combo
        
        # Popola il menu a tendina con i monitor disponibili
        self._populate_screen_selector()
        
        # Configure the main window appearance
        self.setWindowTitle("Intervista Assistant")
        self.resize(1000, 800)
        
        # Connect signals to slots
        self.record_button.clicked.connect(self.toggle_recording)
        self.clear_button.clicked.connect(self.clear_text)
        self.analyze_screenshot_button.clicked.connect(self.take_and_send_screenshot)
        self.save_button.clicked.connect(self.save_conversation)
        
    def _populate_screen_selector(self):
        """Popola il menu a tendina con i monitor disponibili."""
        try:
            # Aggiungi opzione per schermo intero
            self.screen_selector_combo.addItem("Schermo Intero", None)
            
            # Ottieni i monitor disponibili
            monitors = self.screenshot_manager.get_monitors()
            
            # Aggiungi le opzioni per ogni monitor
            for i, monitor in enumerate(monitors):
                display_text = f"Monitor {i+1}: {monitor['width']}x{monitor['height']}"
                self.screen_selector_combo.addItem(display_text, i)
                
            logger.info(f"Menu a tendina popolato con {len(monitors)} monitor")
        except Exception as e:
            logger.error(f"Errore durante il popolamento del menu a tendina: {str(e)}")
        
    def toggle_recording(self):
        """Toggle the connection to the model and immediately start recording."""
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
            
            # Automatically start recording immediately after session initialization
            while not self.text_thread.connected:
                time.sleep(0.1)
            self.text_thread.start_recording()
        else:
            if self.shutdown_in_progress:
                return
                
            self.shutdown_in_progress = True
            self.record_button.setText("Terminating...")
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
        """Called when the thread has finished."""
        self.recording = False
        self.shutdown_in_progress = False
        self.record_button.setText("Start Session")
        self.record_button.setStyleSheet("")
        self.record_button.setEnabled(True)
        self.transcription_text.append("\n[Session ended]")
    
    def update_connection_status(self, connected):
        """Update the interface based on the connection status."""
        if connected:
            self.record_button.setStyleSheet("background-color: #55aa55;")
        else:
            if self.recording:
                self.record_button.setStyleSheet("background-color: #ff5555;")
    
    def update_transcription(self, text):
        """Update the transcription field."""
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
        """Update the response field with markdown formatting."""
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
    
    def take_and_send_screenshot(self):
        """Capture screenshot and send it to the OpenAI model.
        
        Uses gpt-4o to analyze the image and then forwards the response to the realtime thread.
        This creates a seamless conversation flow even though realtime API doesn't support images.
        """
        try:
            # Check if realtime thread is active
            if not self.recording or not self.text_thread or not self.text_thread.connected:
                QMessageBox.warning(self, "Not Connected", 
                                    "You need to start a session first before analyzing images.")
                return
            
            # Ottieni l'indice del monitor selezionato dal menu a tendina
            selected_monitor = self.screen_selector_combo.currentData()
            logger.info(f"Cattura screenshot del monitor: {selected_monitor}")
                
            self.showMinimized()
            time.sleep(0.5)
            screenshot_path = self.screenshot_manager.take_screenshot(monitor_index=selected_monitor)
            self.showNormal()
            
            # Convert the image to base64
            with open(screenshot_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Update UI to show we're sending the image
            self.transcription_text.append("\n[Screenshot sent for analysis]\n")
            self.response_text.append("<p><i>Image analysis in progress...</i></p>")
            QApplication.processEvents()  # Update UI
            
            # Prepare messages for gpt-4o including chat history
            messages = self._prepare_messages_with_history(base64_image)
            
            try:
                # Call gpt-4o to analyze the image with the chat history for context
                logger.info("Sending image to gpt-4o for analysis")
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    max_tokens=1000
                )
                
                # Get the assistant's response
                assistant_response = response.choices[0].message.content
                logger.info(f"Received response from gpt-4o: {assistant_response[:100]}...")
                
                # Add the response to UI and chat history
                self.update_response(assistant_response)
                
                # Now send the analysis as text to the realtime thread to maintain conversation flow
                if self.text_thread and self.text_thread.connected:
                    # Send a shortened version of the response to the realtime thread
                    # This helps the model know what was in the image without having to see it
                    context_msg = f"[I've analyzed the screenshot of a coding exercise/technical interview question. Here's what I found: {assistant_response[:500]}... Let me know if you need more specific details or have questions about how to approach this problem.]"
                    success = self.text_thread.send_text(context_msg)
                    if success:
                        logger.info("Image analysis context sent to realtime thread")
                    else:
                        logger.error("Failed to send image analysis context to realtime thread")
                
                logger.info(f"Screenshot analyzed: {screenshot_path}")
                
            except Exception as e:
                error_msg = f"Error during image analysis: {str(e)}"
                self.show_error(error_msg)
                logger.error(error_msg)
            
        except Exception as e:
            error_msg = f"Error during screenshot capture and analysis: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def _prepare_messages_with_history(self, base64_image):
        """Prepare messages array for gpt-4o including chat history and image."""
        messages = []
        
        # Add system message
        messages.append({
            "role": "system", 
            "content": "You are a specialized assistant for technical interviews, analyzing screenshots of coding exercises and technical problems. Help the user understand the content of these screenshots in detail. Your analysis should be particularly useful for a candidate during a technical interview or coding assessment."
        })
        
        # Add previous conversation history (excluding the last few entries which might be UI updates)
        history_to_include = self.chat_history[:-2] if len(self.chat_history) > 2 else []
        messages.extend(history_to_include)
        
        # Add the image message
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Please analyze this screenshot of a potential technical interview question or coding exercise. Describe what you see in detail, extract any visible code or problem statement, explain the problem if possible, and suggest approaches or ideas to solve it."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })
        
        return messages
    
    def clear_text(self):
        """Clear the text fields."""
        self.transcription_text.clear()
        self.response_text.clear()
        self.chat_history = []
    
    def save_conversation(self):
        """Save the conversation to a JSON file."""
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
            error_msg = f"Error during save: {str(e)}"
            self.show_error(error_msg)
            logger.error(error_msg)
    
    def show_error(self, message):
        """Show an error message."""
        if "buffer too small" in message or "Conversation already has an active response" in message:
            logger.warning(f"Ignored error (log only): {message}")
        else:
            QMessageBox.critical(self, "Error", message)
    
    def closeEvent(self, event):
        """Handle application closure."""
        if self.recording and self.text_thread:
            self.transcription_text.append("\n[Application closing...]")
            try:
                self.text_thread.stop()
                self.text_thread.wait(2000)
            except Exception as e:
                logger.error("Error during application closure: " + str(e))
        event.accept()
    
    def toggle_speaking(self):
        """Toggle voice recording."""
        if not self.recording or not self.text_thread or not self.text_thread.connected:
            self.show_error("You are not connected. Start a session first.")
            return
        if not hasattr(self.text_thread, 'recording') or not self.text_thread.recording:
            self.text_thread.start_recording()
        else:
            self.text_thread.stop_recording()
    
    def stop_recording(self):
        """Method preserved for compatibility (stop handling is done in toggle_recording)."""
        logger.info("IntervistaAssistant: Stopping recording")
        pass 