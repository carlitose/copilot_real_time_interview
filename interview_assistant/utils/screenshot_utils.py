#!/usr/bin/env python3
import os
import time
import requests
import tempfile
from pathlib import Path
from datetime import datetime
import logging

import pyautogui
from PIL import Image
import pyperclip

logger = logging.getLogger(__name__)

class ScreenshotManager:
    """Class for managing screenshots and sharing."""
    
    def __init__(self, base_dir=None):
        """Initialize the screenshot manager.
        
        Args:
            base_dir: Base directory for saving screenshots
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path.cwd() / "screenshots"
            
        # Create directory if it doesn't exist
        self.base_dir.mkdir(exist_ok=True)
    
    def take_screenshot(self, delay=0.5):
        """Capture a screenshot of the entire screen.
        
        Args:
            delay: Delay in seconds before capturing the screenshot
        
        Returns:
            Path: Path to the saved screenshot file
        """
        try:
            # Wait for the specified delay
            time.sleep(delay)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = self.base_dir / filename
            
            # Capture and save screenshot
            screenshot = pyautogui.screenshot()
            screenshot.save(str(filepath))
            
            logger.info(f"Screenshot saved in: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error during screenshot capture: {str(e)}")
            raise
    
    def upload_to_temp_service(self, filepath):
        """Upload the image to a temporary service.
        
        Args:
            filepath: Path to the file to upload
            
        Returns:
            str: URL of the uploaded image
        """
        try:
            # For this example, we use imgbb.com
            # In a real application, an API key might be needed
            # or a different service
            
            # Open the file in binary mode
            with open(filepath, "rb") as file:
                # Prepare the data for the request
                files = {"image": (filepath.name, file, "image/png")}
                
                # Send the request to the service
                response = requests.post(
                    "https://api.imgbb.com/1/upload",
                    files=files,
                    params={"key": os.getenv("IMGBB_API_KEY", "")}
                )
                
                # Verify the response
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        url = data["data"]["url"]
                        logger.info(f"Image uploaded successfully: {url}")
                        return url
                
                logger.error(f"Error uploading image: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error during image upload: {str(e)}")
            return None
    
    def copy_to_clipboard(self, filepath):
        """Copy the image to clipboard.
        
        Args:
            filepath: Path of the file to copy to clipboard
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Open the image
            image = Image.open(filepath)
            
            # Copy to clipboard
            # Note: this works differently on different platforms
            # For macOS, we can use pyperclip to copy the file path
            
            pyperclip.copy(str(filepath))
            
            logger.info(f"Image path copied to clipboard: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error copying to clipboard: {str(e)}")
            return False 