"""
tests/test_execution_pipeline.py
---------------------------------
Comprehensive unit and integration tests for the Executive Integration Pipeline.
"""

from unittest.mock import MagicMock

import pytest

from core.execution_pipeline import ExecutionPipeline
from core.executive_agent import IntentType, TaskType, ExecutionStatus


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_exec_agent():
    ea = MagicMock()
    ea.intent_analyzer = MagicMock()
    ea.task_classifier = MagicMock()
    ea.step_executor = MagicMock()
    
    # Defaults
    ea.intent_analyzer.analyze.return_value = IntentType.GENERAL
    ea.task_classifier.classify.return_value = TaskType.SINGLE_TOOL
    
    result = MagicMock()
    result.status = ExecutionStatus.SUCCESS
    result.final_response = "ExecutiveAgent standard response"
    ea.execute.return_value = result
    
    return ea


@pytest.fixture
def mock_registry():
    return MagicMock()


@pytest.fixture
def mock_planner_agent():
    pa = MagicMock()
    res = MagicMock()
    res.status = "SUCCESS"  # PlannerState.SUCCESS
    res.final_summary = "PlannerAgent plan resolved"
    pa.execute.return_value = res
    return pa


@pytest.fixture
def mock_memory_agent():
    return MagicMock()


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutionPipeline:
    def test_standard_execution_routes_to_exec_agent(
        self, mock_exec_agent, mock_registry, mock_planner_agent, mock_memory_agent
    ):
        progress_messages = []
        def progress_cb(msg):
            progress_messages.append(msg)

        pipeline = ExecutionPipeline(
            executive_agent=mock_exec_agent,
            agent_registry=mock_registry,
            planner_agent=mock_planner_agent,
            memory_agent=mock_memory_agent,
            progress_callback=progress_cb
        )

        response = pipeline.execute("what is the weather today?")

        # Check routing
        mock_exec_agent.execute.assert_called_once_with("what is the weather today?")
        assert response == "ExecutiveAgent standard response"
        
        # Check memory logging
        mock_memory_agent.remember.assert_any_call(
            category="short_term",
            key="last_execution_status",
            value="SUCCESS"
        )

        # Check progress messages
        assert len(progress_messages) > 0
        assert "Analyzing" in progress_messages[0]

    def test_complex_planning_routes_to_planner_agent(
        self, mock_exec_agent, mock_registry, mock_planner_agent, mock_memory_agent
    ):
        # Set task type to PLANNING
        mock_exec_agent.task_classifier.classify.return_value = TaskType.PLANNING
        
        progress_messages = []
        def progress_cb(msg):
            progress_messages.append(msg)

        pipeline = ExecutionPipeline(
            executive_agent=mock_exec_agent,
            agent_registry=mock_registry,
            planner_agent=mock_planner_agent,
            memory_agent=mock_memory_agent,
            progress_callback=progress_cb
        )

        response = pipeline.execute("Complex project roadmap")

        # Check routing
        mock_planner_agent.execute.assert_called_once_with("Complex project roadmap")
        assert response == "PlannerAgent plan resolved"
        
        # Check memory logging
        mock_memory_agent.remember.assert_any_call(
            category="short_term",
            key="last_execution_status",
            value="SUCCESS"
        )
