"""
plugins/web_search_plugin.py
----------------------------
Web search plugin registering the WebSearchTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.web_search import WebSearchTool


class WebSearchPlugin(BasePlugin):
    """Plugin providing search capabilities on the web."""

    @property
    def name(self) -> str:
        return "web_search"

    def get_tools(self) -> list[BaseTool]:
        """Expose the unified WebSearchTool instance."""
        return [WebSearchTool()]
