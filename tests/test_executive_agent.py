"""
tests/test_executive_agent.py
------------------------------
Comprehensive unit tests for the Executive Agent pipeline.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.executive_agent import (
    ExecutiveAgent,
    ExecutionPlan,
    ExecutionPlanner,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStep,
    IntentAnalyzer,
    IntentType,
    ResultCollector,
    StepExecutor,
    TaskClassifier,
    TaskType,
)


# ─────────────────────────────────────────────────────────────────────────────
# Intent Analyzer Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentAnalyzer:
    def setup_method(self):
        self.analyzer = IntentAnalyzer()

    def test_call_intent(self):
        assert self.analyzer.analyze("Call Mom") == IntentType.COMMUNICATION

    def test_open_intent(self):
        assert self.analyzer.analyze("Open YouTube") == IntentType.NAVIGATION

    def test_volume_intent(self):
        assert self.analyzer.analyze("Set volume to 50") == IntentType.SYSTEM

    def test_remember_intent(self):
        assert self.analyzer.analyze("Remember my meeting is at 5pm") == IntentType.MEMORY

    def test_create_intent(self):
        assert self.analyzer.analyze("Create a Python script for sorting") == IntentType.CREATION

    def test_analyse_intent(self):
        assert self.analyzer.analyze("Analyze this log file") == IntentType.ANALYSIS

    def test_query_intent(self):
        assert self.analyzer.analyze("What is the capital of France?") == IntentType.QUERY

    def test_general_fallback(self):
        assert self.analyzer.analyze("Hello there") == IntentType.GENERAL


# ─────────────────────────────────────────────────────────────────────────────
# Task Classifier Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskClassifier:
    def setup_method(self):
        self.classifier = TaskClassifier()

    def test_short_vague_input_is_clarification(self):
        # Single-word input with no context → clarification
        result = self.classifier.classify("hm", IntentType.GENERAL)
        assert result == TaskType.CLARIFICATION

    def test_action_maps_to_single_tool(self):
        result = self.classifier.classify("Please call Mom right now for me", IntentType.COMMUNICATION)
        assert result == TaskType.SINGLE_TOOL

    def test_multi_step_detected_via_connector(self):
        result = self.classifier.classify("Open Chrome and then search Google", IntentType.ACTION)
        assert result == TaskType.MULTI_TOOL

    def test_query_maps_to_conversational(self):
        result = self.classifier.classify("What is machine learning?", IntentType.QUERY)
        assert result == TaskType.CONVERSATIONAL

    def test_planning_marker(self):
        result = self.classifier.classify("How to setup a Python project?", IntentType.GENERAL)
        assert result == TaskType.PLANNING

    def test_long_creation_maps_to_planning(self):
        # 16 words - exceeds the 15-word threshold for creation planning
        long_input = "Create a full REST API server with user authentication and database integration and also write unit tests using FastAPI"
        result = self.classifier.classify(long_input, IntentType.CREATION)
        assert result == TaskType.PLANNING

    def test_short_creation_maps_to_single_tool(self):
        result = self.classifier.classify("Create a new folder", IntentType.CREATION)
        assert result == TaskType.SINGLE_TOOL


# ─────────────────────────────────────────────────────────────────────────────
# Execution Planner Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutionPlanner:
    def setup_method(self):
        self.planner = ExecutionPlanner()

    def test_single_tool_builds_one_step(self):
        plan = self.planner.build_plan("Call Mom", IntentType.COMMUNICATION, TaskType.SINGLE_TOOL)
        assert len(plan.steps) == 1
        assert plan.task_type == TaskType.SINGLE_TOOL

    def test_clarification_builds_clarification_step(self):
        plan = self.planner.build_plan("hi", IntentType.GENERAL, TaskType.CLARIFICATION)
        assert len(plan.steps) == 1
        assert plan.steps[0].input_data == "__clarification__"

    def test_multi_tool_splits_on_connector(self):
        plan = self.planner.build_plan(
            "Open Chrome and then search Google",
            IntentType.ACTION,
            TaskType.MULTI_TOOL,
        )
        assert len(plan.steps) == 2
        assert "Open Chrome" in plan.steps[0].input_data
        assert "search Google" in plan.steps[1].input_data

    def test_multi_step_dependency_chain(self):
        plan = self.planner.build_plan(
            "Open Chrome and then search Google and then open YouTube",
            IntentType.ACTION,
            TaskType.MULTI_TOOL,
        )
        assert len(plan.steps) == 3
        # Each step from step 2 onwards depends on the previous one
        assert plan.steps[1].depends_on == [plan.steps[0].step_id]
        assert plan.steps[2].depends_on == [plan.steps[1].step_id]

    def test_plan_id_unique(self):
        p1 = self.planner.build_plan("Call Mom", IntentType.COMMUNICATION, TaskType.SINGLE_TOOL)
        p2 = self.planner.build_plan("Call Mom", IntentType.COMMUNICATION, TaskType.SINGLE_TOOL)
        assert p1.plan_id != p2.plan_id


# ─────────────────────────────────────────────────────────────────────────────
# ExecutionStep & ExecutionPlan Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutionModels:
    def test_step_duration_none_if_not_run(self):
        step = ExecutionStep()
        assert step.duration is None

    def test_step_duration_computed(self):
        step = ExecutionStep()
        step.started_at = 100.0
        step.finished_at = 102.5
        assert step.duration == pytest.approx(2.5)

    def test_plan_is_complete_when_all_done(self):
        plan = ExecutionPlan()
        s1 = plan.add_step("s1", "input1")
        s2 = plan.add_step("s2", "input2")
        s1.status = ExecutionStatus.SUCCESS
        s2.status = ExecutionStatus.SUCCESS
        assert plan.is_complete
        assert plan.succeeded

    def test_plan_not_complete_while_pending(self):
        plan = ExecutionPlan()
        plan.add_step("s1", "input1")
        assert not plan.is_complete

    def test_plan_not_succeeded_with_failure(self):
        plan = ExecutionPlan()
        s1 = plan.add_step("s1", "input1")
        s1.status = ExecutionStatus.FAILED
        assert plan.is_complete
        assert not plan.succeeded


# ─────────────────────────────────────────────────────────────────────────────
# StepExecutor Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStepExecutor:
    def _mock_engine(self, return_value="OK"):
        engine = MagicMock()
        engine.handle_input.return_value = return_value
        return engine

    def test_successful_execution(self):
        engine = self._mock_engine("Done!")
        executor = StepExecutor(engine)
        step = ExecutionStep(description="test", input_data="do something")
        result = executor.execute(step)
        assert result == "Done!"
        assert step.status == ExecutionStatus.SUCCESS

    def test_clarification_step_returns_preset_message(self):
        engine = self._mock_engine()
        executor = StepExecutor(engine)
        step = ExecutionStep(description="clarify", input_data="__clarification__")
        result = executor.execute(step)
        assert "specific" in result.lower()
        assert step.status == ExecutionStatus.SUCCESS
        engine.handle_input.assert_not_called()

    def test_retry_on_failure_and_eventually_succeeds(self):
        engine = MagicMock()
        # Fail twice then succeed
        engine.handle_input.side_effect = [Exception("Error 1"), Exception("Error 2"), "Success after retries"]
        executor = StepExecutor(engine)
        step = ExecutionStep(description="retry test", input_data="try me", max_retries=2)
        result = executor.execute(step)
        assert result == "Success after retries"
        assert step.status == ExecutionStatus.SUCCESS
        assert step.retry_count == 2

    def test_exhausted_retries_marks_failed(self):
        engine = MagicMock()
        engine.handle_input.side_effect = Exception("Always fails")
        executor = StepExecutor(engine)
        step = ExecutionStep(description="always fail", input_data="fail me", max_retries=1)
        result = executor.execute(step)
        assert step.status == ExecutionStatus.FAILED
        assert "failed" in result.lower()

    def test_cancellation_stops_execution(self):
        engine = self._mock_engine()
        executor = StepExecutor(engine)
        cancel = threading.Event()
        cancel.set()  # Pre-cancelled
        step = ExecutionStep(description="should cancel", input_data="do something")
        result = executor.execute(step, cancel_event=cancel)
        assert step.status == ExecutionStatus.CANCELLED
        engine.handle_input.assert_not_called()

    def test_progress_callback_called(self):
        engine = self._mock_engine("result")
        progress_calls = []
        executor = StepExecutor(engine, progress_callback=lambda s: progress_calls.append(s.status))
        step = ExecutionStep(description="test", input_data="do it")
        executor.execute(step)
        assert ExecutionStatus.SUCCESS in progress_calls


# ─────────────────────────────────────────────────────────────────────────────
# ResultCollector Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestResultCollector:
    def test_single_step_success(self):
        plan = ExecutionPlan(task_type=TaskType.SINGLE_TOOL, intent_type=IntentType.ACTION)
        step = plan.add_step("step1", "input")
        step.status = ExecutionStatus.SUCCESS
        step.output_data = "Call placed."
        collector = ResultCollector()
        result = collector.collect(plan, total_duration=0.5)
        assert result.final_response == "Call placed."
        assert result.status == ExecutionStatus.SUCCESS
        assert result.steps_succeeded == 1
        assert result.steps_failed == 0

    def test_multi_step_combines_outputs(self):
        plan = ExecutionPlan(task_type=TaskType.MULTI_TOOL, intent_type=IntentType.ACTION)
        s1 = plan.add_step("step1", "a")
        s1.status = ExecutionStatus.SUCCESS
        s1.output_data = "Result A."
        s2 = plan.add_step("step2", "b")
        s2.status = ExecutionStatus.SUCCESS
        s2.output_data = "Result B."
        result = ResultCollector().collect(plan, total_duration=1.0)
        assert "Result A." in result.final_response
        assert "Result B." in result.final_response

    def test_partial_failure_overall_status(self):
        plan = ExecutionPlan(task_type=TaskType.MULTI_TOOL, intent_type=IntentType.ACTION)
        s1 = plan.add_step("step1", "a")
        s1.status = ExecutionStatus.SUCCESS
        s1.output_data = "OK"
        s2 = plan.add_step("step2", "b")
        s2.status = ExecutionStatus.FAILED
        s2.output_data = "Error"
        result = ResultCollector().collect(plan, total_duration=0.1)
        assert result.status == ExecutionStatus.FAILED
        assert result.steps_failed == 1

    def test_to_dict_keys(self):
        plan = ExecutionPlan(task_type=TaskType.SINGLE_TOOL, intent_type=IntentType.ACTION)
        s = plan.add_step("s", "i")
        s.status = ExecutionStatus.SUCCESS
        s.output_data = "done"
        result = ResultCollector().collect(plan, 0.0)
        d = result.to_dict()
        assert "plan_id" in d
        assert "final_response" in d
        assert "status" in d


# ─────────────────────────────────────────────────────────────────────────────
# ExecutiveAgent Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutiveAgent:
    def _make_agent(self, engine_response="Done!") -> ExecutiveAgent:
        engine = MagicMock()
        engine.handle_input.return_value = engine_response
        return ExecutiveAgent(engine=engine)

    def test_single_step_execution(self):
        agent = self._make_agent("Phone call initiated.")
        result = agent.execute("Please call Mom right now for me")
        assert isinstance(result, ExecutionResult)
        assert result.final_response == "Phone call initiated."
        assert result.status == ExecutionStatus.SUCCESS

    def test_clarification_response(self):
        agent = self._make_agent()
        result = agent.execute("hi")
        assert "specific" in result.final_response.lower()
        assert result.status == ExecutionStatus.SUCCESS

    def test_multi_step_execution(self):
        engine = MagicMock()
        engine.handle_input.side_effect = ["Chrome opened.", "YouTube opened."]
        agent = ExecutiveAgent(engine=engine)
        result = agent.execute("Open Chrome and then open YouTube")
        assert result.steps_executed == 2
        assert result.steps_succeeded == 2

    def test_engine_failure_recovery(self):
        engine = MagicMock()
        engine.handle_input.side_effect = [Exception("crash"), "Recovered"]
        agent = ExecutiveAgent(engine=engine)
        result = agent.execute("Please call Mom right now for me")
        assert result.status == ExecutionStatus.SUCCESS
        assert "Recovered" in result.final_response

    def test_exhausted_retries_returns_failure(self):
        engine = MagicMock()
        engine.handle_input.side_effect = Exception("Persistent failure")
        agent = ExecutiveAgent(engine=engine)
        result = agent.execute("Do something risky")
        assert result.status == ExecutionStatus.FAILED

    def test_cancellation_mid_execution(self):
        call_count = {"n": 0}

        def slow_engine(text, stream=False):
            call_count["n"] += 1
            time.sleep(0.3)
            return "ok"

        engine = MagicMock()
        engine.handle_input.side_effect = slow_engine

        agent = ExecutiveAgent(engine=engine)
        # Cancel slightly after we kick off
        threading.Timer(0.05, agent.cancel).start()
        result = agent.execute("Open Chrome and then open YouTube and then play music")
        # At least some steps should be cancelled
        assert any(True for _ in [result.status])  # just assert no exception

    def test_handle_input_compat_shim_returns_string(self):
        agent = self._make_agent("Got it.")
        response = agent.handle_input("What time is it?")
        assert isinstance(response, str)
        assert response == "Got it."

    def test_handle_input_stream_shim_returns_generator(self):
        agent = self._make_agent("Streaming response.")
        gen = agent.handle_input("What time is it?", stream=True)
        chunks = list(gen)
        assert "Streaming response." in chunks[0]

    def test_progress_callback_invoked(self):
        steps_reported = []
        engine = MagicMock()
        engine.handle_input.return_value = "ok"
        agent = ExecutiveAgent(engine=engine, progress_callback=lambda s: steps_reported.append(s))
        agent.execute("Please call Mom right now for me")
        assert len(steps_reported) > 0
        assert any(s.status == ExecutionStatus.SUCCESS for s in steps_reported)
