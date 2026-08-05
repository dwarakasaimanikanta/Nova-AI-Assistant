"""
utils/browser_manager.py
------------------------
BrowserManager wraps Python Playwright sync_api to automate Chrome/Edge browser sessions,
implementing open_url, search_google, click_element, type_text, scroll_page, capture_screenshot,
extract_text, download_file, upload_file, and close_browser operations.
Features a robust Mock Browser Mode fallback on headless/process failures.
"""

import os
from pathlib import Path
from typing import Any, List, Optional
from utils.logger import get_logger
from config import SCREENSHOTS_DIR

logger = get_logger(__name__)


class BrowserManager:
    """Controls Chrome/Edge browser sessions over Playwright sync API with mock fallbacks."""

    def __init__(self) -> None:
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.mock_mode = False

    def launch_browser(self, browser_type: str = "chromium", headless: bool = True) -> str:
        """
        Launches a Playwright browser session.

        Args:
            browser_type: 'chromium', 'firefox', 'webkit', 'chrome', or 'edge'.
            headless: True to run in background.

        Returns:
            Status message indicating success or fallback.
        """
        if self.mock_mode:
            return "Success: Launched mock browser."

        try:
            from playwright.sync_api import sync_playwright
            
            logger.info("Initializing Playwright sync session...")
            self.playwright = sync_playwright().start()

            launch_args = {"headless": headless}
            bt_name = browser_type.lower().strip()
            
            # Map Chrome / Edge to chromium channels
            if bt_name == "chrome":
                bt = self.playwright.chromium
                launch_args["channel"] = "chrome"
            elif bt_name == "edge":
                bt = self.playwright.chromium
                launch_args["channel"] = "msedge"
            elif bt_name == "firefox":
                bt = self.playwright.firefox
            elif bt_name == "webkit":
                bt = self.playwright.webkit
            else:
                bt = self.playwright.chromium

            logger.info("Launching Playwright browser %s (headless=%s)...", bt_name, headless)
            self.browser = bt.launch(**launch_args)
            self.context = self.browser.new_context()
            
            # Set default timeout to 15 seconds to prevent freezing
            self.context.set_default_timeout(15000)
            self.page = self.context.new_page()
            
            logger.info("Playwright browser launched successfully.")
            return f"Success: Launched Playwright browser '{bt_name}'."
        except Exception as e:
            # Clean up non-ASCII characters to prevent CP1252 encoding exceptions on Windows consoles
            cleaned_err = "".join([c if ord(c) < 128 else "?" for c in str(e)])
            logger.warning("Real Playwright launch failed: %s. Switched to Mock Browser Mode.", cleaned_err)
            self.mock_mode = True
            return f"Success: Initialized Mock Browser (Real launch failed: {cleaned_err})."

    def open_url(self, url: str) -> str:
        """Navigates the browser page to a specific URL."""
        # Sanity check URL protocol
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        if self.mock_mode:
            logger.info("[Mock Browser] Opened URL: %s", url)
            return f"Success: Navigated to '{url}' (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched. Call launch_browser first."

        try:
            logger.info("Navigating to %s...", url)
            self.page.goto(url, wait_until="load")
            return f"Success: Navigated to '{url}'."
        except Exception as e:
            logger.error("Failed to navigate to '%s': %s", url, e)
            return f"Failure: Navigation error: {e}"

    def search_google(self, query: str) -> str:
        """Navigates to Google and submits a search query."""
        if self.mock_mode:
            logger.info("[Mock Browser] Searched Google for: '%s'", query)
            return f"Success: Searched Google for '{query}' (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            self.open_url("https://www.google.com")
            # Google search input name is 'q'
            self.page.fill("input[name='q']", query)
            self.page.press("input[name='q']", "Enter")
            self.page.wait_for_timeout(2000) # Give it 2s to load results
            return f"Success: Submitted Google search query: '{query}'."
        except Exception as e:
            logger.error("Failed Google search: %s", e)
            return f"Failure: Google search error: {e}"

    def click_element(self, selector: str) -> str:
        """Clicks on a target element matching selector."""
        if self.mock_mode:
            logger.info("[Mock Browser] Clicked element selector: '%s'", selector)
            return f"Success: Clicked selector '{selector}' (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            self.page.click(selector)
            return f"Success: Clicked element matching selector '{selector}'."
        except Exception as e:
            logger.error("Failed to click element '%s': %s", selector, e)
            return f"Failure: Click element error: {e}"

    def type_text(self, selector: str, text: str) -> str:
        """Fills input elements with text content."""
        if self.mock_mode:
            logger.info("[Mock Browser] Typed '%s' in selector '%s'", text, selector)
            return f"Success: Typed text in selector '{selector}' (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            self.page.fill(selector, text)
            return f"Success: Fills input matching selector '{selector}' with text."
        except Exception as e:
            logger.error("Failed to type text in '%s': %s", selector, e)
            return f"Failure: Type text error: {e}"

    def scroll_page(self, direction: str = "down", amount: int = 500) -> str:
        """Scrolls viewport view direction (up/down)."""
        if self.mock_mode:
            logger.info("[Mock Browser] Scrolled page %s by %dpx", direction, amount)
            return f"Success: Scrolled page {direction} (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            y = amount if direction.lower() == "down" else -amount
            self.page.evaluate(f"window.scrollBy(0, {y})")
            return f"Success: Scrolled page {direction}."
        except Exception as e:
            logger.error("Failed to scroll page: %s", e)
            return f"Failure: Scroll error: {e}"

    def capture_screenshot(self, filename: Optional[str] = None) -> str:
        """Captures page viewport and saves it as image."""
        if not filename:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"browser_shot_{timestamp}.png"

        save_path = SCREENSHOTS_DIR / filename

        if self.mock_mode:
            # Create a mock image file
            from PIL import Image
            save_path.parent.mkdir(parents=True, exist_ok=True)
            img = Image.new("RGB", (100, 100), color="blue")
            img.save(save_path)
            logger.info("[Mock Browser] Captured screenshot: %s", save_path)
            return f"Success: Screenshot saved to '{save_path}' (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(save_path))
            return f"Success: Screenshot saved to '{save_path}'."
        except Exception as e:
            logger.error("Failed to capture screenshot: %s", e)
            return f"Failure: Screenshot error: {e}"

    def extract_text(self) -> str:
        """Extracts page text string content."""
        if self.mock_mode:
            return "[Mock Page Text Content]: Simulated search engine results and website header paragraphs."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            return self.page.inner_text("body")
        except Exception as e:
            logger.error("Failed to extract page text: %s", e)
            return f"Failure: Extract text error: {e}"

    def download_file(self, selector_or_url: str, save_path: str) -> str:
        """Downloads file target by selector click or direct goto."""
        path = Path(save_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        if self.mock_mode:
            # Create a mock file
            with open(path, "w", encoding="utf-8") as f:
                f.write("mock download content")
            logger.info("[Mock Browser] Downloaded file to %s", path)
            return f"Success: File downloaded to '{path}' (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            # If selector looks like selector (doesn't start with http/https)
            if not selector_or_url.startswith(("http://", "https://")):
                with self.page.expect_download(timeout=30000) as download_info:
                    self.page.click(selector_or_url)
                download = download_info.value
                download.save_as(str(path))
            else:
                # Direct navigation download
                with self.page.expect_download(timeout=30000) as download_info:
                    self.page.goto(selector_or_url)
                download = download_info.value
                download.save_as(str(path))

            return f"Success: File downloaded and saved to '{path}'."
        except Exception as e:
            logger.error("Failed download: %s", e)
            return f"Failure: Download error: {e}"

    def upload_file(self, selector: str, file_paths: List[str]) -> str:
        """Uploads files to inputs matching selector."""
        paths = [str(Path(p).resolve()) for p in file_paths]

        if self.mock_mode:
            logger.info("[Mock Browser] Uploaded files %s to selector '%s'", paths, selector)
            return f"Success: Uploaded files to selector '{selector}' (Mock Mode)."

        if not self.page:
            return "Failure: Browser is not launched."

        try:
            self.page.set_input_files(selector, paths)
            return f"Success: Uploaded {len(paths)} files to input matching selector '{selector}'."
        except Exception as e:
            logger.error("Failed upload: %s", e)
            return f"Failure: Upload error: {e}"

    def close_browser(self) -> str:
        """Terminates context page and stops Playwright."""
        if self.mock_mode:
            self.mock_mode = False
            return "Success: Closed mock browser."

        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("Playwright browser closed successfully.")
            return "Success: Closed Playwright browser."
        except Exception as e:
            logger.error("Failed to close Playwright browser: %s", e)
            return f"Failure: Close error: {e}"
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
