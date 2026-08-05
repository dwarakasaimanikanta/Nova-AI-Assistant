"""
plugins/file_manager_plugin.py
------------------------------
FileManager plugin registering the FileManagerTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.file_manager import FileManagerTool


class FileManagerPlugin(BasePlugin):
    """Plugin providing local file system management capabilities."""

    @property
    def name(self) -> str:
        return "file_manager"

    def get_tools(self) -> list[BaseTool]:
        """Expose the unified FileManagerTool instance."""
        return [FileManagerTool()]
