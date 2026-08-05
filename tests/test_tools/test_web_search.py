"""
tests/test_tools/test_web_search.py
-----------------------------------
Unit tests for Nova's consolidated web search tool and plugin.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from tools.web_search import WebSearchTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_web_search_schema() -> None:
    """Ensure WebSearchTool defines correct parameters schema and is LOW risk."""
    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert tool.risk_level == RiskLevel.LOW
    assert "query" in tool.parameters_schema["required"]
    assert "type" in tool.parameters_schema["properties"]["query"]


def test_web_search_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and registers the WebSearchPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    # WebSearchPlugin, MemoryPlugin, BrowserPlugin, FileManagerPlugin, TerminalPlugin should be loaded
    assert len(discovered_plugins) >= 5
    assert any(p.name == "web_search" for p in discovered_plugins)


def test_engine_web_search_registration() -> None:
    """Ensure engine dynamically registers web search tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    # WebSearchPlugin should be loaded
    assert any(p.name == "web_search" for p in engine.plugins)

    # WebSearchTool should be registered in registry
    assert engine.registry.get_tool("web_search") is not None


@patch("tools.web_search.DDGS")
def test_web_search_execution_success(mock_ddgs_cls: Any) -> None:
    """Ensure WebSearchTool queries DDGS and returns formatted outputs successfully."""
    # Setup mock instance context manager
    mock_instance = MagicMock()
    mock_instance.text.return_value = [
        {"title": "OpenAI", "href": "https://openai.com", "body": "OpenAI is an AI research laboratory..."},
        {"title": "Python Tutorials", "href": "https://python.org", "body": "Learn python Programming with tutorials..."}
    ]
    mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

    tool = WebSearchTool()
    res = tool.execute(query="test query")

    assert "OpenAI" in res
    assert "https://openai.com" in res
    assert "Python Tutorials" in res
    mock_instance.text.assert_called_with("test query", max_results=5)


@patch("tools.web_search.DDGS")
def test_web_search_no_results(mock_ddgs_cls: Any) -> None:
    """Ensure WebSearchTool returns informational message if no results found."""
    mock_instance = MagicMock()
    mock_instance.text.return_value = []
    mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

    tool = WebSearchTool()
    res = tool.execute(query="nonexistent term")

    assert "no search results found" in res.lower()


def test_web_search_missing_params() -> None:
    """Ensure WebSearchTool handles empty queries gracefully."""
    tool = WebSearchTool()
    assert "Failure" in tool.execute(query="")
    assert "Failure" in tool.execute()
