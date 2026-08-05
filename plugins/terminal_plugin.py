"""
plugins/terminal_plugin.py
--------------------------
Terminal execution plugin registering the TerminalTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.terminal import TerminalTool


class TerminalPlugin(BasePlugin):
    """Plugin providing shell command execution capabilities."""

    @property
    def name(self) -> str:
        return "terminal"

    def get_tools(self) -> list[BaseTool]:
        """Expose the unified TerminalTool instance."""
        return [TerminalTool()]
