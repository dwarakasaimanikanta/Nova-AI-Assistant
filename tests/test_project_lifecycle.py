"""
tests/test_project_lifecycle.py
-------------------------------
Comprehensive unit and integration tests for the ProjectLifecycle manager.
"""

from unittest.mock import MagicMock

import pytest

from core.project_lifecycle import ProjectLifecycle


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_planner():
    pa = MagicMock()
    # Mock planning execution
    task1 = MagicMock()
    task1.description = "Design index.html structure"
    task2 = MagicMock()
    task2.description = "Implement uvicorn main app"
    
    res = MagicMock()
    res.tasks = [task1, task2]
    pa.execute.return_value = res
    return pa


@pytest.fixture
def mock_auton_coder():
    ac = MagicMock()
    
    # Mock coder execution report
    from agents.autonomous_coder import CoderExecutionReport
    report = CoderExecutionReport(
        task_id="lifecycle_task",
        success=True,
        project_type="python",
        root_dir="mock_dir",
        retries_attempted=1,
        errors=[],
        stdout="",
        stderr="",
        preview_url="http://localhost:5000"
    )
    ac.execute_workflow.return_value = report
    return ac


@pytest.fixture
def mock_browser():
    return MagicMock()


@pytest.fixture
def mock_memory():
    return MagicMock()


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectLifecycle:
    def test_lifecycle_success_path(
        self, mock_planner, mock_auton_coder, mock_browser, mock_memory
    ):
        lifecycle = ProjectLifecycle(
            planner_agent=mock_planner,
            autonomous_coder=mock_auton_coder,
            browser_agent=mock_browser,
            memory_agent=mock_memory
        )

        report = lifecycle.run("Build a portfolio web application")

        # Verify components execution
        mock_planner.execute.assert_called_once_with("Build a portfolio web application")
        mock_auton_coder.execute_workflow.assert_called_once_with("Build a portfolio web application")
        
        # Verify memory log calls
        mock_memory.remember.assert_any_call(
            category="short_term",
            key="last_lifecycle_status",
            value="SUCCESS"
        )
        mock_memory.remember.assert_any_call(
            category="short_term",
            key="last_project_url",
            value="http://localhost:5000"
        )

        # Verify report values
        assert report.success is True
        assert len(report.plan_tasks) == 2
        assert report.retries_attempted == 1
        assert report.preview_url == "http://localhost:5000"
        assert len(report.errors) == 0
