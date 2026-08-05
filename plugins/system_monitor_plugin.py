"""
plugins/system_monitor_plugin.py
--------------------------------
Plugin registration for the SystemMonitorTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.system_monitor import SystemMonitorTool


class SystemMonitorPlugin(BasePlugin):
    """Plugin providing live system statistics and resource monitoring."""

    @property
    def name(self) -> str:
        return "system_monitor"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated SystemMonitorTool instance."""
        return [SystemMonitorTool()]
