from plugins.base import BasePlugin
from tools.base_tool import BaseTool


class BrowserPlugin(BasePlugin):
    """Plugin providing web browsing and search redirection capabilities."""

    @property
    def name(self) -> str:
        return "browser"

    def get_tools(self) -> list[BaseTool]:
        """Expose the unified BrowserTool instances."""
        from tools.browser import BrowserTool as LegacyBrowserTool
        from tools.browser_tool import BrowserTool as PlaywrightBrowserTool
        return [LegacyBrowserTool(), PlaywrightBrowserTool()]
