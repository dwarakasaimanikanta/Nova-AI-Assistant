"""
tests/test_executive_agent_routing.py
--------------------------------------
Integration tests for ExecutiveAgent request routing to sub-agents.
"""

from unittest.mock import MagicMock

import pytest

from core.executive_agent import ExecutiveAgent, ExecutionStatus, IntentType, TaskType
from agents.coding_agent import CodingStatus
from agents.browser_agent import BrowserStatus
from agents.android_agent import AndroidStatus


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

class MockEngine:
    """Mock NovaEngine for fallback execution."""
    def __init__(self):
        self.calls = []

    def handle_input(self, user_input: str, stream: bool = False) -> str:
        self.calls.append(user_input)
        return f"Engine output: {user_input}"


@pytest.fixture
def engine():
    return MockEngine()


@pytest.fixture
def mock_coding_agent():
    agent = MagicMock()
    # Mock return value of execute
    result = MagicMock()
    result.status = CodingStatus.SUCCESS
    result.summary.return_value = "Mock Coding success summary"
    result.errors = []
    agent.execute.return_value = result
    return agent


@pytest.fixture
def mock_browser_agent():
    agent = MagicMock()
    result = MagicMock()
    result.status = BrowserStatus.SUCCESS
    result.final_output = "Mock Browser final output"
    result.summary.return_value = "Mock Browser success summary"
    result.errors = []
    agent.execute.return_value = result
    return agent


@pytest.fixture
def mock_android_agent():
    agent = MagicMock()
    result = MagicMock()
    result.status = AndroidStatus.SUCCESS
    result.final_output = "Mock Android final output"
    result.summary.return_value = "Mock Android success summary"
    result.errors = []
    agent.execute.return_value = result
    return agent


@pytest.fixture
def exec_agent(engine, mock_coding_agent, mock_browser_agent, mock_android_agent):
    return ExecutiveAgent(
        engine=engine,
        coding_agent=mock_coding_agent,
        browser_agent=mock_browser_agent,
        android_agent=mock_android_agent,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routing Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutiveAgentRouting:
    def test_coding_request_routes_to_coding_agent(self, exec_agent, mock_coding_agent, engine):
        # Triggering CREATION intent
        result = exec_agent.execute("Create a Python script for sorting")
        
        # Verify CodingAgent was called
        mock_coding_agent.execute.assert_called_once_with("Create a Python script for sorting")
        # Verify NovaEngine was NOT called
        assert len(engine.calls) == 0
        # Verify result contains the routed response
        assert result.status == ExecutionStatus.SUCCESS
        assert result.final_response == "Mock Coding success summary"

    def test_browser_request_routes_to_browser_agent(self, exec_agent, mock_browser_agent, engine):
        # Triggering NAVIGATION intent
        result = exec_agent.execute("Open https://github.com")
        
        # Verify BrowserAgent was called
        mock_browser_agent.execute.assert_called_once_with("Open https://github.com")
        # Verify NovaEngine was NOT called
        assert len(engine.calls) == 0
        # Verify result contains the routed response
        assert result.status == ExecutionStatus.SUCCESS
        assert result.final_response == "Mock Browser final output"

    def test_android_request_routes_to_android_agent(self, exec_agent, mock_android_agent, engine):
        # Triggering COMMUNICATION intent
        result = exec_agent.execute("Call Mom")
        
        # Verify AndroidAgent was called
        mock_android_agent.execute.assert_called_once_with("Call Mom")
        # Verify NovaEngine was NOT called
        assert len(engine.calls) == 0
        # Verify result contains the routed response
        assert result.status == ExecutionStatus.SUCCESS
        assert result.final_response == "Mock Android final output"

    def test_unknown_request_falls_back_to_engine(
        self, exec_agent, mock_coding_agent, mock_browser_agent, mock_android_agent, engine
    ):
        # General query / non-agent intent
        result = exec_agent.execute("What is the capital of France?")
        
        # Verify no agents were called
        assert not mock_coding_agent.execute.called
        assert not mock_browser_agent.execute.called
        assert not mock_android_agent.execute.called
        
        # Verify engine was called
        assert len(engine.calls) == 1
        assert "capital of France" in engine.calls[0]
        assert result.status == ExecutionStatus.SUCCESS
        assert result.final_response == "Engine output: What is the capital of France?"

    def test_agent_failure_falls_back_to_engine(self, exec_agent, mock_coding_agent, engine):
        # Set mock coding agent to return FAILED
        fail_result = MagicMock()
        fail_result.status = CodingStatus.FAILED
        fail_result.errors = ["Mock compilation error"]
        mock_coding_agent.execute.return_value = fail_result
        
        # Run coding request
        result = exec_agent.execute("Create a Python script for sorting")
        
        # Verify CodingAgent was called
        mock_coding_agent.execute.assert_called_once()
        # Verify engine was invoked as fallback
        assert len(engine.calls) == 1
        assert result.final_response == "Engine output: Create a Python script for sorting"

    def test_agent_exception_falls_back_to_engine(self, exec_agent, mock_coding_agent, engine):
        # Set mock coding agent to raise an exception
        mock_coding_agent.execute.side_effect = RuntimeError("Something went wrong")
        
        # Run coding request
        result = exec_agent.execute("Create a Python script for sorting")
        
        # Verify CodingAgent was called
        mock_coding_agent.execute.assert_called_once()
        # Verify engine was invoked as fallback
        assert len(engine.calls) == 1
        assert result.final_response == "Engine output: Create a Python script for sorting"
