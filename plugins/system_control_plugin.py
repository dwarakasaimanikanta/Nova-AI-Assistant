"""
plugins/system_control_plugin.py
--------------------------------
Plugin registration for the SystemControlTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.system_control import SystemControlTool


class SystemControlPlugin(BasePlugin):
    """Plugin providing local system control automation capabilities."""

    @property
    def name(self) -> str:
        return "system_control"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated SystemControlTool instance."""
        return [SystemControlTool()]
