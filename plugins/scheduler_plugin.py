"""
plugins/scheduler_plugin.py
---------------------------
Plugin registration for the SchedulerTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.scheduler import SchedulerTool


class SchedulerPlugin(BasePlugin):
    """Plugin providing background task scheduling and automation triggers."""

    @property
    def name(self) -> str:
        return "scheduler"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated SchedulerTool instance."""
        return [SchedulerTool()]
