"""
utils/vision_manager.py
-----------------------
VisionManager handles screenshot captures, active window metadata extraction on Windows,
local OCR text extraction via pytesseract, and multimodal visual analysis using Google Gemini.
"""

import os
import sys
import datetime
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
from PIL import Image, ImageGrab
from utils.logger import get_logger
from config import SCREENSHOTS_DIR

logger = get_logger(__name__)

try:
    import pytesseract
except ImportError:
    pytesseract = None


class VisionManager:
    """Manages system screen captures, window metadata, OCR, and vision LLM queries."""

    def __init__(self) -> None:
        self.screenshots_dir = SCREENSHOTS_DIR
        self.screenshots_dir.mkdir(exist_ok=True)

    def get_active_window_info(self) -> Dict[str, Any]:
        """
        Retrieves metadata about the currently active foreground window on Windows systems.

        Returns:
            A dictionary containing window title, coordinates, and process ID.
        """
        info = {
            "title": "Unknown Window",
            "rect": (0, 0, 1920, 1080),
            "pid": 0,
            "platform": sys.platform
        }

        if sys.platform != "win32":
            return info

        try:
            import win32gui
            import win32process
            
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd)
                rect = win32gui.GetWindowRect(hwnd) # (left, top, right, bottom)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                
                info.update({
                    "title": title or "(Untitled Window)",
                    "rect": rect,
                    "pid": pid
                })
        except Exception as e:
            logger.warning("Failed to retrieve win32 foreground window metadata: %s", e)

        return info

    def capture_screen(self, filename: Optional[str] = None) -> Tuple[Path, Dict[str, Any]]:
        """
        Captures a screenshot of the main screen and saves it.

        Args:
            filename: Target file name (e.g. 'shot.png'). If omitted, defaults to timestamp naming.

        Returns:
            A tuple of (saved_file_path, active_window_metadata).
        """
        if not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"

        save_path = self.screenshots_dir / filename
        
        # Verify supported extensions
        suffix = save_path.suffix.lower()
        if suffix not in [".png", ".jpg", ".jpeg", ".bmp"]:
            logger.warning("Unsupported image extension '%s'. Defaulting to PNG.", suffix)
            save_path = save_path.with_suffix(".png")

        try:
            # Grabs full screen
            screenshot = ImageGrab.grab()
            screenshot.save(save_path)
            logger.info("Captured and saved screenshot to %s", save_path)
        except Exception as e:
            logger.exception("Failed to capture screenshot using ImageGrab: %s", e)
            raise RuntimeError(f"Failed to capture screen: {e}")

        # Fetch active window metadata
        window_info = self.get_active_window_info()
        return save_path, window_info

    def read_text(self, image_path: Path) -> str:
        """
        Performs local OCR on a targeted image path using pytesseract.

        Args:
            image_path: Path to the image file.

        Returns:
            The extracted text string.
        """
        if not image_path.exists():
            return f"Failure: Image file '{image_path}' does not exist."

        if not pytesseract:
            return "Failure: pytesseract package is not installed. Please install pytesseract."

        # Bind config command if specified
        from config import TESSERACT_CMD
        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        try:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            return text.strip()
        except Exception as e:
            logger.error("OCR extraction failed on %s: %s", image_path, e)
            return f"Failure: Local OCR extraction failed: {e}. Ensure Tesseract is installed."

    def query_multimodal_vision(self, image_path: Path, query: str) -> str:
        """
        Submits a query alongside an image to Google Gemini Vision APIs.

        Args:
            image_path: Path to the image file.
            query: Vision instruction (e.g. 'Describe this image').

        Returns:
            The model's visual analysis response text.
        """
        if not image_path.exists():
            return f"Failure: Image file '{image_path}' does not exist."

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or os.getenv("ENVIRONMENT") == "test":
            logger.warning("Running vision query in offline mock mode (no GEMINI_API_KEY found or in test).")
            return f"[Mock Vision Response for {image_path.name}]: Visual analysis complete for query '{query}'."

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key, transport="rest")
            
            # Load image
            img = Image.open(image_path)
            
            # Use gemini-2.5-flash or gemini-3.5-flash-lite as the multimodal model
            model = genai.GenerativeModel("gemini-3.5-flash-lite")
            logger.info("Sending multimodal generation request to Gemini model.")
            response = model.generate_content([query, img])
            return response.text
        except Exception as e:
            logger.error("Multimodal vision query failed: %s", e)
            return f"Failure: Multimodal analysis failed: {e}"
