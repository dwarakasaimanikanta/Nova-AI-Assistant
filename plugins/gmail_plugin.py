"""
plugins/gmail_plugin.py
-----------------------
Gmail plugin registering the GmailTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.gmail_tool import GmailTool


class GmailPlugin(BasePlugin):
    """Plugin providing Gmail email capabilities."""

    @property
    def name(self) -> str:
        return "gmail"

    def get_tools(self) -> list[BaseTool]:
        return [GmailTool()]
