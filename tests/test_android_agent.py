"""
tests/test_android_agent.py
----------------------------
Comprehensive unit tests for the AndroidAgent pipeline.

All tests use a MockAndroidTool or _StubAndroidTool to avoid requiring
a physical Android device or ADB in the CI environment.
"""

import threading
import time
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from agents.android_agent import (
    ActionRunner,
    AndroidAction,
    AndroidAgent,
    AndroidPlanner,
    AndroidResult,
    AndroidStatus,
    AndroidStep,
    AndroidTask,
    ResultBuilder,
    _StubAndroidTool,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

class MockAndroidTool:
    """
    Configurable mock AndroidTool that records all calls.
    Returns Success: responses by default; Failure: for specified actions.
    """
    def __init__(self, responses: Dict[str, str] = None, fail_actions: list = None):
        self.calls: list = []
        self.responses = responses or {}
        self.fail_actions = fail_actions or []

    def execute(self, **kwargs) -> str:
        self.calls.append(kwargs.copy())
        action = kwargs.get("action", "")
        if action in self.fail_actions:
            return f"Failure: Simulated failure for '{action}'."
        if action in self.responses:
            return self.responses[action]
        return f"Success: {action} executed."


@pytest.fixture
def mock_tool():
    return MockAndroidTool()


@pytest.fixture
def agent(mock_tool):
    return AndroidAgent(android_tool=mock_tool, max_step_retries=1)


# ─────────────────────────────────────────────────────────────────────────────
# AndroidStep model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAndroidStep:
    def test_default_status_pending(self):
        step = AndroidStep(action=AndroidAction.CALL)
        assert step.status == AndroidStatus.PENDING

    def test_duration_none_before_execution(self):
        step = AndroidStep(action=AndroidAction.CALL)
        assert step.duration is None

    def test_duration_computed(self):
        step = AndroidStep(action=AndroidAction.CALL)
        step.started_at = 100.0
        step.finished_at = 102.5
        assert step.duration == pytest.approx(2.5)

    def test_succeeded_true_on_success(self):
        step = AndroidStep(action=AndroidAction.CALL)
        step.status = AndroidStatus.SUCCESS
        assert step.succeeded() is True

    def test_succeeded_false_on_failure(self):
        step = AndroidStep(action=AndroidAction.CALL)
        step.status = AndroidStatus.FAILED
        assert step.succeeded() is False


# ─────────────────────────────────────────────────────────────────────────────
# AndroidTask model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAndroidTask:
    def test_add_step_appends_step(self):
        task = AndroidTask(description="test")
        step = task.add_step(AndroidAction.CALL, "Call Mom", action="call", contact="Mom")
        assert len(task.steps) == 1
        assert step.action == AndroidAction.CALL
        assert step.params == {"action": "call", "contact": "Mom"}

    def test_task_id_unique(self):
        t1 = AndroidTask()
        t2 = AndroidTask()
        assert t1.task_id != t2.task_id

    def test_multiple_steps(self):
        task = AndroidTask()
        task.add_step(AndroidAction.CHECK_DEVICE, "check")
        task.add_step(AndroidAction.CALL, "call", action="call", contact="Dad")
        assert len(task.steps) == 2


# ─────────────────────────────────────────────────────────────────────────────
# AndroidResult model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAndroidResult:
    def _make_result(self, status=AndroidStatus.SUCCESS, final_output="Done"):
        return AndroidResult(
            task_id="abc123",
            status=status,
            steps_executed=1,
            steps_succeeded=1,
            steps_failed=0,
            total_duration=0.5,
            final_output=final_output,
        )

    def test_summary_contains_task_id(self):
        result = self._make_result()
        assert "abc123" in result.summary()

    def test_to_dict_keys(self):
        result = self._make_result()
        d = result.to_dict()
        for key in ("task_id", "status", "steps_executed", "final_output", "errors"):
            assert key in d

    def test_to_dict_status_is_string(self):
        result = self._make_result()
        assert isinstance(result.to_dict()["status"], str)


# ─────────────────────────────────────────────────────────────────────────────
# AndroidPlanner tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAndroidPlanner:
    def setup_method(self):
        self.planner = AndroidPlanner()

    def test_call_request(self):
        task = self.planner.plan("Call Mom")
        assert len(task.steps) == 1
        assert task.steps[0].action == AndroidAction.CALL
        assert task.steps[0].params.get("action") == "call"

    def test_sms_request(self):
        task = self.planner.plan('Send SMS to Dad saying "Hello there"')
        assert task.steps[0].action == AndroidAction.SMS
        assert task.steps[0].params.get("action") == "sms"

    def test_whatsapp_request(self):
        task = self.planner.plan("WhatsApp Ravi saying hi")
        assert task.steps[0].action == AndroidAction.WHATSAPP

    def test_check_device_request(self):
        task = self.planner.plan("Check device connection status")
        assert task.steps[0].action == AndroidAction.CHECK_DEVICE

    def test_reconnect_request(self):
        task = self.planner.plan("Reconnect wireless ADB")
        assert task.steps[0].action == AndroidAction.RECONNECT

    def test_read_contacts_request(self):
        task = self.planner.plan("Show me my contacts")
        assert task.steps[0].action == AndroidAction.READ_CONTACTS

    def test_read_notifications_request(self):
        task = self.planner.plan("Read my notifications")
        assert task.steps[0].action == AndroidAction.READ_NOTIFICATIONS

    def test_open_app_request(self):
        task = self.planner.plan("Open the Camera app")
        assert task.steps[0].action == AndroidAction.OPEN_APP

    def test_open_settings_request(self):
        task = self.planner.plan("Open phone settings")
        assert task.steps[0].action == AndroidAction.OPEN_SETTINGS

    def test_shell_cmd_request(self):
        task = self.planner.plan("Run shell: dumpsys battery")
        assert task.steps[0].action == AndroidAction.SHELL_CMD

    def test_task_description_set(self):
        task = self.planner.plan("Call Mom")
        assert task.description == "Call Mom"

    def test_unknown_falls_back_to_check_device(self):
        task = self.planner.plan("do something unknown")
        assert task.steps[0].action == AndroidAction.CHECK_DEVICE

    def test_contact_extracted_from_call(self):
        task = self.planner.plan("Call Pradeep")
        contact = task.steps[0].params.get("contact", "")
        assert "Pradeep" in contact

    def test_message_extracted_for_sms(self):
        task = self.planner.plan('SMS Ravi saying "Meeting at 5pm"')
        message = task.steps[0].params.get("message", "")
        assert "Meeting at 5pm" in message


# ─────────────────────────────────────────────────────────────────────────────
# ActionRunner tests
# ─────────────────────────────────────────────────────────────────────────────

class TestActionRunner:
    def test_successful_step_sets_success(self):
        tool = MockAndroidTool()
        runner = ActionRunner(tool)
        step = AndroidStep(action=AndroidAction.CALL, params={"action": "call", "contact": "Mom"})
        runner.run(step)
        assert step.status == AndroidStatus.SUCCESS
        assert step.output is not None

    def test_failure_response_marks_failed(self):
        tool = MockAndroidTool(fail_actions=["call"])
        runner = ActionRunner(tool)
        step = AndroidStep(action=AndroidAction.CALL, params={"action": "call", "contact": "X"}, max_retries=0)
        runner.run(step)
        assert step.status == AndroidStatus.FAILED

    def test_retry_eventually_succeeds(self):
        call_count = {"n": 0}
        class RetryTool:
            def execute(self, **kwargs):
                # Reconnect calls must not be counted — they are internal to ActionRunner
                if kwargs.get("action") == "reconnect":
                    return "Success: reconnected."
                call_count["n"] += 1
                if call_count["n"] < 2:
                    return "Failure: first attempt."
                return "Success: second attempt."
        runner = ActionRunner(RetryTool())
        step = AndroidStep(action=AndroidAction.CALL, params={
            "action": "call", "contact": "X"
        }, max_retries=2)
        runner.run(step)
        assert step.status == AndroidStatus.SUCCESS
        assert call_count["n"] == 2

    def test_exhausted_retries_marks_failed(self):
        tool = MockAndroidTool(fail_actions=["call"])
        runner = ActionRunner(tool)
        step = AndroidStep(action=AndroidAction.CALL, params={"action": "call"}, max_retries=1)
        runner.run(step)
        assert step.status == AndroidStatus.FAILED
        assert step.retry_count > 0

    def test_cancellation_stops_before_execution(self):
        tool = MockAndroidTool()
        cancel = threading.Event()
        cancel.set()
        runner = ActionRunner(tool)
        step = AndroidStep(action=AndroidAction.CALL, params={"action": "call", "contact": "Mom"})
        runner.run(step, cancel_event=cancel)
        assert step.status == AndroidStatus.CANCELLED
        assert len(tool.calls) == 0

    def test_progress_callback_called_on_success(self):
        tool = MockAndroidTool()
        events = []
        runner = ActionRunner(tool, progress_callback=lambda s: events.append(s.status))
        step = AndroidStep(action=AndroidAction.CHECK_DEVICE, params={"action": "check_device"})
        runner.run(step)
        assert AndroidStatus.SUCCESS in events

    def test_duration_set_after_run(self):
        tool = MockAndroidTool()
        runner = ActionRunner(tool)
        step = AndroidStep(action=AndroidAction.CHECK_DEVICE, params={"action": "check_device"})
        runner.run(step)
        assert step.duration is not None
        assert step.duration >= 0

    def test_thread_safety(self):
        """Multiple threads executing steps concurrently should not error."""
        tool = MockAndroidTool()
        runner = ActionRunner(tool)
        errors = []

        def run_step():
            step = AndroidStep(action=AndroidAction.CHECK_DEVICE, params={"action": "check_device"})
            try:
                runner.run(step)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=run_step) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ─────────────────────────────────────────────────────────────────────────────
