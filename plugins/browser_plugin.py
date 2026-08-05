"""
plugins/browser_plugin.py
-------------------------
Browser automation plugin registering the BrowserTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.browser import BrowserTool


class BrowserPlugin(BasePlugin):
    """Plugin providing web browsing and search redirection capabilities."""

    @property
    def name(self) -> str:
        return "browser"

    def get_tools(self) -> list[BaseTool]:
        """Expose the unified BrowserTool instance."""
        return [BrowserTool()]
