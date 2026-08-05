"""
plugins/time_plugin.py
----------------------
Plugin registration for the TimeTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.builtin_tools import TimeTool


class TimePlugin(BasePlugin):
    """Plugin providing system time retrieval capabilities."""

    @property
    def name(self) -> str:
        return "time"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated TimeTool instance."""
        return [TimeTool()]
