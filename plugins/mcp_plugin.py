"""
plugins/mcp_plugin.py
---------------------
MCPPlugin scans discovered servers and dynamically registers their tools.
Conforms to Nova's BasePlugin and BaseTool architectures.
"""

import json
from typing import Any, List, Optional
from plugins.base import BasePlugin
from tools.base_tool import BaseTool, RiskLevel
from utils.mcp_manager import MCPManager
from utils.logger import get_logger

logger = get_logger(__name__)


class MCPToolWrapper(BaseTool):
    """Dynamic tool wrapper that routes requests to an underlying MCP server tool."""

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str,
        parameters_schema: dict[str, Any],
        mcp_manager: MCPManager,
    ) -> None:
        self._name = f"mcp_{server_name}_{tool_name}"
        self._description = f"[MCP: {server_name}] {description}"
        self._parameters_schema = parameters_schema
        self.server_name = server_name
        self.tool_name = tool_name
        self.mcp_manager = mcp_manager

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return self._parameters_schema

    @property
    def risk_level(self) -> RiskLevel:
        # MCP tools can perform write actions; default to RiskLevel.HIGH to ensure safety gates.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        """Forward execution parameters to the MCPManager call route."""
        return self.mcp_manager.call_tool(self.server_name, self.tool_name, kwargs)


class MCPPlugin(BasePlugin):
    """Dynamic plugin that exposes tools discovered from active MCP server instances."""

    def __init__(self, mcp_manager: Optional[MCPManager] = None) -> None:
        self.manager = mcp_manager or MCPManager()

    @property
    def name(self) -> str:
        return "mcp"

    def get_tools(self) -> List[BaseTool]:
        """Discovers tools on connected servers and returns wrappers for them."""
        # Check configured server count to prevent unnecessary startup delays
        configured_count = 0
        if self.manager.config_path.exists():
            try:
                with open(self.manager.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    configured_count = len(config.get("mcpServers", {}))
            except Exception as e:
                logger.error("Failed to parse MCP config count: %s", e)

        # Wait up to 1.5 seconds for background thread connection task completions
        for _ in range(15):
            if len(self.manager.get_connected_servers()) >= configured_count:
                break
            import time
            time.sleep(0.1)

        tools: List[BaseTool] = []
        for server_name in self.manager.get_connected_servers():
            try:
                mcp_tools = self.manager.list_tools(server_name)
                for t in mcp_tools:
                    # Retrieve input schema structure
                    schema = getattr(t, "inputSchema", {})
                    if not schema and isinstance(t, dict):
                        schema = t.get("inputSchema", {})
                        
                    wrapper = MCPToolWrapper(
                        server_name=server_name,
                        tool_name=t.name,
                        description=t.description or "",
                        parameters_schema=schema,
                        mcp_manager=self.manager,
                    )
                    tools.append(wrapper)
                    logger.info("Dynamically registered MCP tool: %s", wrapper.name)
            except Exception as err:
                logger.error("Failed to register tools for MCP server '%s': %s", server_name, err)

        return tools

    def shutdown(self) -> None:
        """Teardown connections on application close."""
        self.manager.shutdown()
