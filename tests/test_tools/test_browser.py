"""
tests/test_tools/test_browser.py
--------------------------------
Unit tests for Nova's consolidated browser tool and plugin system.
"""

from typing import Any
from unittest.mock import patch

from tools.browser import BrowserTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_browser_schema() -> None:
    """Ensure BrowserTool defines standard properties schema and is classified as LOW risk."""
    tool = BrowserTool()
    assert tool.name == "browser"
    assert tool.risk_level == RiskLevel.LOW
    assert "action" in tool.parameters_schema["required"]
    assert "open_google" in tool.parameters_schema["properties"]["action"]["enum"]
    assert "open_url" in tool.parameters_schema["properties"]["action"]["enum"]


def test_browser_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and loads the BrowserPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    # BrowserPlugin should be found and loaded dynamically
    assert len(discovered_plugins) >= 2
    assert any(p.name == "browser" for p in discovered_plugins)


def test_engine_browser_registration() -> None:
    """Ensure engine dynamically registers browser tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    # BrowserPlugin should be loaded
    assert any(p.name == "browser" for p in engine.plugins)

    # BrowserTool should be registered in registry
    assert engine.registry.get_tool("browser") is not None


@patch("webbrowser.open")
def test_browser_actions(mock_open: Any) -> None:
    """Ensure BrowserTool triggerswebBrowser.open with correct destination URLs."""
    tool = BrowserTool()

    # 1. open_google
    res = tool.execute(action="open_google")
    assert "Success" in res
    mock_open.assert_called_with("https://www.google.com")

    # 2. open_youtube
    res = tool.execute(action="open_youtube")
    assert "Success" in res
    mock_open.assert_called_with("https://www.youtube.com")

    # 3. open_github
    res = tool.execute(action="open_github")
    assert "Success" in res
    mock_open.assert_called_with("https://www.github.com")

    # 4. open_chatgpt
    res = tool.execute(action="open_chatgpt")
    assert "Success" in res
    mock_open.assert_called_with("https://chatgpt.com")

    # 5. open_url (with scheme)
    res = tool.execute(action="open_url", url="https://example.com/test")
    assert "Success" in res
    mock_open.assert_called_with("https://example.com/test")

    # 6. open_url (without scheme - should prepend https://)
    res = tool.execute(action="open_url", url="example.com/abc")
    assert "Success" in res
    mock_open.assert_called_with("https://example.com/abc")

    # 7. google_search (escaped)
    res = tool.execute(action="google_search", query="Nova AI Assistant")
    assert "Success" in res
    mock_open.assert_called_with("https://www.google.com/search?q=Nova+AI+Assistant")

    # 8. youtube_search (escaped)
    res = tool.execute(action="youtube_search", query="lofi hip hop")
    assert "Success" in res
    mock_open.assert_called_with("https://www.youtube.com/results?search_query=lofi+hip+hop")


def test_browser_missing_params() -> None:
    """Ensure BrowserTool handles missing arguments gracefully."""
    tool = BrowserTool()

    assert "Failure" in tool.execute(action="open_url")
    assert "Failure" in tool.execute(action="google_search")
    assert "Failure" in tool.execute(action="youtube_search")
    assert "Failure" in tool.execute(action="invalid_action")
