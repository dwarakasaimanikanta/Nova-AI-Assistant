"""
utils/mcp_manager.py
--------------------
MCPManager handles the lifecycle of multiple Model Context Protocol (MCP) servers.
Runs an asyncio loop in a background thread to manage non-blocking stdio sessions,
supporting discovery, reconnection, tools execution, resources reading, and prompt get requests.
"""

import os
import json
import asyncio
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from utils.logger import get_logger
from config import MCP_CONFIG_FILE

logger = get_logger(__name__)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError as e:
    logger.warning("mcp SDK not found. MCP integration will run in mock/disabled state: %s", e)
    ClientSession = Any
    StdioServerParameters = Any
    stdio_client = Any
    MCP_AVAILABLE = False


class MCPManager:
    """Manages connections to multiple MCP servers over stdio transports."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or MCP_CONFIG_FILE
        self.sessions: Dict[str, ClientSession] = {}
        self.shutdown_events: Dict[str, asyncio.Event] = {}
        self.is_shutting_down = False

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()

        # Connect automatically on initialization
        if MCP_AVAILABLE:
            self.load_and_connect_all()

    def _run_event_loop(self) -> None:
        """Run background event loop."""
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        except Exception as e:
            logger.error("Error in MCPManager background event loop: %s", e)

    def load_and_connect_all(self) -> None:
        """Read mcp_config.json and start connection tasks for all configured servers."""
        if not self.config_path.exists():
            logger.warning("MCP config file not found at %s. Skipping server boot.", self.config_path)
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            logger.error("Failed to parse MCP configuration file: %s", e)
            return

        servers = config_data.get("mcpServers", {})
        for name, info in servers.items():
            command = info.get("command")
            args = info.get("args", [])
            env = info.get("env")
            
            if not command:
                logger.warning("Skipping MCP server '%s': no startup command configured.", name)
                continue

            # Start connection task in background loop
            params = StdioServerParameters(command=command, args=args, env=env)
            asyncio.run_coroutine_threadsafe(self._manage_server_lifecycle(name, params), self.loop)

    async def _manage_server_lifecycle(self, name: str, params: StdioServerParameters) -> None:
        """Lifecycle manager running connection task with auto-reconnect loops."""
        while not self.is_shutting_down:
            try:
                logger.info("Initializing connection to MCP server '%s'...", name)
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self.sessions[name] = session
                        logger.info("Successfully connected and initialized MCP server '%s'.", name)

                        # Keep the session open by waiting on standard shut down event
                        event = asyncio.Event()
                        self.shutdown_events[name] = event
                        await event.wait()
            except Exception as err:
                if self.is_shutting_down:
                    break
                logger.error("MCP Server '%s' session lost or failed to start: %s. Reconnecting in 5s...", name, err)
                self.sessions.pop(name, None)
                await asyncio.sleep(5)

    # --- Synchronous Bridged Operations ---

    def get_connected_servers(self) -> List[str]:
        """List names of active MCP servers."""
        return list(self.sessions.keys())

    # 1. Tools Operations
    async def _list_tools_async(self, server_name: str) -> List[Any]:
        session = self.sessions.get(server_name)
        if not session:
            return []
        res = await session.list_tools()
        return res.tools

    def list_tools(self, server_name: str) -> List[Any]:
        """List tools registered on a specific server."""
        if not MCP_AVAILABLE or os.getenv("ENVIRONMENT") == "test":
            return []
        future = asyncio.run_coroutine_threadsafe(self._list_tools_async(server_name), self.loop)
        try:
            return future.result(timeout=10)
        except Exception as e:
            logger.error("Failed to list tools from MCP server '%s': %s", server_name, e)
            return []

    async def _call_tool_async(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        session = self.sessions.get(server_name)
        if not session:
            raise RuntimeError(f"Server '{server_name}' is disconnected or unavailable.")
        res = await session.call_tool(tool_name, arguments)
        
        # Format tool contents returned by MCP server
        texts = []
        for content in res.content:
            if hasattr(content, "text"):
                texts.append(content.text)
            elif isinstance(content, dict) and "text" in content:
                texts.append(content["text"])
        return "\n".join(texts)

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on a specific server synchronously."""
        if not MCP_AVAILABLE or os.getenv("ENVIRONMENT") == "test":
            return f"[Mock] Execution of mcp_{server_name}_{tool_name} successful."

        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(server_name, tool_name, arguments), self.loop
        )
        try:
            return future.result(timeout=30)
        except Exception as e:
            logger.error("Failed to execute tool '%s' on MCP server '%s': %s", tool_name, server_name, e)
            return f"Failure: Executing MCP tool failed: {e}"

    # 2. Resources Operations
    async def _list_resources_async(self, server_name: str) -> List[Any]:
        session = self.sessions.get(server_name)
        if not session:
            return []
        res = await session.list_resources()
        return res.resources

    def list_resources(self, server_name: str) -> List[Any]:
        """List resources registered on a specific server."""
        if not MCP_AVAILABLE or os.getenv("ENVIRONMENT") == "test":
            return []
        future = asyncio.run_coroutine_threadsafe(self._list_resources_async(server_name), self.loop)
        try:
            return future.result(timeout=10)
        except Exception as e:
            logger.error("Failed to list resources from MCP server '%s': %s", server_name, e)
            return []

    async def _read_resource_async(self, server_name: str, uri: str) -> str:
        session = self.sessions.get(server_name)
        if not session:
            raise RuntimeError(f"Server '{server_name}' is disconnected or unavailable.")
        res = await session.read_resource(uri)
        
        contents = []
        for item in res.contents:
            if hasattr(item, "text"):
                contents.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                contents.append(item["text"])
        return "\n".join(contents)

    def read_resource(self, server_name: str, uri: str) -> str:
        """Read resource content from a specific server synchronously."""
        if not MCP_AVAILABLE or os.getenv("ENVIRONMENT") == "test":
            return f"[Mock] Resource contents from {uri}"

        future = asyncio.run_coroutine_threadsafe(self._read_resource_async(server_name, uri), self.loop)
        try:
            return future.result(timeout=30)
        except Exception as e:
            logger.error("Failed to read resource '%s' on MCP server '%s': %s", uri, server_name, e)
            return f"Failure: Reading MCP resource failed: {e}"

    # 3. Prompts Operations
    async def _list_prompts_async(self, server_name: str) -> List[Any]:
        session = self.sessions.get(server_name)
        if not session:
            return []
        res = await session.list_prompts()
        return res.prompts

    def list_prompts(self, server_name: str) -> List[Any]:
        """List prompts registered on a specific server."""
        if not MCP_AVAILABLE or os.getenv("ENVIRONMENT") == "test":
            return []
        future = asyncio.run_coroutine_threadsafe(self._list_prompts_async(server_name), self.loop)
        try:
            return future.result(timeout=10)
        except Exception as e:
            logger.error("Failed to list prompts from MCP server '%s': %s", server_name, e)
            return []

    async def _get_prompt_async(self, server_name: str, prompt_name: str, arguments: Dict[str, Any]) -> str:
        session = self.sessions.get(server_name)
        if not session:
            raise RuntimeError(f"Server '{server_name}' is disconnected or unavailable.")
        res = await session.get_prompt(prompt_name, arguments)
        
        messages = []
        for msg in res.messages:
            role = msg.role
            content_type = getattr(msg.content, "type", "text")
            content_text = getattr(msg.content, "text", "")
            messages.append(f"{role.capitalize()}: {content_text}")
        return "\n".join(messages)

    def get_prompt(self, server_name: str, prompt_name: str, arguments: Dict[str, Any]) -> str:
        """Get prompt template from a specific server synchronously."""
        if not MCP_AVAILABLE or os.getenv("ENVIRONMENT") == "test":
            return f"[Mock] Prompt template for {prompt_name}"

        future = asyncio.run_coroutine_threadsafe(
            self._get_prompt_async(server_name, prompt_name, arguments), self.loop
        )
        try:
            return future.result(timeout=30)
        except Exception as e:
            logger.error("Failed to fetch prompt '%s' on MCP server '%s': %s", prompt_name, server_name, e)
            return f"Failure: Fetching MCP prompt failed: {e}"

    # --- Shutdown Lifecycle ---

    def shutdown(self) -> None:
        """Close all active sessions, terminate background event loops and threads."""
        self.is_shutting_down = True
        
        # Stop background server lifecycle tasks
        for name, event in list(self.shutdown_events.items()):
            try:
                self.loop.call_soon_threadsafe(event.set)
            except Exception:
                pass
                
        # Close loop
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            pass

        if self.thread.is_alive():
            self.thread.join(timeout=3.0)
        logger.info("MCPManager shutdown complete.")