# ResultBuilder tests
# ─────────────────────────────────────────────────────────────────────────────

class TestResultBuilder:
    def _make_task(self, *statuses: AndroidStatus) -> AndroidTask:
        task = AndroidTask(description="test")
        for i, status in enumerate(statuses):
            step = AndroidStep(action=AndroidAction.CALL, params={})
            step.status = status
            step.output = f"output {i}"
            task.steps.append(step)
        return task

    def test_all_success_overall_success(self):
        task = self._make_task(AndroidStatus.SUCCESS, AndroidStatus.SUCCESS)
        result = ResultBuilder().build(task, 1.0)
        assert result.status == AndroidStatus.SUCCESS
        assert result.steps_succeeded == 2
        assert result.steps_failed == 0

    def test_any_failure_overall_failed(self):
        task = self._make_task(AndroidStatus.SUCCESS, AndroidStatus.FAILED)
        result = ResultBuilder().build(task, 1.0)
        assert result.status == AndroidStatus.FAILED
        assert result.steps_failed == 1

    def test_cancelled_task_status(self):
        task = self._make_task(AndroidStatus.CANCELLED)
        task.cancelled = True
        result = ResultBuilder().build(task, 0.1)
        assert result.status == AndroidStatus.CANCELLED

    def test_final_output_is_last_success(self):
        task = self._make_task(AndroidStatus.SUCCESS, AndroidStatus.SUCCESS)
        task.steps[1].output = "last output"
        result = ResultBuilder().build(task, 1.0)
        assert result.final_output == "last output"

    def test_step_outputs_populated(self):
        task = self._make_task(AndroidStatus.SUCCESS)
        result = ResultBuilder().build(task, 0.1)
        assert len(result.step_outputs) == 1
        assert "action" in result.step_outputs[0]

    def test_errors_collected(self):
        task = AndroidTask()
        step = AndroidStep(action=AndroidAction.CALL, params={})
        step.status = AndroidStatus.FAILED
        step.error = "ADB not found."
        task.steps.append(step)
        result = ResultBuilder().build(task, 0.1)
        assert any("ADB not found" in e for e in result.errors)


