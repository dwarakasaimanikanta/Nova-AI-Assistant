"""
utils/browser_manager.py
------------------------
BrowserManager wraps Python Playwright async_api to automate Chrome/Edge browser sessions,
implementing open_url, search_google, click_element, type_text, scroll_page, capture_screenshot,
extract_text, download_file, upload_file, and close_browser operations.

Uses a dedicated background thread with its own asyncio event loop so that async Playwright
can be called safely from synchronous code even when another asyncio loop is running.
"""

import asyncio
import threading
from pathlib import Path
from typing import Any, List, Optional
from utils.logger import get_logger
from config import SCREENSHOTS_DIR

logger = get_logger(__name__)


class BrowserManager:
    """Controls Chrome/Edge browser sessions over Playwright async API with a dedicated event loop."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        # Dedicated event loop running in a daemon thread so async Playwright
        # never conflicts with any existing asyncio loop in the main thread.
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, coro) -> Any:
        """Submit a coroutine to the background event loop and block until it finishes."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=60)

    # ------------------------------------------------------------------
    # Public API (synchronous interface, unchanged signatures)
    # ------------------------------------------------------------------

    def launch_browser(self, browser_type: str = "chromium", headless: bool = True) -> str:
        """
        Launches a Playwright browser session.

        Args:
            browser_type: 'chromium', 'firefox', 'webkit', 'chrome', or 'edge'.
            headless: True to run in background.

        Returns:
            Status message indicating success.
        """
        return self._run(self._async_launch_browser(browser_type, headless))

    def open_url(self, url: str) -> str:
        """Navigates the browser page to a specific URL."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return self._run(self._async_open_url(url))

    def search_google(self, query: str) -> str:
        """Navigates to Google and submits a search query."""
        return self._run(self._async_search_google(query))

    def click_element(self, selector: str) -> str:
        """Clicks on a target element matching selector."""
        return self._run(self._async_click_element(selector))

    def type_text(self, selector: str, text: str) -> str:
        """Fills input elements with text content."""
        return self._run(self._async_type_text(selector, text))

    def scroll_page(self, direction: str = "down", amount: int = 500) -> str:
        """Scrolls viewport view direction (up/down)."""
        return self._run(self._async_scroll_page(direction, amount))

    def capture_screenshot(self, filename: Optional[str] = None) -> str:
        """Captures page viewport and saves it as image."""
        return self._run(self._async_capture_screenshot(filename))

    def extract_text(self) -> str:
        """Extracts page text string content."""
        return self._run(self._async_extract_text())

    def download_file(self, selector_or_url: str, save_path: str) -> str:
        """Downloads file target by selector click or direct goto."""
        return self._run(self._async_download_file(selector_or_url, save_path))

    def upload_file(self, selector: str, file_paths: List[str]) -> str:
        """Uploads files to inputs matching selector."""
        return self._run(self._async_upload_file(selector, file_paths))

    def press_key(self, key_name: str) -> str:
        """Simulates pressing a keyboard key."""
        return self._run(self._async_press_key(key_name))

    def wait_for_selector(self, selector: str, timeout: Optional[int] = None) -> str:
        """Waits for element matching selector to be present in page."""
        return self._run(self._async_wait_for_selector(selector, timeout))

    def click_text(self, text: str) -> str:
        """Clicks an element containing the specified text."""
        return self._run(self._async_click_text(text))

    def save_browser_session(self, session_path: str = "data/browser_session.json") -> str:
        """Saves current browser session state to a file."""
        return self._run(self._async_save_browser_session(session_path))

    def load_browser_session(self, session_path: str = "data/browser_session.json") -> str:
        """Loads browser session state from a file."""
        return self._run(self._async_load_browser_session(session_path))

    def close_browser(self) -> str:
        """Terminates context page and stops Playwright."""
        return self._run(self._async_close_browser())

    # ------------------------------------------------------------------
    # Async implementation
    # ------------------------------------------------------------------

    async def _async_launch_browser(self, browser_type: str, headless: bool) -> str:
        try:
            from playwright.async_api import async_playwright

            logger.info("Initializing Playwright async session...")
            self._playwright = await async_playwright().start()

            launch_args: dict[str, Any] = {"headless": headless}
            bt_name = browser_type.lower().strip()

            if bt_name == "chrome":
                bt = self._playwright.chromium
                launch_args["channel"] = "chrome"
            elif bt_name == "edge":
                bt = self._playwright.chromium
                launch_args["channel"] = "msedge"
            elif bt_name == "firefox":
                bt = self._playwright.firefox
            elif bt_name == "webkit":
                bt = self._playwright.webkit
            else:
                bt = self._playwright.chromium

            user_data_dir = Path("data/browser_profile")
            user_data_dir.mkdir(parents=True, exist_ok=True)

            # Auto-load default session state if it exists
            default_session = Path("data/browser_session.json")
            if default_session.exists():
                launch_args["storage_state"] = str(default_session)
                logger.info("Found default session file. Loading session state...")

            logger.info("Launching Playwright browser %s (headless=%s)...", bt_name, headless)
            try:
                # Try launching with persistent context first (for session persistence)
                self._context = await bt.launch_persistent_context(str(user_data_dir), **launch_args)
                self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
                self._browser = None
                logger.info("Playwright browser launched with persistent context successfully.")
            except (AttributeError, TypeError, Exception) as e:
                # Fallback to standard launch (backward compatible for mock testing environments)
                logger.warning("Persistent context launch not supported or failed: %s. Falling back to standard launch.", e)
                storage_state_path = launch_args.pop("storage_state", None)
                self._browser = await bt.launch(**launch_args)
                
                context_args = {}
                if storage_state_path:
                    context_args["storage_state"] = storage_state_path
                    
                self._context = await self._browser.new_context(**context_args)
                self._context.set_default_timeout(15000)
                self._page = await self._context.new_page()
                logger.info("Playwright browser standard launch completed successfully.")

            return f"Success: Launched Playwright browser '{bt_name}'."
        except Exception as e:
            cleaned_err = "".join([c if ord(c) < 128 else "?" for c in str(e)])
            logger.error("Playwright launch failed: %s", cleaned_err)
            return f"Failure: Playwright launch failed: {cleaned_err}"

    async def _async_open_url(self, url: str) -> str:
        if not self._page:
            return "Failure: Browser is not launched. Call launch_browser first."
        try:
            logger.info("Navigating to %s...", url)
            await self._page.goto(url, wait_until="load")
            return f"Success: Navigated to '{url}'."
        except Exception as e:
            logger.error("Failed to navigate to '%s': %s", url, e)
            return f"Failure: Navigation error: {e}"

    async def _async_dismiss_google_consent(self) -> None:
        """Attempt to dismiss Google's cookie consent / GDPR banner if present."""
        consent_selectors = [
            "button#L2AGLb",
            "button[id='L2AGLb']",
            "button:has-text('Accept all')",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Tout accepter')",
            "button:has-text('Aceptar todo')",
            "[aria-label='Accept all']",
            "form[action*='consent'] button",
        ]
        for selector in consent_selectors:
            try:
                btn = self._page.locator(selector).first
                if await btn.is_visible(timeout=1500):
                    await btn.click(timeout=3000)
                    logger.info("Dismissed Google consent banner via: %s", selector)
                    await self._page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    async def _async_find_search_input(self):
        """Locate Google's search input using multiple fallback selectors."""
        selectors = [
            "textarea[name='q']",
            "input[name='q']",
            "[aria-label='Search']",
            "textarea[title='Search']",
            "input[title='Search']",
        ]
        for selector in selectors:
            try:
                loc = self._page.locator(selector).first
                if await loc.is_visible(timeout=2000):
                    logger.debug("Found search input via: %s", selector)
                    return loc
            except Exception:
                continue
        return None

    async def _async_search_google(self, query: str) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        try:
            await self._async_open_url("https://www.google.com")
            await self._async_dismiss_google_consent()

            search_box = await self._async_find_search_input()
            if not search_box:
                return "Failure: Could not locate Google search input box."

            await search_box.click(timeout=5000)
            await search_box.fill(query, timeout=5000)
            await search_box.press("Enter")

            try:
                await self._page.wait_for_selector("#search, #rso, #main", timeout=10000)
            except Exception:
                await self._page.wait_for_timeout(3000)

            return f"Success: Submitted Google search query: '{query}'."
        except Exception as e:
            logger.error("Failed Google search: %s", e)
            return f"Failure: Google search error: {e}"

    async def _async_click_element(self, selector: str) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        try:
            await self._page.click(selector)
            return f"Success: Clicked element matching selector '{selector}'."
        except Exception as e:
            logger.error("Failed to click element '%s': %s", selector, e)
            return f"Failure: Click element error: {e}"

    async def _async_type_text(self, selector: str, text: str) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        try:
            await self._page.fill(selector, text)
            return f"Success: Fills input matching selector '{selector}' with text."
        except Exception as e:
            logger.error("Failed to type text in '%s': %s", selector, e)
            return f"Failure: Type text error: {e}"

    async def _async_scroll_page(self, direction: str, amount: int) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        try:
            y = amount if direction.lower() == "down" else -amount
            await self._page.evaluate(f"window.scrollBy(0, {y})")
            return f"Success: Scrolled page {direction}."
        except Exception as e:
            logger.error("Failed to scroll page: %s", e)
            return f"Failure: Scroll error: {e}"

    async def _async_capture_screenshot(self, filename: Optional[str]) -> str:
        if not filename:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"browser_shot_{timestamp}.png"

        save_path = SCREENSHOTS_DIR / filename

        if not self._page:
            return "Failure: Browser is not launched."
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await self._page.screenshot(path=str(save_path))
            return f"Success: Screenshot saved to '{save_path}'."
        except Exception as e:
            logger.error("Failed to capture screenshot: %s", e)
            return f"Failure: Screenshot error: {e}"

    async def _async_extract_text(self) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        try:
            return await self._page.inner_text("body")
        except Exception as e:
            logger.error("Failed to extract page text: %s", e)
            return f"Failure: Extract text error: {e}"

    async def _async_download_file(self, selector_or_url: str, save_path: str) -> str:
        path = Path(save_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        if not self._page:
            return "Failure: Browser is not launched."
        try:
            if not selector_or_url.startswith(("http://", "https://")):
                async with self._page.expect_download(timeout=30000) as download_info:
                    await self._page.click(selector_or_url)
                download = download_info.value
                await download.save_as(str(path))
            else:
                async with self._page.expect_download(timeout=30000) as download_info:
                    await self._page.goto(selector_or_url)
                download = download_info.value
                await download.save_as(str(path))

            return f"Success: File downloaded and saved to '{path}'."
        except Exception as e:
            logger.error("Failed download: %s", e)
            return f"Failure: Download error: {e}"

    async def _async_upload_file(self, selector: str, file_paths: List[str]) -> str:
        paths = [str(Path(p).resolve()) for p in file_paths]

        if not self._page:
            return "Failure: Browser is not launched."
        try:
            await self._page.set_input_files(selector, paths)
            return f"Success: Uploaded {len(paths)} files to input matching selector '{selector}'."
        except Exception as e:
            logger.error("Failed upload: %s", e)
            return f"Failure: Upload error: {e}"

    async def _async_press_key(self, key_name: str) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        allowed_keys = {"Enter", "Tab", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}
        if key_name not in allowed_keys:
            return f"Failure: Unsupported key '{key_name}'. Supported keys: {sorted(allowed_keys)}"
        try:
            await self._page.keyboard.press(key_name)
            return f"Success: Pressed key '{key_name}'."
        except Exception as e:
            logger.error("Failed to press key '%s': %s", key_name, e)
            return f"Failure: Press key error: {e}"

    async def _async_wait_for_selector(self, selector: str, timeout: Optional[int] = None) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        try:
            playwright_timeout = timeout if timeout is not None else 15000
            await self._page.wait_for_selector(selector, timeout=playwright_timeout)
            return f"Success: Selector '{selector}' is present."
        except Exception as e:
            logger.error("Failed to wait for selector '%s': %s", selector, e)
            return f"Failure: Wait for selector error: {e}"

    async def _async_click_text(self, text: str) -> str:
        if not self._page:
            return "Failure: Browser is not launched."
        try:
            loc = self._page.locator(f"text={text}").first
            await loc.click()
            return f"Success: Clicked element containing text '{text}'."
        except Exception as e:
            logger.error("Failed to click element with text '%s': %s", text, e)
            return f"Failure: Click text error: {e}"

    async def _async_save_browser_session(self, session_path: str) -> str:
        if not self._context:
            return "Failure: Browser is not launched."
        try:
            path = Path(session_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=str(path))
            return f"Success: Saved browser session to '{path}'."
        except Exception as e:
            logger.error("Failed to save browser session: %s", e)
            return f"Failure: Save session error: {e}"

    async def _async_load_browser_session(self, session_path: str) -> str:
        if not self._playwright:
            return "Failure: Browser is not launched."
        try:
            path = Path(session_path).resolve()
            if not path.exists():
                return f"Failure: Session file '{path}' does not exist."
            
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
                
            if self._browser:
                self._context = await self._browser.new_context(storage_state=str(path))
            else:
                bt = self._playwright.chromium
                user_data_dir = Path("data/browser_profile")
                self._context = await bt.launch_persistent_context(
                    str(user_data_dir),
                    storage_state=str(path),
                    headless=True
                )
            
            self._context.set_default_timeout(15000)
            self._page = await self._context.new_page()
            return f"Success: Loaded browser session from '{path}'."
        except Exception as e:
            logger.error("Failed to load browser session: %s", e)
            return f"Failure: Load session error: {e}"

    async def _async_close_browser(self) -> str:
        try:
            if self._context:
                try:
                    default_session = Path("data/browser_session.json")
                    default_session.parent.mkdir(parents=True, exist_ok=True)
                    await self._context.storage_state(path=str(default_session))
                    logger.info("Automatically saved browser session state.")
                except Exception as save_err:
                    logger.debug("Failed to auto-save session state on close: %s", save_err)

            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Playwright browser closed successfully.")
            return "Success: Closed Playwright browser."
        except Exception as e:
            logger.error("Failed to close Playwright browser: %s", e)
            return f"Failure: Close error: {e}"
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

    def shutdown(self) -> None:
        """Close browser resources, stop event loop and join background thread."""
        logger.info("[Watchdog] BrowserManager shutdown initiated.")
        try:
            # Run close browser synchronously inside the loop if playwright is active
            if self._playwright:
                self._run(self._async_close_browser())
        except Exception as e:
            logger.error("[Watchdog] Error closing browser: %s", e)
            
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception as e:
            logger.error("[Watchdog] Error stopping event loop: %s", e)

        if self._thread.is_alive():
            logger.info("[Watchdog] Joining BrowserManager thread...")
            self._thread.join(timeout=1.5)
            if self._thread.is_alive():
                logger.warning("[Watchdog] BrowserManager thread did not exit within timeout.")
            else:
                logger.info("[Watchdog] BrowserManager thread stopped successfully.")
