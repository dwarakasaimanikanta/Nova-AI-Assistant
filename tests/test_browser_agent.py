"""
tests/test_browser_agent.py
---------------------------
Unit tests for BrowserManager, BrowserTool, and browser PermissionGate checks.
Fully mocked to ensure headless execution without requiring actual Playwright browser binaries.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tools.browser_tool import BrowserTool
from utils.browser_manager import BrowserManager
from tools.permission_gate import PermissionGate
from tools.base_tool import RiskLevel


@pytest.fixture
def mock_async_playwright():
    """Generates complete mock structure of async Playwright page, contexts, and browsers."""
    with patch("playwright.async_api.async_playwright") as mock_async:
        mock_p = MagicMock()
        mock_p.stop = AsyncMock()  # stop() is awaited in close_browser
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        # async_playwright() returns an async context; .start() is awaited
        mock_cm = AsyncMock()
        mock_cm.start = AsyncMock(return_value=mock_p)
        mock_async.return_value = mock_cm

        # Link context tree (all return values must be awaitable)
        mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.set_default_timeout = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        # Mock locator chain for search_google
        mock_locator = MagicMock()
        mock_locator.first = MagicMock()
        mock_locator.first.is_visible = AsyncMock(return_value=True)
        mock_locator.first.click = AsyncMock()
        mock_locator.first.fill = AsyncMock()
        mock_locator.first.press = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_page.wait_for_selector = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        yield mock_p, mock_browser, mock_context, mock_page


def test_browser_manager_actions(mock_async_playwright) -> None:
    """BrowserManager: verify navigations, searches, clicks, typing, and closes call Playwright."""
    _, _, _, mock_page = mock_async_playwright

    manager = BrowserManager()
    res_launch = manager.launch_browser("chromium", headless=True)
    assert "Success" in res_launch

    # 1. Open URL
    manager.open_url("http://test.com")
    mock_page.goto.assert_awaited_with("http://test.com", wait_until="load")

    # 2. Search Google (uses page.locator() -> .fill() / .press() internally)
    manager.search_google("RAG agent")
    # Verify Google was navigated to
    mock_page.goto.assert_any_await("https://www.google.com", wait_until="load")
    # Verify locator was used to find the search input
    mock_page.locator.assert_called()

    # 3. Click Element
    manager.click_element("button#submit")
    mock_page.click.assert_awaited_with("button#submit")

    # 4. Type Text
    manager.type_text("input#name", "Nova Assistant")
    mock_page.fill.assert_awaited_with("input#name", "Nova Assistant")

    # 5. Extract Text
    mock_page.inner_text = AsyncMock(return_value="Page body text content")
    txt = manager.extract_text()
    assert txt == "Page body text content"
    mock_page.inner_text.assert_awaited_with("body")

    # 6. Close Browser
    res_close = manager.close_browser()
    assert "Success" in res_close
    mock_page.close.assert_awaited_once()


def test_browser_manager_resiliency_fallback() -> None:
    """BrowserManager: verify launch failures return Failure message gracefully."""
    with patch("playwright.async_api.async_playwright", side_effect=ImportError("No driver found")):
        manager = BrowserManager()
        res = manager.launch_browser()

        assert "Failure" in res

        # Subsequent operations return informative failure since browser is not launched
        res_open = manager.open_url("http://verify.org")
        assert "Failure" in res_open

        res_search = manager.search_google("testing")
        assert "Failure" in res_search


def test_browser_tool_routing() -> None:
    """BrowserTool: verify action arguments map to manager methods correctly."""
    mock_mgr = MagicMock(spec=BrowserManager)
    tool = BrowserTool(manager=mock_mgr)

    # 1. Type text route
    tool.execute(action="type_text", selector="input#search", text="test query")
    mock_mgr.type_text.assert_called_with("input#search", "test query")

    # 2. Scroll page route
    tool.execute(action="scroll_page", direction="up", amount=200)
    mock_mgr.scroll_page.assert_called_with("up", 200)


def test_browser_permission_gate() -> None:
    """Security: verify gate permits browsing/reads and prompts for clicks, typing, downloads, and closes."""
    tool = BrowserTool()
    callback_mock = MagicMock(return_value=True)
    gate = PermissionGate(callback=callback_mock)

    # 1. Verify LOW-risk actions automatically approved (bypasses callback)
    assert gate.check_permission(tool, {"action": "open_url", "url": "https://google.com"}) is True
    assert gate.check_permission(tool, {"action": "search_google", "query": "Nova"}) is True
    assert gate.check_permission(tool, {"action": "extract_text"}) is True
    callback_mock.assert_not_called()

    # 2. Verify HIGH-risk actions call the permission gate callback
    callback_mock.reset_mock()
    assert gate.check_permission(tool, {"action": "click_element", "selector": "#delete"}) is True
    callback_mock.assert_called_once_with("browser_agent", {"action": "click_element", "selector": "#delete"})

    callback_mock.reset_mock()
    assert gate.check_permission(tool, {"action": "download_file", "selector_or_url": "link", "save_path": "a.zip"}) is True
    callback_mock.assert_called_once_with("browser_agent", {"action": "download_file", "selector_or_url": "link", "save_path": "a.zip"})
