from plugins.base import BasePlugin
from tools.base_tool import BaseTool


class BrowserPlugin(BasePlugin):
    """Plugin providing web browsing and search redirection capabilities."""

    def __init__(self) -> None:
        self._tools = None

    @property
    def name(self) -> str:
        return "browser"

    def get_tools(self) -> list[BaseTool]:
        """Expose the unified BrowserTool instances."""
        if self._tools is None:
            from tools.browser import BrowserTool as LegacyBrowserTool
            from tools.browser_tool import BrowserTool as PlaywrightBrowserTool
            self._tools = [LegacyBrowserTool(), PlaywrightBrowserTool()]
        return self._tools

    def shutdown(self) -> None:
        """Shut down browser tools and manager event loops/threads."""
        if self._tools:
            for tool in self._tools:
                if hasattr(tool, "shutdown"):
                    try:
                        tool.shutdown()
                    except Exception as e:
                        pass
