"""
tests/test_autonomous_coder.py
------------------------------
Comprehensive unit and integration tests for the Autonomous Coding Workflow.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.autonomous_coder import AutonomousCoder, CoderExecutionReport
from agents.coding_agent import CodingResult, CodingStatus, ProjectType


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_coding_agent():
    ca = MagicMock()
    # Default success response
    res = CodingResult(
        task_id="coding_t",
        status=CodingStatus.SUCCESS,
        project_type=ProjectType.PYTHON,
        root_dir=Path("mock_proj")
    )
    ca.execute.return_value = res
    return ca


@pytest.fixture
def mock_workspace_agent():
    return MagicMock()


@pytest.fixture
def mock_browser_agent():
    return MagicMock()


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestAutonomousCoder:
    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_workflow_success_opens_preview(
        self, mock_sleep, mock_popen_cls, mock_coding_agent, mock_workspace_agent, mock_browser_agent
    ):
        # Mock successful subprocess run (exited None meaning running, or exited 0)
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # stays running
        mock_popen_cls.return_value = mock_proc

        coder = AutonomousCoder(
            coding_agent=mock_coding_agent,
            workspace_agent=mock_workspace_agent,
            browser_agent=mock_browser_agent,
            max_retries=1
        )

        report = coder.execute_workflow("Create a python script")

        assert report.success is True
        assert report.retries_attempted == 0
        mock_coding_agent.execute.assert_called_once_with("Create a python script")
        # Verify BrowserAgent opened the preview (it defaults to mock entry main.py path)
        mock_browser_agent.execute.assert_called_once()

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_workflow_crashes_and_triggers_healing_retries(
        self, mock_sleep, mock_popen_cls, mock_coding_agent, mock_workspace_agent, mock_browser_agent
    ):
        # Mock crashed subprocess on first run (exit code 1), then stays running on second run
        proc1 = MagicMock()
        proc1.poll.return_value = 1
        proc1.communicate.return_value = ("stdout data", "Traceback error: division by zero")

        proc2 = MagicMock()
        proc2.poll.return_value = None  # stays running on retry

        mock_popen_cls.side_effect = [proc1, proc2]

        coder = AutonomousCoder(
            coding_agent=mock_coding_agent,
            workspace_agent=mock_workspace_agent,
            browser_agent=mock_browser_agent,
            max_retries=2
        )

        report = coder.execute_workflow("Create a python script")

        assert report.success is True
        assert report.retries_attempted == 1
        # CodingAgent should have been called twice: 1 for generate, 1 for patch fix
        assert len(mock_coding_agent.execute.call_args_list) == 2
        patch_call = mock_coding_agent.execute.call_args_list[1][0][0]
        assert "division by zero" in patch_call

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_workflow_fails_permanently_after_max_retries(
        self, mock_sleep, mock_popen_cls, mock_coding_agent, mock_workspace_agent, mock_browser_agent
    ):
        # Always crashed
        proc = MagicMock()
        proc.poll.return_value = 1
        proc.communicate.return_value = ("", "Compile error")
        mock_popen_cls.return_value = proc

        coder = AutonomousCoder(
            coding_agent=mock_coding_agent,
            workspace_agent=mock_workspace_agent,
            browser_agent=mock_browser_agent,
            max_retries=2
        )

        report = coder.execute_workflow("Create a python script")

        assert report.success is False
        assert report.retries_attempted == 3  # Initial + 2 retries
        assert len(report.errors) > 0
