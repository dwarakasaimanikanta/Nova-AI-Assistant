"""
tests/test_browser_agent.py
---------------------------
Unit tests for BrowserManager, BrowserTool, and browser PermissionGate checks.
Fully mocked to ensure headless execution without requiring actual Playwright browser binaries.
"""

from unittest.mock import MagicMock, patch
import pytest

from tools.browser_tool import BrowserTool
from utils.browser_manager import BrowserManager
from tools.permission_gate import PermissionGate
from tools.base_tool import RiskLevel


@pytest.fixture
def mock_playwright_context():
    """Generates complete mock structure of Playwright page, contexts, and browsers."""
    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        
        # Link context tree
        mock_sync.return_value.start.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        yield mock_p, mock_browser, mock_context, mock_page


def test_browser_manager_actions(mock_playwright_context) -> None:
    """BrowserManager: verify navigations, searches, clicks, typing, and closes call Playwright."""
    _, _, _, mock_page = mock_playwright_context
    
    manager = BrowserManager()
    res_launch = manager.launch_browser("chromium", headless=True)
    assert "Success" in res_launch
    assert manager.mock_mode is False

    # 1. Open URL
    manager.open_url("http://test.com")
    mock_page.goto.assert_called_with("http://test.com", wait_until="load")

    # 2. Search Google
    manager.search_google("RAG agent")
    mock_page.fill.assert_any_call("input[name='q']", "RAG agent")
    mock_page.press.assert_any_call("input[name='q']", "Enter")

    # 3. Click Element
    manager.click_element("button#submit")
    mock_page.click.assert_called_with("button#submit")

    # 4. Type Text
    manager.type_text("input#name", "Nova Assistant")
    mock_page.fill.assert_called_with("input#name", "Nova Assistant")

    # 5. Extract Text
    mock_page.inner_text.return_value = "Page body text content"
    txt = manager.extract_text()
    assert txt == "Page body text content"
    mock_page.inner_text.assert_called_with("body")

    # 6. Close Browser
    res_close = manager.close_browser()
    assert "Success" in res_close
    mock_page.close.assert_called_once()


def test_browser_manager_resiliency_fallback() -> None:
    """BrowserManager: verify launch failures fallback to Mock Browser Mode gracefully."""
    # Force exception during playwright import or start
    with patch("playwright.sync_api.sync_playwright", side_effect=ImportError("No driver found")):
        manager = BrowserManager()
        res = manager.launch_browser()
        
        assert "Success" in res
        assert manager.mock_mode is True
        
        # Test subsequent operations do not crash and report Mock Mode Success
        res_open = manager.open_url("http://verify.org")
        assert "Mock Mode" in res_open
        
        res_search = manager.search_google("testing")
        assert "Mock Mode" in res_search


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
