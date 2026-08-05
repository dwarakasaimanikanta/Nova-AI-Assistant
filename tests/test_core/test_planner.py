"""
tests/test_core/test_planner.py
--------------------------------
Unit tests for the AgentPlanner loop orchestration.
"""

from typing import Any
from unittest.mock import MagicMock

from core.planner import AgentPlanner
from memory.short_term import ShortTermMemory
from llm.base_provider import LLMResponse
from tools.base_tool import BaseTool
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from tools.permission_gate import PermissionGate


class MockSearchTool(BaseTool):
    """Mock search tool that is not a direct-return built-in tool."""

    @property
    def name(self) -> str:
        return "custom_search"

    @property
    def description(self) -> str:
        return "Mock search tool."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    def execute(self, **kwargs: Any) -> str:
        return "Search results: found 3 pages"


def test_planner_direct_answer() -> None:
    """Ensure AgentPlanner handles text responses directly without executing tools."""
    memory = ShortTermMemory()
    provider = MagicMock()
    # Mock direct text reply
    provider.generate.return_value = LLMResponse(text="Direct response text")

    registry = ToolRegistry()
    executor = ToolExecutor()
    gate = PermissionGate()

    planner = AgentPlanner(provider, memory, registry, executor, gate)
    response = planner.ask("Query")

    assert response == "Direct response text"
    # Ensure message is saved in short-term memory
    history = memory.get_history()
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "Query"
    assert history[1].role == "assistant"
    assert history[1].content == "Direct response text"


def test_planner_tool_calling_loop() -> None:
    """Ensure AgentPlanner coordinates iterative tool execution loops."""
    memory = ShortTermMemory()
    provider = MagicMock()

    # 1. First call: Gemini returns function call request
    fc = {"name": "custom_search", "args": {"query": "gemini documentation"}}
    provider.generate.side_effect = [
        LLMResponse(function_calls=[fc]),
        LLMResponse(text="The documentation says Gemini is fast"),
    ]

    registry = ToolRegistry()
    search_tool = MockSearchTool()
    registry.register_tool(search_tool)

    executor = ToolExecutor()
    gate = PermissionGate()

    planner = AgentPlanner(provider, memory, registry, executor, gate)
    response = planner.ask("Find Gemini documentation")

    assert response == "The documentation says Gemini is fast"

    # Verify exact conversational sequence registered in history:
    # 1. User prompt
    # 2. Assistant function call intent
    # 3. Tool response value
    # 4. Assistant final response text
    history = memory.get_history()
    assert len(history) == 4
    assert history[0].role == "user"
    assert history[0].content == "Find Gemini documentation"
    assert history[1].role == "assistant"
    assert history[1].function_calls == [fc]
    assert history[2].role == "tool"
    assert history[2].name == "custom_search"
    assert history[2].content == "Search results: found 3 pages"
    assert history[3].role == "assistant"
    assert history[3].content == "The documentation says Gemini is fast"


def test_planner_direct_tool_return() -> None:
    """Ensure AgentPlanner immediately returns the tool output for direct-return tools."""
    memory = ShortTermMemory()
    provider = MagicMock()

    fc = {"name": "calculate_expression", "args": {"expression": "245 * 73"}}
    # Mocking single LLM call returning a tool call
    provider.generate.return_value = LLMResponse(function_calls=[fc])

    registry = ToolRegistry()
    from tools.builtin_tools import CalculateTool
    registry.register_tool(CalculateTool())

    executor = ToolExecutor()
    gate = PermissionGate()

    planner = AgentPlanner(provider, memory, registry, executor, gate)
    response = planner.ask("What is 245 * 73?")

    # Verify that the direct tool output is returned immediately
    assert response == "245 * 73 = 17885"

    # Verify memory log integrity
    history = memory.get_history()
    assert len(history) == 4
    assert history[0].role == "user"
    assert history[1].role == "assistant"
    assert history[1].function_calls == [fc]
    assert history[2].role == "tool"
    assert history[2].content == "245 * 73 = 17885"
    assert history[3].role == "assistant"
    assert history[3].content == "245 * 73 = 17885"

    # Verify provider was only called once (skipping second LLM generation call)
    provider.generate.assert_called_once()