# ─────────────────────────────────────────────────────────────────────────────
# AndroidAgent Integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAndroidAgent:
    def test_call_request(self, agent):
        result = agent.execute("Call Mom")
        assert isinstance(result, AndroidResult)
        assert result.steps_executed == 1

    def test_sms_request(self, agent):
        result = agent.execute("Send SMS to Dad saying hello")
        assert isinstance(result, AndroidResult)

    def test_whatsapp_request(self, agent):
        result = agent.execute("WhatsApp Ravi saying hi there")
        assert isinstance(result, AndroidResult)

    def test_check_device_request(self, agent):
        result = agent.execute("Check device connection")
        assert isinstance(result, AndroidResult)

    def test_read_contacts_request(self, agent):
        result = agent.execute("Show my contacts")
        assert isinstance(result, AndroidResult)

    def test_read_notifications_request(self, agent):
        result = agent.execute("Read my notifications")
        assert isinstance(result, AndroidResult)

    def test_to_dict_from_execute(self, agent):
        result = agent.execute("Call Mom")
        d = result.to_dict()
        assert "task_id" in d
        assert "status" in d
        assert "final_output" in d

    def test_handle_input_shim_returns_string(self, agent):
        response = agent.handle_input("Call Mom")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_handle_input_stream_returns_generator(self, agent):
        gen = agent.handle_input("Call Mom", stream=True)
        chunks = list(gen)
        assert len(chunks) == 1
        assert isinstance(chunks[0], str)

    def test_progress_callback_invoked(self, mock_tool):
        events = []
        agent = AndroidAgent(
            android_tool=mock_tool,
            progress_callback=lambda s: events.append(s),
        )
        agent.execute("Call Mom")
        assert len(events) > 0

    def test_execute_task_direct_api(self, agent):
        task = AndroidTask(description="Direct task")
        task.add_step(AndroidAction.CALL, "Call Dad", action="call", contact="Dad")
        result = agent.execute_task(task)
        assert isinstance(result, AndroidResult)
        assert result.steps_executed == 1

    def test_failed_step_cancels_remaining(self):
        tool = MockAndroidTool(fail_actions=["call"])
        agent = AndroidAgent(android_tool=tool, max_step_retries=0)
        task = AndroidTask()
        task.add_step(AndroidAction.CALL, "call", action="call", contact="Mom")
        task.add_step(AndroidAction.READ_CONTACTS, "contacts", action="read_contacts")
        agent.execute_task(task)
        assert task.steps[1].status == AndroidStatus.CANCELLED

    def test_cancel_signal_respected(self, mock_tool):
        agent = AndroidAgent(android_tool=mock_tool, max_step_retries=0)
        # Pre-cancel before execute
        agent.cancel()
        task = AndroidTask()
        task.add_step(AndroidAction.CALL, "call", action="call", contact="Mom")
        task.add_step(AndroidAction.SMS, "sms", action="sms", contact="Dad", message="hi")
        agent._run_steps(task)
        # All steps should be cancelled
        for step in task.steps:
            assert step.status == AndroidStatus.CANCELLED

    def test_stub_tool_fallback(self):
        stub = _StubAndroidTool()
        agent = AndroidAgent(android_tool=stub)
        result = agent.execute("Call Mom")
        assert isinstance(result, AndroidResult)
        assert result.steps_executed > 0

    def test_summary_string(self, agent):
        result = agent.execute("Call Mom")
        summary = result.summary()
        assert "AndroidAgent" in summary


