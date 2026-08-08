from typing import Any, Optional
import urllib.parse

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger
from utils.browser_manager import BrowserManager

logger = get_logger(__name__)


class BrowserTool(BaseTool):
    """Consolidated browser tool handling website opens and web searches using Playwright."""

    def __init__(self, manager: Optional[BrowserManager] = None) -> None:
        # Share or instantiate the Playwright BrowserManager
        self.manager = manager or BrowserManager()

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Provides web browser automation capabilities to open URLs "
            "and perform web searches (Google, YouTube, GitHub, ChatGPT)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "open_google",
                        "open_youtube",
                        "open_github",
                        "open_chatgpt",
                        "open_url",
                        "google_search",
                        "youtube_search",
                    ],
                    "description": "The web browser action to execute.",
                },
                "url": {
                    "type": "string",
                    "description": "The destination URL to open (required for open_url action).",
                },
                "query": {
                    "type": "string",
                    "description": "The search query query term (required for google_search and youtube_search actions).",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action provided."

        logger.info("[BROWSER] Routing browser tool action: '%s'", action)

        try:
            if action == "open_google":
                res = self.manager.open_url("https://www.google.com")
                return f"Success: Opened Google. {res}"

            elif action == "open_youtube":
                res = self.manager.open_url("https://www.youtube.com")
                return f"Success: Opened YouTube. {res}"

            elif action == "open_github":
                res = self.manager.open_url("https://github.com")
                return f"Success: Opened GitHub. {res}"

            elif action == "open_chatgpt":
                res = self.manager.open_url("https://chatgpt.com")
                return f"Success: Opened ChatGPT. {res}"

            elif action == "open_url":
                url = kwargs.get("url")
                if not url:
                    return "Failure: Missing parameter 'url'."
                
                parsed = urllib.parse.urlparse(url)
                if not parsed.scheme:
                    url = "https://" + url
                
                res = self.manager.open_url(url)
                return f"Success: Opened URL '{url}'. {res}"

            elif action == "google_search":
                query = kwargs.get("query")
                if not query:
                    return "Failure: Missing parameter 'query'."
                
                res = self.manager.search_google(query)
                return f"Success: Performed Google search for '{query}'. {res}"

            elif action == "youtube_search":
                query = kwargs.get("query")
                if not query:
                    return "Failure: Missing parameter 'query'."
                
                encoded_query = urllib.parse.quote_plus(query)
                url = f"https://www.youtube.com/results?search_query={encoded_query}"
                res = self.manager.open_url(url)
                return f"Success: Performed YouTube search for '{query}'. {res}"

            else:
                return f"Failure: Unsupported action '{action}'."

        except Exception as e:
            logger.exception("Error in BrowserTool execution for action '%s': %s", action, e)
            return f"Failure executing browser action '{action}': {e}"

    def shutdown(self) -> None:
        """Close browser resources on shutdown."""
        try:
            self.manager.close_browser()
        except Exception:
            pass
