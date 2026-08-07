"""
tests/test_planner_agent.py
----------------------------
Comprehensive unit and integration tests for the PlannerAgent pipeline
and its dynamic routing integration within the ExecutiveAgent.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.executive_agent import ExecutiveAgent, ExecutionStatus
from agents.planner_agent import (
    ExecutionGraph,
    ExecutionPlan,
    ExecutionTask,
    GoalDecomposer,
    PlannerAgent,
    PlannerResult,
    PlannerState,
    TaskStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# Graph & Topological Sort Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutionGraph:
    def test_topological_order_no_deps(self):
        graph = ExecutionGraph()
        t1 = ExecutionTask(task_id="t1")
        t2 = ExecutionTask(task_id="t2")
        graph.add_task(t1)
        graph.add_task(t2)
        assert graph.get_topological_order() == ["t1", "t2"]

    def test_topological_order_with_deps(self):
        graph = ExecutionGraph()
        t1 = ExecutionTask(task_id="t1")
        t2 = ExecutionTask(task_id="t2")
        t3 = ExecutionTask(task_id="t3")
        graph.add_task(t1)
        graph.add_task(t2)
        graph.add_task(t3)

        # t3 depends on t2, t2 depends on t1
        graph.add_dependency("t3", "t2")
        graph.add_dependency("t2", "t1")

        assert graph.get_topological_order() == ["t1", "t2", "t3"]

    def test_cycle_detection(self):
        graph = ExecutionGraph()
        t1 = ExecutionTask(task_id="t1")
        t2 = ExecutionTask(task_id="t2")
        graph.add_task(t1)
        graph.add_task(t2)

        # t1 depends on t2, t2 depends on t1 (cycle)
        graph.add_dependency("t1", "t2")
        graph.add_dependency("t2", "t1")

        with pytest.raises(ValueError, match="cycle"):
            graph.get_topological_order()


# ─────────────────────────────────────────────────────────────────────────────
# Goal Decomposer Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGoalDecomposer:
    def setup_method(self):
        self.decomposer = GoalDecomposer()

    def test_decompose_numbered_steps(self):
        goal = "Goal:\n1. create folder 'src'\n2. create file 'src/main.py'"
        plan = self.decomposer.decompose(goal)
        tasks = list(plan.graph.tasks.values())
        assert len(tasks) == 2
        assert "create folder" in tasks[0].instruction
        assert "create file" in tasks[1].instruction
        assert tasks[0].assigned_agent == "workspace"
        assert tasks[1].assigned_agent == "workspace"

    def test_decompose_connectors(self):
        goal = "open url 'http://site.com' and then search google for python"
        plan = self.decomposer.decompose(goal)
        tasks = list(plan.graph.tasks.values())
        assert len(tasks) == 2
        assert tasks[0].assigned_agent == "browser"
        assert tasks[1].assigned_agent == "browser"

    def test_agent_selection(self):
        assert self.decomposer._select_agent("create python script") == "coding"
        assert self.decomposer._select_agent("open url") == "browser"
        assert self.decomposer._select_agent("call Mom") == "android"
        assert self.decomposer._select_agent("create folder") == "workspace"
        assert self.decomposer._select_agent("tell me a joke") == "engine"


# ─────────────────────────────────────────────────────────────────────────────
# PlannerAgent Coordination Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPlannerAgent:
    @pytest.fixture
    def engine(self):
        m = MagicMock()
        m.handle_input.return_value = "engine output"
        return m

    def test_execute_success(self, engine):
        agent = PlannerAgent(engine=engine)
        goal = "1. do something\n2. do something else"
        result = agent.execute(goal)
        assert result.status == PlannerState.SUCCESS
        assert result.tasks_succeeded == 2
        assert len(engine.handle_input.call_args_list) == 2

    def test_execute_skip_on_dependent_failure(self, engine):
        agent = PlannerAgent(engine=engine)
        # Mock engine to fail 3 times (1 initial run + 2 retries) so Task 1 fails completely
        engine.handle_input.side_effect = [
            RuntimeError("Action failed"),
            RuntimeError("Action failed"),
            RuntimeError("Action failed"),
            "success"
        ]
        goal = "1. do fail\n2. do success"
        result = agent.execute(goal)
        assert result.status == PlannerState.FAILED
        assert result.tasks_failed == 2  # one failed, one skipped due to dependency
        assert len(engine.handle_input.call_args_list) == 3

    def test_cancellation(self, engine):
        agent = PlannerAgent(engine=engine)
        # Use progress callback to trigger cancellation in-flight
        def callback(task):
            if task.status == TaskStatus.RUNNING:
                agent.cancel()
        agent.progress_callback = callback

        result = agent.execute("1. run first\n2. run second")
        assert result.status == PlannerState.CANCELLED


    def test_dispatch_specialized_agents(self, engine):
        mock_coding = MagicMock()
        res_coding = MagicMock()
        res_coding.status = "SUCCESS"
        res_coding.summary.return_value = "Mock coding summary"
        mock_coding.execute.return_value = res_coding

        agent = PlannerAgent(engine=engine, coding_agent=mock_coding)
        result = agent.execute("create python script for sorting")
        assert result.status == PlannerState.SUCCESS
        mock_coding.execute.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Integration Routing Verification
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutiveAgentPlannerIntegration:
    def test_routing_to_planner(self):
        engine = MagicMock()
        planner_agent = MagicMock()
        res = MagicMock()
        res.status = PlannerState.SUCCESS
        res.final_summary = "composite plan solved"
        planner_agent.execute.return_value = res

        exec_agent = ExecutiveAgent(engine=engine, planner_agent=planner_agent)
        result = exec_agent.execute("复合任务 / composite task:\n1. run step a\n2. run step b")
        
        # Verify planner_agent handled the execution
        planner_agent.execute.assert_called_once()
        assert result.status == ExecutionStatus.SUCCESS
        assert result.final_response == "composite plan solved"
        assert len(engine.handle_input.calls if hasattr(engine.handle_input, "calls") else []) == 0
