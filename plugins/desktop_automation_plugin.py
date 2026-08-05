"""
plugins/desktop_automation_plugin.py
------------------------------------
Desktop automation plugin registering the DesktopAutomationTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.desktop_automation_tool import DesktopAutomationTool


class DesktopAutomationPlugin(BasePlugin):
    """Plugin providing OS-level automation controls (mouse, keyboard, clipboard, processes, filesystem)."""

    @property
    def name(self) -> str:
        return "desktop_automation"

    def get_tools(self) -> list[BaseTool]:
        return [DesktopAutomationTool()]
