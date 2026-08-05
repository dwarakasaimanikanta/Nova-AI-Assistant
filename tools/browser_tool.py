"""
tools/browser_tool.py
---------------------
Browser automation agent tool supporting launch, open_url, search_google,
click_element, type_text, scroll_page, capture_screenshot, extract_text,
download_file, upload_file, and close_browser actions.
Conforms to the BaseTool interface.
"""

from typing import Any, Optional
from tools.base_tool import BaseTool, RiskLevel
from utils.browser_manager import BrowserManager
from utils.logger import get_logger

logger = get_logger(__name__)


class BrowserTool(BaseTool):
    """Playwright-based Browser Agent tool for web automation and page testing."""

    def __init__(self, manager: Optional[BrowserManager] = None) -> None:
        self.manager = manager or BrowserManager()

    @property
    def name(self) -> str:
        return "browser_agent"

    @property
    def description(self) -> str:
        return (
            "Automates headless and graphical web browsers. "
            "Supported actions: "
            "action='launch_browser' (optional browser_type, headless), "
            "action='open_url' (requires url), "
            "action='search_google' (requires query), "
            "action='click_element' (requires selector), "
            "action='type_text' (requires selector, text), "
            "action='scroll_page' (optional direction, amount), "
            "action='capture_screenshot' (optional filename), "
            "action='extract_text', "
            "action='download_file' (requires selector_or_url, save_path), "
            "action='upload_file' (requires selector, file_paths), "
            "action='close_browser'."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "launch_browser", "open_url", "search_google", "click_element",
                        "type_text", "scroll_page", "capture_screenshot", "extract_text",
                        "download_file", "upload_file", "close_browser"
                    ],
                    "description": "The browser agent action to execute.",
                },
                "browser_type": {
                    "type": "string",
                    "enum": ["chromium", "firefox", "webkit", "chrome", "edge"],
                    "description": "Browser engine type (default: chromium).",
                    "default": "chromium",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Whether to run browser in headless background mode (default: true).",
                    "default": True,
                },
                "url": {
                    "type": "string",
                    "description": "The destination URL to open.",
                },
                "query": {
                    "type": "string",
                    "description": "The term query to search on Google.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector matching the target input or clickable element.",
                },
                "text": {
                    "type": "string",
                    "description": "Text content to type into input fields.",
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll direction (default: down).",
                    "default": "down",
                },
                "amount": {
                    "type": "integer",
                    "description": "Number of pixels to scroll (default: 500).",
                    "default": 500,
                },
                "filename": {
                    "type": "string",
                    "description": "File name for the saved screenshot (optional).",
                },
                "selector_or_url": {
                    "type": "string",
                    "description": "Target CSS click selector or direct URL for file download.",
                },
                "save_path": {
                    "type": "string",
                    "description": "Target filepath location to save the downloaded file.",
                },
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Local file paths to upload.",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Base risk level is HIGH since this tool has the ability to click, type, download and interact.
        # PermissionGate evaluates the specific action dynamically to distinguish between LOW and HIGH.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: Missing parameter 'action'."

        try:
            if action == "launch_browser":
                browser_type = kwargs.get("browser_type", "chromium")
                headless = kwargs.get("headless", True)
                return self.manager.launch_browser(browser_type, headless)

            elif action == "open_url":
                url = kwargs.get("url")
                if not url:
                    return "Failure: Parameter 'url' is required for open_url."
                return self.manager.open_url(url)

            elif action == "search_google":
                query = kwargs.get("query")
                if not query:
                    return "Failure: Parameter 'query' is required for search_google."
                return self.manager.search_google(query)

            elif action == "click_element":
                selector = kwargs.get("selector")
                if not selector:
                    return "Failure: Parameter 'selector' is required for click_element."
                return self.manager.click_element(selector)

            elif action == "type_text":
                selector = kwargs.get("selector")
                text = kwargs.get("text")
                if not selector or text is None:
                    return "Failure: Both 'selector' and 'text' are required for type_text."
                return self.manager.type_text(selector, text)

            elif action == "scroll_page":
                direction = kwargs.get("direction", "down")
                amount = kwargs.get("amount", 500)
                return self.manager.scroll_page(direction, amount)

            elif action == "capture_screenshot":
                filename = kwargs.get("filename")
                return self.manager.capture_screenshot(filename)

            elif action == "extract_text":
                return self.manager.extract_text()

            elif action == "download_file":
                selector_or_url = kwargs.get("selector_or_url")
                save_path = kwargs.get("save_path")
                if not selector_or_url or not save_path:
                    return "Failure: Both 'selector_or_url' and 'save_path' are required for download_file."
                return self.manager.download_file(selector_or_url, save_path)

            elif action == "upload_file":
                selector = kwargs.get("selector")
                file_paths = kwargs.get("file_paths")
                if not selector or not file_paths:
                    return "Failure: Both 'selector' and 'file_paths' list are required for upload_file."
                return self.manager.upload_file(selector, file_paths)

            elif action == "close_browser":
                return self.manager.close_browser()

            else:
                return f"Failure: Unsupported browser_agent action '{action}'."

        except Exception as e:
            logger.error("BrowserTool execute error: %s", e)
            return f"Failure: Browser agent execution error: {e}"