# ─────────────────────────────────────────────────────────────────────────────
# _StubAndroidTool tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStubAndroidTool:
    def setup_method(self):
        self.stub = _StubAndroidTool()

    def test_call_returns_success(self):
        assert self.stub.execute(action="call", contact="Mom").startswith("Success")

    def test_sms_returns_success(self):
        assert self.stub.execute(action="sms", contact="Dad", message="hi").startswith("Success")

    def test_whatsapp_returns_success(self):
        assert self.stub.execute(action="whatsapp", contact="Ravi", message="hello").startswith("Success")

    def test_open_app_returns_success(self):
        assert self.stub.execute(action="open_app", app="Camera").startswith("Success")

    def test_check_device_returns_success(self):
        assert self.stub.execute(action="check_device").startswith("Success")

    def test_reconnect_returns_success(self):
        assert self.stub.execute(action="reconnect").startswith("Success")

    def test_read_contacts_returns_success(self):
        assert self.stub.execute(action="read_contacts").startswith("Success")

    def test_read_notifications_returns_success(self):
        assert self.stub.execute(action="read_notifications").startswith("Success")

    def test_shell_cmd_returns_success(self):
        assert self.stub.execute(action="shell_cmd", command="ls").startswith("Success")

    def test_unknown_action_returns_success(self):
        assert self.stub.execute(action="unknown").startswith("Success")
