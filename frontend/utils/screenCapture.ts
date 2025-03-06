/**
 * Utility functions for screen capture and display detection
 */

/**
 * Interface for screen information
 */
export interface ScreenInfo {
  id: string;
  label: string;
  width: number;
  height: number;
}

/**
 * Gets all available screens/displays without requesting permission immediately
 * @returns Promise with dummy screen info for initial state
 */
export async function getAvailableScreens(): Promise<ScreenInfo[]> {
  try {
    // Instead of requesting permissions immediately, return a dummy screen
    // The actual screen selection will happen when the user clicks the capture button
    const screens: ScreenInfo[] = [
      {
        id: 'screen1',
        label: 'Schermo principale',
        width: 1920,
        height: 1080
      }
    ];

    return screens;
  } catch (error) {
    console.error('Error getting available screens:', error);
    return [];
  }
}

/**
 * Captures a screenshot from the selected screen
 * @param screenId ID of the screen to capture
 * @returns Promise with the captured image as a base64 data URL
 */
export async function captureScreenshot(screenId: string): Promise<string | null> {
  try {
    // Request screen capture
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false
    });

    // Create a video element to display the stream
    const video = document.createElement('video');
    video.srcObject = stream;
    
    // Wait for the video to load metadata
    await new Promise<void>((resolve) => {
      video.onloadedmetadata = () => {
        video.play();
        resolve();
      };
    });

    // Create a canvas to capture the screenshot
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // Draw the video frame to the canvas
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Could not get canvas context');
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Stop all tracks to release the stream
    stream.getTracks().forEach(track => track.stop());
    
    // Convert the canvas to a data URL
    const dataUrl = canvas.toDataURL('image/png');
    return dataUrl;
  } catch (error) {
    console.error('Error capturing screenshot:', error);
    return null;
  }
} 