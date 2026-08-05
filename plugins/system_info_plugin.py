"""
plugins/system_info_plugin.py
-----------------------------
Plugin registration for the SystemInfoTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.builtin_tools import SystemInfoTool


class SystemInfoPlugin(BasePlugin):
    """Plugin providing system info retrieval capabilities."""

    @property
    def name(self) -> str:
        return "system_info"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated SystemInfoTool instance."""
        return [SystemInfoTool()]
