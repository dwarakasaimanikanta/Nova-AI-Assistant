"""
tests/test_browser_agent.py
----------------------------
Comprehensive unit tests for the BrowserAgent pipeline.

All tests use a MockBrowserTool to avoid requiring Playwright/Chrome
in the CI environment.
"""

import time
from typing import Any, Dict
from unittest.mock import MagicMock, call, patch

import pytest

from agents.browser_agent import (
    ActionRunner,
    BrowserAction,
    BrowserAgent,
    BrowserPlanner,
    BrowserResult,
    BrowserStatus,
    BrowserStep,
    BrowserTask,
    ResultBuilder,
    _StubBrowserTool,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

class MockBrowserTool:
    """
    Configurable mock browser tool that returns canned responses.
    Records all calls made to it for assertion purposes.
    """
    def __init__(self, responses: Dict[str, str] = None, fail_actions: list = None):
        self.calls: list = []
        self.responses = responses or {}
        self.fail_actions = fail_actions or []

    def execute(self, **kwargs) -> str:
        self.calls.append(kwargs.copy())
        action = kwargs.get("action", "")
        if action in self.fail_actions:
            return f"Failure: Simulated failure for action '{action}'."
        return self.responses.get(action, f"Success: {action} completed.")


@pytest.fixture
def mock_tool():
    return MockBrowserTool()


@pytest.fixture
def agent(mock_tool):
    return BrowserAgent(browser_tool=mock_tool, max_step_retries=1)


# ─────────────────────────────────────────────────────────────────────────────
# BrowserStep model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowserStep:
    def test_default_status_is_pending(self):
        step = BrowserStep(action=BrowserAction.OPEN_URL)
        assert step.status == BrowserStatus.PENDING

    def test_duration_none_before_execution(self):
        step = BrowserStep(action=BrowserAction.OPEN_URL)
        assert step.duration is None

    def test_duration_computed_after_execution(self):
        step = BrowserStep(action=BrowserAction.OPEN_URL)
        step.started_at = 100.0
        step.finished_at = 102.5
        assert step.duration == pytest.approx(2.5)

    def test_succeeded_true_on_success(self):
        step = BrowserStep(action=BrowserAction.OPEN_URL)
        step.status = BrowserStatus.SUCCESS
        assert step.succeeded() is True

    def test_succeeded_false_on_failure(self):
        step = BrowserStep(action=BrowserAction.OPEN_URL)
        step.status = BrowserStatus.FAILED
        assert step.succeeded() is False


# ─────────────────────────────────────────────────────────────────────────────
# BrowserTask model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowserTask:
    def test_add_step_appends_to_list(self):
        task = BrowserTask(description="test")
        step = task.add_step(BrowserAction.OPEN_URL, "Open site", url="https://example.com")
        assert len(task.steps) == 1
        assert step.action == BrowserAction.OPEN_URL
        assert step.params == {"url": "https://example.com"}

    def test_task_id_is_unique(self):
        t1 = BrowserTask()
        t2 = BrowserTask()
        assert t1.task_id != t2.task_id

    def test_multiple_steps(self):
        task = BrowserTask()
        task.add_step(BrowserAction.LAUNCH, "launch")
        task.add_step(BrowserAction.SEARCH, "search", query="test")
        task.add_step(BrowserAction.CLOSE, "close")
        assert len(task.steps) == 3


# ─────────────────────────────────────────────────────────────────────────────
# BrowserResult model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowserResult:
    def _make_result(self, status=BrowserStatus.SUCCESS, final_output="Done"):
        return BrowserResult(
            task_id="abc123",
            status=status,
            steps_executed=2,
            steps_succeeded=2,
            steps_failed=0,
            total_duration=1.5,
            final_output=final_output,
        )

    def test_summary_contains_task_id(self):
        result = self._make_result()
        assert "abc123" in result.summary()

    def test_to_dict_structure(self):
        result = self._make_result()
        d = result.to_dict()
        assert "task_id" in d
        assert "status" in d
        assert "steps_executed" in d
        assert "final_output" in d
        assert "screenshot_paths" in d
        assert "extracted_texts" in d

    def test_to_dict_status_is_string(self):
        result = self._make_result()
        d = result.to_dict()
        assert isinstance(d["status"], str)


# ─────────────────────────────────────────────────────────────────────────────
# BrowserPlanner tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowserPlanner:
    def setup_method(self):
        self.planner = BrowserPlanner()

    def test_search_request_creates_search_step(self):
        task = self.planner.plan("Search Google for Python tutorials")
        actions = [s.action for s in task.steps]
        assert BrowserAction.SEARCH in actions

    def test_open_url_request(self):
        task = self.planner.plan("Open https://example.com")
        actions = [s.action for s in task.steps]
        assert BrowserAction.OPEN_URL in actions

    def test_screenshot_request_includes_screenshot_step(self):
        task = self.planner.plan("Take a screenshot of https://example.com")
        actions = [s.action for s in task.steps]
        assert BrowserAction.SCREENSHOT in actions

    def test_extract_text_request(self):
        task = self.planner.plan("Extract text from https://example.com")
        actions = [s.action for s in task.steps]
        assert BrowserAction.EXTRACT_TEXT in actions

    def test_download_request(self):
        task = self.planner.plan("Download https://example.com/file.pdf save report.pdf")
        actions = [s.action for s in task.steps]
        assert BrowserAction.DOWNLOAD in actions

    def test_always_starts_with_launch(self):
        task = self.planner.plan("Search for cats")
        assert task.steps[0].action == BrowserAction.LAUNCH

    def test_always_ends_with_close(self):
        task = self.planner.plan("Search for cats")
        assert task.steps[-1].action == BrowserAction.CLOSE

    def test_task_has_description(self):
        task = self.planner.plan("Open https://example.com")
        assert task.description == "Open https://example.com"

    def test_url_extraction_with_http(self):
        task = self.planner.plan("Open http://example.com and read it")
        open_steps = [s for s in task.steps if s.action == BrowserAction.OPEN_URL]
        assert len(open_steps) > 0
        assert open_steps[0].params["url"].startswith("http")

    def test_url_extraction_with_www(self):
        task = self.planner.plan("Go to www.github.com")
        open_steps = [s for s in task.steps if s.action == BrowserAction.OPEN_URL]
        assert len(open_steps) > 0
        assert "github" in open_steps[0].params["url"]

    def test_generic_request_falls_back_to_search(self):
        task = self.planner.plan("find Python documentation")
        actions = [s.action for s in task.steps]
        assert BrowserAction.SEARCH in actions


# ─────────────────────────────────────────────────────────────────────────────
# ActionRunner tests
# ─────────────────────────────────────────────────────────────────────────────

class TestActionRunner:
    def test_successful_step_sets_success_status(self):
        tool = MockBrowserTool()
        runner = ActionRunner(tool)
        step = BrowserStep(action=BrowserAction.OPEN_URL, params={"url": "https://example.com"})
        result = runner.run(step)
        assert step.status == BrowserStatus.SUCCESS
        assert step.output is not None

    def test_failure_response_marks_step_failed(self):
        tool = MockBrowserTool(fail_actions=["open_url"])
        runner = ActionRunner(tool, )
        step = BrowserStep(action=BrowserAction.OPEN_URL, params={"url": "https://bad.com"}, max_retries=0)
        runner.run(step)
        assert step.status == BrowserStatus.FAILED

    def test_retry_on_failure_eventually_succeeds(self):
        call_count = {"n": 0}
        class RetryTool:
            def execute(self, **kwargs):
                call_count["n"] += 1
                if call_count["n"] < 2:
                    return "Failure: first attempt."
                return "Success: second attempt."
        runner = ActionRunner(RetryTool())
        step = BrowserStep(action=BrowserAction.OPEN_URL, params={}, max_retries=2)
        result = runner.run(step)
        assert step.status == BrowserStatus.SUCCESS
        assert call_count["n"] == 2

    def test_exhausted_retries_marks_failed(self):
        tool = MockBrowserTool(fail_actions=["open_url"])
        runner = ActionRunner(tool)
        step = BrowserStep(action=BrowserAction.OPEN_URL, params={}, max_retries=1)
        runner.run(step)
        assert step.status == BrowserStatus.FAILED
        assert step.retry_count > 0

    def test_progress_callback_called(self):
        tool = MockBrowserTool()
        progress_calls = []
        runner = ActionRunner(tool, progress_callback=lambda s: progress_calls.append(s.status))
        step = BrowserStep(action=BrowserAction.OPEN_URL, params={})
        runner.run(step)
        assert BrowserStatus.SUCCESS in progress_calls

    def test_step_duration_set_after_run(self):
        tool = MockBrowserTool()
        runner = ActionRunner(tool)
        step = BrowserStep(action=BrowserAction.SEARCH, params={"query": "test"})
        runner.run(step)
        assert step.duration is not None
        assert step.duration >= 0


# ─────────────────────────────────────────────────────────────────────────────
# ResultBuilder tests
# ─────────────────────────────────────────────────────────────────────────────

class TestResultBuilder:
    def _make_task(self, *statuses: BrowserStatus) -> BrowserTask:
        task = BrowserTask(description="test task")
        for i, status in enumerate(statuses):
            step = BrowserStep(action=BrowserAction.OPEN_URL, params={})
            step.status = status
            step.output = f"output {i}"
            task.steps.append(step)
        return task

    def test_all_success_overall_success(self):
        task = self._make_task(BrowserStatus.SUCCESS, BrowserStatus.SUCCESS)
        result = ResultBuilder().build(task, 1.0)
        assert result.status == BrowserStatus.SUCCESS
        assert result.steps_succeeded == 2
        assert result.steps_failed == 0

    def test_any_failure_overall_failed(self):
        task = self._make_task(BrowserStatus.SUCCESS, BrowserStatus.FAILED)
        result = ResultBuilder().build(task, 1.0)
        assert result.status == BrowserStatus.FAILED
        assert result.steps_failed == 1

    def test_screenshot_path_extracted(self):
        task = BrowserTask()
        step = BrowserStep(action=BrowserAction.SCREENSHOT, params={})
        step.status = BrowserStatus.SUCCESS
        step.output = "Success: Screenshot saved to screenshots/nova_20260807.png"
        task.steps.append(step)
        result = ResultBuilder().build(task, 0.5)
        assert len(result.screenshot_paths) == 1
        assert "screenshots" in result.screenshot_paths[0]

    def test_extracted_text_collected(self):
        task = BrowserTask()
        step = BrowserStep(action=BrowserAction.EXTRACT_TEXT, params={})
        step.status = BrowserStatus.SUCCESS
        step.output = "Page content: hello world"
        task.steps.append(step)
        result = ResultBuilder().build(task, 0.5)
        assert len(result.extracted_texts) == 1
        assert "hello world" in result.extracted_texts[0]

    def test_final_output_is_last_success(self):
        task = self._make_task(BrowserStatus.SUCCESS, BrowserStatus.SUCCESS)
        task.steps[1].output = "last output"
        result = ResultBuilder().build(task, 1.0)
        assert result.final_output == "last output"

    def test_step_outputs_list_populated(self):
        task = self._make_task(BrowserStatus.SUCCESS)
        result = ResultBuilder().build(task, 0.1)
        assert len(result.step_outputs) == 1
        assert "action" in result.step_outputs[0]


# ─────────────────────────────────────────────────────────────────────────────
# BrowserAgent Integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowserAgent:
    def test_search_request_succeeds(self, agent):
        result = agent.execute("Search Google for Python tutorials")
        assert isinstance(result, BrowserResult)
        assert result.steps_executed > 0

    def test_open_url_request(self, agent):
        result = agent.execute("Open https://example.com")
        assert isinstance(result, BrowserResult)
        assert result.steps_executed > 0

    def test_screenshot_request(self, agent):
        result = agent.execute("Take a screenshot of https://example.com")
        assert isinstance(result, BrowserResult)

    def test_extract_text_request(self, agent):
        result = agent.execute("Extract text from https://example.com")
        assert isinstance(result, BrowserResult)

    def test_to_dict_from_execute(self, agent):
        result = agent.execute("Search Google for cats")
        d = result.to_dict()
        assert "task_id" in d
        assert "status" in d
        assert isinstance(d["steps_executed"], int)

    def test_handle_input_shim_returns_string(self, agent):
        response = agent.handle_input("Search Google for cats")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_handle_input_stream_returns_generator(self, agent):
        gen = agent.handle_input("Open https://example.com", stream=True)
        chunks = list(gen)
        assert len(chunks) == 1
        assert isinstance(chunks[0], str)

    def test_progress_callback_invoked(self, mock_tool):
        events = []
        agent = BrowserAgent(
            browser_tool=mock_tool,
            progress_callback=lambda s: events.append(s),
        )
        agent.execute("Search for cats")
        assert len(events) > 0

    def test_execute_task_direct_api(self, agent):
        task = BrowserTask(description="Direct task")
        task.add_step(BrowserAction.LAUNCH, "launch", headless=True)
        task.add_step(BrowserAction.SEARCH, "search", query="Nova AI")
        task.add_step(BrowserAction.CLOSE, "close")
        result = agent.execute_task(task)
        assert isinstance(result, BrowserResult)
        assert result.steps_executed == 3

    def test_failed_step_cancels_remaining(self):
        tool = MockBrowserTool(fail_actions=["open_url"])
        agent = BrowserAgent(browser_tool=tool, max_step_retries=0)
        task = BrowserTask()
        task.add_step(BrowserAction.LAUNCH, "launch")
        task.add_step(BrowserAction.OPEN_URL, "open", url="https://example.com")
        task.add_step(BrowserAction.EXTRACT_TEXT, "extract")
        task.add_step(BrowserAction.CLOSE, "close")
        result = agent.execute_task(task)
        # EXTRACT_TEXT should be CANCELLED
        cancelled = [s for s in task.steps if s.status == BrowserStatus.CANCELLED]
        assert len(cancelled) > 0

    def test_close_step_always_runs_despite_failure(self):
        """CLOSE step should still execute even if a prior step fails."""
        tool = MockBrowserTool(fail_actions=["open_url"])
        agent = BrowserAgent(browser_tool=tool, max_step_retries=0)
        task = BrowserTask()
        task.add_step(BrowserAction.LAUNCH, "launch")
        task.add_step(BrowserAction.OPEN_URL, "open", url="https://bad.com")
        task.add_step(BrowserAction.CLOSE, "close")
        # CLOSE is never cancelled because it's excluded from the halt logic
        result = agent.execute_task(task)
        close_step = task.steps[-1]
        # Close step was NOT cancelled (it's excluded from halt logic)
        assert close_step.status != BrowserStatus.CANCELLED

    def test_stub_tool_fallback(self):
        """BrowserAgent must still function when Playwright is unavailable."""
        stub = _StubBrowserTool()
        agent = BrowserAgent(browser_tool=stub)
        result = agent.execute("Search Google for test query")
        assert isinstance(result, BrowserResult)
        assert result.steps_executed > 0


# ─────────────────────────────────────────────────────────────────────────────
# _StubBrowserTool tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStubBrowserTool:
    def setup_method(self):
        self.stub = _StubBrowserTool()

    def test_launch_returns_success(self):
        assert self.stub.execute(action="launch_browser").startswith("Success")

    def test_open_url_returns_success(self):
        assert self.stub.execute(action="open_url", url="https://x.com").startswith("Success")

    def test_search_returns_success(self):
        assert self.stub.execute(action="search_google", query="test").startswith("Success")

    def test_extract_text_returns_success(self):
        assert self.stub.execute(action="extract_text").startswith("Success")

    def test_screenshot_returns_success(self):
        assert self.stub.execute(action="capture_screenshot").startswith("Success")

    def test_close_returns_success(self):
        assert self.stub.execute(action="close_browser").startswith("Success")

    def test_unknown_action_returns_success(self):
        assert self.stub.execute(action="unknown_action").startswith("Success")
