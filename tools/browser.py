"""
tools/browser.py
----------------
Consolidated browser automation tool using Python's built-in webbrowser module.
Conforms to the BaseTool interface.
"""

from typing import Any
import urllib.parse
import webbrowser

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class BrowserTool(BaseTool):
    """Consolidated browser tool handling website opens and web searches."""

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
        # Opening web pages is classified as LOW risk, running automatically
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action provided."

        try:
            if action == "open_google":
                url = "https://www.google.com"
                webbrowser.open(url)
                return "Success: Opened Google in your default web browser."

            elif action == "open_youtube":
                url = "https://www.youtube.com"
                webbrowser.open(url)
                return "Success: Opened YouTube in your default web browser."

            elif action == "open_github":
                url = "https://www.github.com"
                webbrowser.open(url)
                return "Success: Opened GitHub in your default web browser."

            elif action == "open_chatgpt":
                url = "https://chatgpt.com"
                webbrowser.open(url)
                return "Success: Opened ChatGPT in your default web browser."

            elif action == "open_url":
                url = kwargs.get("url")
                if not url:
                    return "Failure: Missing parameter 'url'."
                
                # Sanity check: Prepend https:// if protocol is missing
                parsed = urllib.parse.urlparse(url)
                if not parsed.scheme:
                    url = "https://" + url
                
                webbrowser.open(url)
                return f"Success: Opened URL '{url}' in your default web browser."

            elif action == "google_search":
                query = kwargs.get("query")
                if not query:
                    return "Failure: Missing parameter 'query'."
                
                encoded_query = urllib.parse.quote_plus(query)
                url = f"https://www.google.com/search?q={encoded_query}"
                webbrowser.open(url)
                return f"Success: Performed Google search for '{query}' in your default web browser."

            elif action == "youtube_search":
                query = kwargs.get("query")
                if not query:
                    return "Failure: Missing parameter 'query'."
                
                encoded_query = urllib.parse.quote_plus(query)
                url = f"https://www.youtube.com/results?search_query={encoded_query}"
                webbrowser.open(url)
                return f"Success: Performed YouTube search for '{query}' in your default web browser."

            else:
                return f"Failure: Unsupported action '{action}'."

        except Exception as e:
            logger.exception("Error in BrowserTool execution for action '%s': %s", action, e)
            return f"Failure executing browser action '{action}': {e}"
