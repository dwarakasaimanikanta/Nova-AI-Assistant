"""
tools/vision_tool.py
--------------------
Vision tool supporting screenshot capture, active window discovery,
local OCR text reading, and Gemini multimodal image descriptions.
Conforms to the BaseTool interface.
"""

from pathlib import Path
from typing import Any, Optional
from tools.base_tool import BaseTool, RiskLevel
from utils.vision_manager import VisionManager
from utils.logger import get_logger

logger = get_logger(__name__)


class VisionTool(BaseTool):
    """Google Gemini & Pytesseract powered Vision tool for system screenshot analysis."""

    def __init__(self, vision_manager: Optional[VisionManager] = None) -> None:
        self.manager = vision_manager or VisionManager()

    @property
    def name(self) -> str:
        return "vision"

    @property
    def description(self) -> str:
        return (
            "Captures and analyzes screen images. "
            "Supports action='capture_screen' (saves screen and returns path & active window title), "
            "action='analyze_screen' (captures screenshot and describes it with a query), "
            "action='read_text' (runs local OCR on image_path or last screenshot), "
            "action='detect_ui_elements' (locates buttons/text fields on image_path or last screenshot), "
            "and action='describe_image' (describes image_path using a custom query)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["capture_screen", "analyze_screen", "read_text", "detect_ui_elements", "describe_image"],
                    "description": "The vision operation to perform.",
                },
                "image_path": {
                    "type": "string",
                    "description": "Path to a local image file. If omitted for analysis, captures a new screenshot to analyze.",
                },
                "query": {
                    "type": "string",
                    "description": "Specific query or instruction for visual description (required for describe_image/analyze_screen).",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Screen capturing and window scanning are LOW-risk read-only actions.
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: Missing parameter 'action'."

        try:
            if action == "capture_screen":
                path, win_info = self.manager.capture_screen()
                return (
                    f"Success: Screenshot captured and saved to '{path}'.\n"
                    f"Active Window Title: '{win_info.get('title')}'\n"
                    f"Window Coordinates: {win_info.get('rect')}\n"
                    f"Process ID: {win_info.get('pid')}"
                )

            elif action == "analyze_screen":
                query = kwargs.get("query")
                if not query:
                    query = "Describe what is currently visible on the screen."

                # Capture screen first
                path, win_info = self.manager.capture_screen()
                analysis = self.manager.query_multimodal_vision(path, query)
                return (
                    f"Screenshot captured at '{path}' (Active Window: '{win_info.get('title')}').\n"
                    f"Analysis Output:\n{analysis}"
                )

            elif action == "read_text":
                image_path_str = kwargs.get("image_path")
                if image_path_str:
                    path = Path(image_path_str)
                else:
                    # Capture current screen as default target
                    path, _ = self.manager.capture_screen()

                text = self.manager.read_text(path)
                return f"OCR Text Extracted from '{path}':\n\n{text}"

            elif action == "detect_ui_elements":
                image_path_str = kwargs.get("image_path")
                if image_path_str:
                    path = Path(image_path_str)
                else:
                    path, _ = self.manager.capture_screen()

                query = "Identify and list all interactive user interface elements, input boxes, and buttons, noting their approximate screen positions."
                analysis = self.manager.query_multimodal_vision(path, query)
                return f"UI Elements Detection for '{path}':\n\n{analysis}"

            elif action == "describe_image":
                image_path_str = kwargs.get("image_path")
                query = kwargs.get("query")
                if not image_path_str or not query:
                    return "Failure: Both 'image_path' and 'query' parameters are required for describe_image."

                path = Path(image_path_str)
                analysis = self.manager.query_multimodal_vision(path, query)
                return f"Visual Analysis for '{path}':\n\n{analysis}"

            else:
                return f"Failure: Unsupported Vision action '{action}'."

        except Exception as e:
            logger.error("VisionTool execution failure: %s", e)
            return f"Failure: Vision tool error: {e}"
