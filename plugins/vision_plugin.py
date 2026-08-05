"""
plugins/vision_plugin.py
------------------------
Vision plugin registering the VisionTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.vision_tool import VisionTool


class VisionPlugin(BasePlugin):
    """Plugin providing system screenshot capturing, OCR, and multimodal visual analysis."""

    @property
    def name(self) -> str:
        return "vision"

    def get_tools(self) -> list[BaseTool]:
        return [VisionTool()]
