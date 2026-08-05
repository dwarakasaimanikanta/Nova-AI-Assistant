"""
plugins/calendar_plugin.py
--------------------------
Google Calendar plugin registering the CalendarTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.calendar_tool import CalendarTool


class CalendarPlugin(BasePlugin):
    """Plugin providing Google Calendar capabilities."""

    @property
    def name(self) -> str:
        return "calendar"

    def get_tools(self) -> list[BaseTool]:
        return [CalendarTool()]
