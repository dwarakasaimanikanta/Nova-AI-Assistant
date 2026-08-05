"""
tests/test_mcp.py
-----------------
Unit tests for the Model Context Protocol (MCP) Client manager and plugin integrations.
Fully mocked to run headlessly in CI/CD without spawning actual subprocesses.
"""

import os
import json
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from utils.mcp_manager import MCPManager
from plugins.mcp_plugin import MCPPlugin, MCPToolWrapper


@pytest.fixture
def temp_mcp_config(tmp_path):
    """Generates a temporary configuration file defining server schemas."""
    config_file = tmp_path / "mcp_config.json"
    config_data = {
        "mcpServers": {
            "test_server": {
                "command": "python",
                "args": ["dummy.py"],
                "env": {"DUMMY_KEY": "value"}
            }
        }
    }
    config_file.write_text(json.dumps(config_data, indent=2))
    return config_file


@pytest.fixture
def mock_mcp_session():
    """Returns a mocked ClientSession with async stubs for discovery and operations."""
    session = MagicMock()
    session.initialize = AsyncMock()
    
    # Mock List Tools
    mock_tool = MagicMock()
    mock_tool.name = "get_weather"
    mock_tool.description = "Get current weather"
    mock_tool.inputSchema = {"type": "object"}
    
    mock_tools_res = MagicMock()
    mock_tools_res.tools = [mock_tool]
    session.list_tools = AsyncMock(return_value=mock_tools_res)

    # Mock Call Tool
    mock_content = MagicMock()
    mock_content.text = "Sunny, 22C"
    mock_call_res = MagicMock()
    mock_call_res.content = [mock_content]
    session.call_tool = AsyncMock(return_value=mock_call_res)

    # Mock List Resources
    mock_resource = MagicMock()
    mock_resource.uri = "file://logs.txt"
    mock_resource.name = "App Logs"
    mock_resource.mimeType = "text/plain"
    mock_resources_res = MagicMock()
    mock_resources_res.resources = [mock_resource]
    session.list_resources = AsyncMock(return_value=mock_resources_res)

    # Mock Read Resource
    mock_res_content = MagicMock()
    mock_res_content.text = "Log contents text line"
    mock_read_res = MagicMock()
    mock_read_res.contents = [mock_res_content]
    session.read_resource = AsyncMock(return_value=mock_read_res)

    # Mock List Prompts
    mock_prompt = MagicMock()
    mock_prompt.name = "summarize"
    mock_prompt.description = "Summarize user input"
    mock_prompt_res = MagicMock()
    mock_prompt_res.prompts = [mock_prompt]
    session.list_prompts = AsyncMock(return_value=mock_prompt_res)

    # Mock Get Prompt
    mock_msg = MagicMock()
    mock_msg.role = "user"
    mock_msg.content = MagicMock(type="text", text="Summarize this text")
    mock_get_prompt_res = MagicMock()
    mock_get_prompt_res.messages = [mock_msg]
    session.get_prompt = AsyncMock(return_value=mock_get_prompt_res)

    return session


@pytest.fixture
def mock_stdio_client(mock_mcp_session):
    """Mocks stdio_client context manager yielding read/write streams."""
    class MockContextManager:
        async def __aenter__(self):
            # Returns (read, write) streams
            return (MagicMock(), MagicMock())
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSessionContextManager:
        async def __aenter__(self):
            return mock_mcp_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("utils.mcp_manager.stdio_client", return_value=MockContextManager()), \
         patch("utils.mcp_manager.ClientSession", return_value=MockSessionContextManager()):
        yield mock_mcp_session


def test_mcp_manager_discovery_and_execution(temp_mcp_config, mock_stdio_client) -> None:
    """Verify MCPManager connects to config servers, loads tools/resources, and runs calls."""
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        manager = MCPManager(config_path=temp_mcp_config)
        
        # Wait up to 1.0 second for thread task to connect
        for _ in range(10):
            if manager.get_connected_servers():
                break
            import time
            time.sleep(0.1)

        assert "test_server" in manager.get_connected_servers()

        # 1. Tools listing and execution
        tools = manager.list_tools("test_server")
        assert len(tools) == 1
        assert tools[0].name == "get_weather"

        res = manager.call_tool("test_server", "get_weather", {"location": "London"})
        assert "Sunny, 22C" in res

        # 2. Resources listing and reading
        resources = manager.list_resources("test_server")
        assert len(resources) == 1
        assert resources[0].name == "App Logs"

        res_content = manager.read_resource("test_server", "file://logs.txt")
        assert "Log contents text line" in res_content

        # 3. Prompts listing and loading
        prompts = manager.list_prompts("test_server")
        assert len(prompts) == 1
        assert prompts[0].name == "summarize"

        prompt_str = manager.get_prompt("test_server", "summarize", {"text": "hello"})
        assert "User: Summarize this text" in prompt_str

        # Shutdown manager thread
        manager.shutdown()


def test_mcp_plugin_dynamic_registration(temp_mcp_config, mock_stdio_client) -> None:
    """Verify MCPPlugin registers discovered tools dynamically as dynamic MCPToolWrapper tools."""
    # Ensure ENVIRONMENT points to production to run actual discovery loops
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        manager = MCPManager(config_path=temp_mcp_config)
        
        # Wait up to 1.0 second for thread task to connect
        for _ in range(10):
            if manager.get_connected_servers():
                break
            import time
            time.sleep(0.1)

        plugin = MCPPlugin(mcp_manager=manager)
        tools = plugin.get_tools()

        assert len(tools) == 1
        assert isinstance(tools[0], MCPToolWrapper)
        assert tools[0].name == "mcp_test_server_get_weather"
        assert "Get current weather" in tools[0].description
        assert tools[0].parameters_schema == {"type": "object"}

        # Check call execution forwards arguments to manager call_tool route
        res = tools[0].execute(location="Paris")
        assert "Sunny, 22C" in res

        plugin.shutdown()


def test_mcp_reconnection_loop(temp_mcp_config, mock_mcp_session) -> None:
    """Verify manager task sleeps and reconnects if server crashes or yields connection errors."""
    call_counts = {"enter": 0}

    class MockReconnectContextManager:
        async def __aenter__(self):
            call_counts["enter"] += 1
            if call_counts["enter"] == 1:
                # Force failure on first attempt to trigger reconnection handler
                raise ConnectionError("Server disconnected unexpectedly")
            return (MagicMock(), MagicMock())
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSessionContextManager:
        async def __aenter__(self):
            return mock_mcp_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("utils.mcp_manager.stdio_client", return_value=MockReconnectContextManager()), \
         patch("utils.mcp_manager.ClientSession", return_value=MockSessionContextManager()), \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep, \
         patch.dict(os.environ, {"ENVIRONMENT": "production"}):
         
        manager = MCPManager(config_path=temp_mcp_config)

        # Wait up to 1.0 second for connection reconnection loop to fire
        for _ in range(10):
            if manager.get_connected_servers():
                break
            import time
            time.sleep(0.1)

        # Reconnection loop should have triggered sleep and then successfully connected
        assert call_counts["enter"] >= 2
        assert "test_server" in manager.get_connected_servers()
        mock_sleep.assert_called_with(5)

        manager.shutdown()
