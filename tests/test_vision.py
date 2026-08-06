"""
tests/test_vision.py
--------------------
Unit tests for the Vision & Screen Understanding plugin.
Mocked to ensure headless execution without requiring active displays or local Tesseract binary engines.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from tools.vision_tool import VisionTool
from utils.vision_manager import VisionManager


@pytest.fixture
def mock_vision_manager(tmp_path):
    """Mocks VisionManager and overrides screenshots storage directory."""
    manager = VisionManager()
    manager.screenshots_dir = tmp_path
    
    # Mock active window metadata
    manager.get_active_window_info = MagicMock(return_value={
        "title": "Verifying Code Document",
        "rect": (10, 20, 800, 600),
        "pid": 5678,
        "platform": "win32"
    })
    return manager


@pytest.fixture
def dummy_image_file(tmp_path):
    """Generates a dummy local PNG file for OCR/Analysis mocks."""
    img_path = tmp_path / "test_shot.png"
    img = Image.new("RGB", (50, 50), color="blue")
    img.save(img_path)
    return img_path


def test_capture_screen(mock_vision_manager) -> None:
    """Vision: verify screenshot saves file and fetches window info."""
    # Mock ImageGrab.grab to return a tiny dummy PIL Image
    dummy_img = Image.new("RGB", (10, 10), color="red")
    
    with patch("PIL.ImageGrab.grab", return_value=dummy_img) as mock_grab:
        path, win_info = mock_vision_manager.capture_screen("test_capture.png")
        
        assert path.exists()
        assert path.name == "test_capture.png"
        assert win_info["title"] == "Verifying Code Document"
        assert win_info["pid"] == 5678
        mock_grab.assert_called_once()


def test_read_text_ocr(mock_vision_manager, dummy_image_file) -> None:
    """Vision: verify local OCR reads target file and returns extracted text."""
    with patch("utils.vision_manager.pytesseract") as mock_tess:
        mock_tess.image_to_string.return_value = "Verification OCR Data Line"
        
        text = mock_vision_manager.read_text(dummy_image_file)
        assert text == "Verification OCR Data Line"
        mock_tess.image_to_string.assert_called_once()


def test_query_multimodal_vision(mock_vision_manager, dummy_image_file) -> None:
    """Vision: verify multimodal queries build generative models and post queries."""
    # Ensure api_key check is bypassed
    import os
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_api_key"}), \
         patch("google.genai.Client") as mock_client_class:
         
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text="Multimodal Description Text")
        mock_client_class.return_value = mock_client
        
        res = mock_vision_manager.query_multimodal_vision(dummy_image_file, "Describe colors")
        
        assert "Multimodal Description Text" in res
        mock_client_class.assert_called_once_with(api_key="fake_api_key")


def test_vision_tool_execute_actions(mock_vision_manager, dummy_image_file) -> None:
    """VisionTool: verify actions capture_screen, read_text, and analyze_screen execute correctly."""
    tool = VisionTool(vision_manager=mock_vision_manager)
    dummy_img = Image.new("RGB", (10, 10), color="green")

    with patch("PIL.ImageGrab.grab", return_value=dummy_img):
        # 1. Action: capture_screen
        res = tool.execute(action="capture_screen")
        assert "Success" in res
        assert "Verifying Code Document" in res
    
        # 2. Action: read_text
        with patch("utils.vision_manager.pytesseract") as mock_tess:
            mock_tess.image_to_string.return_value = "OCR Output string content"
            res = tool.execute(action="read_text", image_path=str(dummy_image_file))
            assert "OCR Output string content" in res
    
        # 3. Action: analyze_screen
        import os
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            res = tool.execute(action="analyze_screen", query="Find buttons")
            assert "Screenshot captured" in res
            assert "Visual analysis complete" in res
