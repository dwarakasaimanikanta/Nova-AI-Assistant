"""
plugins/drive_plugin.py
-----------------------
Google Drive plugin registering the DriveTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.drive_tool import DriveTool


class DrivePlugin(BasePlugin):
    """Plugin providing Google Drive search capabilities."""

    @property
    def name(self) -> str:
        return "drive"

    def get_tools(self) -> list[BaseTool]:
        return [DriveTool()]
