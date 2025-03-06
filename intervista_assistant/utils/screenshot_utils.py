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
    """Class to manage screenshots and sharing."""
    
    def __init__(self, base_dir=None):
        """Initialize the screenshot manager.
        
        Args:
            base_dir: Base directory to save screenshots
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path.cwd() / "screenshots"
            
        # Create the directory if it doesn't exist
        self.base_dir.mkdir(exist_ok=True)
        
        # Initialize mss for screenshots
        self.sct = mss.mss()
    
    def get_monitors(self):
        """Get the list of available monitors.
        
        Returns:
            list: List of available monitors with their dimensions
        """
        try:
            monitors = self.sct.monitors
            # The first element (index 0) is the union of all monitors
            # Return individual monitors starting from index 1
            return monitors[1:]
        except Exception as e:
            logger.error(f"Error retrieving monitors: {str(e)}")
            return []
    
    def take_screenshot(self, delay=0.5, monitor_index=None):
        """Capture a screenshot of the selected screen or the entire screen.
        
        Args:
            delay: Delay in seconds before capturing the screenshot
            monitor_index: Index of the monitor to capture (None = entire screen)
        
        Returns:
            Path: Path of the saved screenshot file
        """
        try:
            # Wait for the specified delay
            time.sleep(delay)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = self.base_dir / filename
            
            # Capture and save the screenshot
            if monitor_index is not None:
                # Get the list of monitors
                monitors = self.get_monitors()
                if 0 <= monitor_index < len(monitors):
                    # Capture the screenshot of the specified monitor
                    monitor = monitors[monitor_index]
                    screenshot = self.sct.grab(monitor)
                    mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))
                else:
                    logger.warning(f"Invalid monitor index: {monitor_index}, using entire screen")
                    screenshot = pyautogui.screenshot()
                    screenshot.save(str(filepath))
            else:
                # Capture the screenshot of the entire screen
                screenshot = pyautogui.screenshot()
                screenshot.save(str(filepath))
            
            logger.info(f"Screenshot saved at: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error capturing screenshot: {str(e)}")
            raise
    
    def upload_to_temp_service(self, filepath):
        """Upload the image to a temporary service.
        
        Args:
            filepath: Path of the file to upload
            
        Returns:
            str: URL of the uploaded image
        """
        try:
            # For this example, we use imgbb.com
            # In a real application, an API account or a different service might be needed
            
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
                
                # Check the response
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        url = data["data"]["url"]
                        logger.info(f"Image successfully uploaded: {url}")
                        return url
                
                logger.error(f"Error uploading image: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error during image upload: {str(e)}")
            return None
    
    def copy_to_clipboard(self, filepath):
        """Copy the image to the clipboard.
        
        Args:
            filepath: Path of the file to copy to the clipboard
            
        Returns:
            bool: True if the operation was successful, False otherwise
        """
        try:
            # Open the image
            image = Image.open(filepath)
            
            # Copy to clipboard
            # Note: this works differently on different platforms
            # It may require OS-specific implementations
            
            # On macOS, we can use pyperclip to copy the file path
            pyperclip.copy(str(filepath))
            
            logger.info(f"Image path copied to clipboard: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error copying to clipboard: {str(e)}")
            return False  