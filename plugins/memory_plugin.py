"""
plugins/memory_plugin.py
------------------------
Long-term memory plugin registering the MemoryTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.memory_tool import MemoryTool


class MemoryPlugin(BasePlugin):
    """Plugin providing persistent long-term memory for user facts."""

    @property
    def name(self) -> str:
        return "memory"

    def get_tools(self) -> list[BaseTool]:
        """Expose the unified MemoryTool instance."""
        return [MemoryTool()]
