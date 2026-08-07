"""
tests/test_workspace_agent.py
------------------------------
Comprehensive unit and integration tests for the WorkspaceAgent pipeline
and its dynamic routing integration within the ExecutiveAgent.
"""

import os
import shutil
import zipfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.workspace_agent import (
    ActionRunner,
    ResultBuilder,
    WorkspaceAction,
    WorkspaceAgent,
    WorkspacePlanner,
    WorkspaceResult,
    WorkspaceStatus,
    WorkspaceStep,
    WorkspaceTask,
)
from core.executive_agent import ExecutiveAgent, ExecutionStatus


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def agent(tmp_workspace):
    return WorkspaceAgent(workspace_root=tmp_workspace, max_step_retries=1)


# ─────────────────────────────────────────────────────────────────────────────
# Core Step & Task Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkspaceCore:
    def test_step_duration(self):
        step = WorkspaceStep(action=WorkspaceAction.CREATE_FILE)
        assert step.duration is None
        step.started_at = 10.0
        step.finished_at = 10.5
        assert step.duration == pytest.approx(0.5)
        assert step.succeeded() is False
        step.status = WorkspaceStatus.SUCCESS
        assert step.succeeded() is True

    def test_task_add_step(self):
        task = WorkspaceTask(description="create structure")
        step = task.add_step(WorkspaceAction.CREATE_FOLDER, "mkdir test", path="test")
        assert len(task.steps) == 1
        assert step.action == WorkspaceAction.CREATE_FOLDER
        assert step.params == {"path": "test"}


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Planner Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkspacePlanner:
    def setup_method(self):
        self.planner = WorkspacePlanner()

    def test_project_rules(self):
        t1 = self.planner.plan("create project 'nova'")
        assert t1.steps[0].action == WorkspaceAction.CREATE_PROJECT
        assert t1.steps[0].params["project_name"] == "nova"

        t2 = self.planner.plan("open project 'my_proj'")
        assert t2.steps[0].action == WorkspaceAction.OPEN_PROJECT

        t3 = self.planner.plan("delete project 'my_proj'")
        assert t3.steps[0].action == WorkspaceAction.DELETE_PROJECT

        t4 = self.planner.plan("archive project 'my_proj'")
        assert t4.steps[0].action == WorkspaceAction.ARCHIVE_PROJECT

    def test_folder_rules(self):
        t1 = self.planner.plan("create folder 'docs'")
        assert t1.steps[0].action == WorkspaceAction.CREATE_FOLDER
        assert t1.steps[0].params["path"] == "docs"

        t2 = self.planner.plan("rename folder 'docs' to 'documentation'")
        assert t2.steps[0].action == WorkspaceAction.RENAME_FOLDER
        assert t2.steps[0].params["src"] == "docs"
        assert t2.steps[0].params["dest"] == "documentation"

        t3 = self.planner.plan("delete folder 'docs'")
        assert t3.steps[0].action == WorkspaceAction.DELETE_FOLDER

    def test_file_rules(self):
        t1 = self.planner.plan("create file 'app.py'")
        assert t1.steps[0].action == WorkspaceAction.CREATE_FILE

        t2 = self.planner.plan("read file 'app.py'")
        assert t2.steps[0].action == WorkspaceAction.READ_FILE

        t3 = self.planner.plan("write to file 'app.py' content 'print(1)'")
        assert t3.steps[0].action == WorkspaceAction.WRITE_FILE
        assert t3.steps[0].params["content"] == "print(1)"

        t4 = self.planner.plan("append file 'log.txt' content 'done'")
        assert t4.steps[0].action == WorkspaceAction.APPEND_FILE
        assert t4.steps[0].params["content"] == "done"

        t5 = self.planner.plan("copy file 'a.py' to 'b.py'")
        assert t5.steps[0].action == WorkspaceAction.COPY_FILE

    def test_workspace_operations(self):
        t1 = self.planner.plan("search workspace for 'logger'")
        assert t1.steps[0].action == WorkspaceAction.SEARCH
        assert t1.steps[0].params["query"] == "logger"

        t2 = self.planner.plan("list files")
        assert t2.steps[0].action == WorkspaceAction.LIST_DIR

        t3 = self.planner.plan("zip 'docs' to 'docs.zip'")
        assert t3.steps[0].action == WorkspaceAction.ZIP

        t4 = self.planner.plan("unzip 'docs.zip' to 'docs'")
        assert t4.steps[0].action == WorkspaceAction.UNZIP

    def test_dev_utilities(self):
        t1 = self.planner.plan("open vs code in 'project'")
        assert t1.steps[0].action == WorkspaceAction.OPEN_VS_CODE

        t2 = self.planner.plan("open terminal")
        assert t2.steps[0].action == WorkspaceAction.OPEN_TERMINAL

        t3 = self.planner.plan("open explorer")
        assert t3.steps[0].action == WorkspaceAction.OPEN_EXPLORER


# ─────────────────────────────────────────────────────────────────────────────
# Action Runner Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestActionRunner:
    def test_project_operations(self, tmp_workspace):
        runner = ActionRunner(tmp_workspace)
        # Create Project
        s1 = WorkspaceStep(action=WorkspaceAction.CREATE_PROJECT, params={"project_name": "p1"})
        runner.run(s1)
        assert s1.status == WorkspaceStatus.SUCCESS
        assert (tmp_workspace / "p1" / "README.md").exists()

        # Open Project
        s2 = WorkspaceStep(action=WorkspaceAction.OPEN_PROJECT, params={"project_name": "p1"})
        runner.run(s2)
        assert s2.status == WorkspaceStatus.SUCCESS

        # Archive Project
        s3 = WorkspaceStep(action=WorkspaceAction.ARCHIVE_PROJECT, params={"project_name": "p1"})
        runner.run(s3)
        assert s3.status == WorkspaceStatus.SUCCESS
        assert (tmp_workspace / "p1_archive.zip").exists()

        # Delete Project
        s4 = WorkspaceStep(action=WorkspaceAction.DELETE_PROJECT, params={"project_name": "p1"})
        runner.run(s4)
        assert s4.status == WorkspaceStatus.SUCCESS
        assert not (tmp_workspace / "p1").exists()

    def test_folder_and_file_operations(self, tmp_workspace):
        runner = ActionRunner(tmp_workspace)
        # Create folder
        s1 = WorkspaceStep(action=WorkspaceAction.CREATE_FOLDER, params={"path": "src"})
        runner.run(s1)
        assert (tmp_workspace / "src").is_dir()

        # Create file
        s2 = WorkspaceStep(action=WorkspaceAction.CREATE_FILE, params={"path": "src/main.py"})
        runner.run(s2)
        assert (tmp_workspace / "src/main.py").is_file()

        # Write file
        s3 = WorkspaceStep(action=WorkspaceAction.WRITE_FILE, params={"path": "src/main.py", "content": "x = 42"})
        runner.run(s3)
        assert (tmp_workspace / "src/main.py").read_text(encoding="utf-8") == "x = 42"

        # Append file
        s4 = WorkspaceStep(action=WorkspaceAction.APPEND_FILE, params={"path": "src/main.py", "content": "\ny = 10"})
        runner.run(s4)
        assert "y = 10" in (tmp_workspace / "src/main.py").read_text(encoding="utf-8")

        # Copy file
        s5 = WorkspaceStep(action=WorkspaceAction.COPY_FILE, params={"src": "src/main.py", "dest": "src/backup.py"})
        runner.run(s5)
        assert (tmp_workspace / "src/backup.py").is_file()

        # Move file
        s6 = WorkspaceStep(action=WorkspaceAction.MOVE_FILE, params={"src": "src/backup.py", "dest": "backup.py"})
        runner.run(s6)
        assert (tmp_workspace / "backup.py").is_file()
        assert not (tmp_workspace / "src/backup.py").exists()

    def test_zip_and_unzip(self, tmp_workspace):
        runner = ActionRunner(tmp_workspace)
        # Setup source
        (tmp_workspace / "data").mkdir()
        (tmp_workspace / "data" / "f.txt").write_text("hello", encoding="utf-8")

        # Zip
        s1 = WorkspaceStep(action=WorkspaceAction.ZIP, params={"src": "data", "dest": "data.zip"})
        runner.run(s1)
        assert (tmp_workspace / "data.zip").is_file()

        # Unzip
        s2 = WorkspaceStep(action=WorkspaceAction.UNZIP, params={"src": "data.zip", "dest": "extracted"})
        runner.run(s2)
        assert (tmp_workspace / "extracted" / "f.txt").read_text(encoding="utf-8") == "hello"

    def test_search_workspace(self, tmp_workspace):
        runner = ActionRunner(tmp_workspace)
        (tmp_workspace / "a.py").write_text("def run_system_check(): pass", encoding="utf-8")
        s1 = WorkspaceStep(action=WorkspaceAction.SEARCH, params={"query": "system_check"})
        runner.run(s1)
        assert "a.py" in s1.output

    def test_list_directory(self, tmp_workspace):
        runner = ActionRunner(tmp_workspace)
        (tmp_workspace / "item.txt").touch()
        s1 = WorkspaceStep(action=WorkspaceAction.LIST_DIR, params={"path": "."})
        runner.run(s1)
        assert "item.txt" in s1.output

    def test_launch_utilities(self, tmp_workspace):
        runner = ActionRunner(tmp_workspace)
        with patch("subprocess.Popen") as mock_popen:
            # VS Code
            s1 = WorkspaceStep(action=WorkspaceAction.OPEN_VS_CODE, params={"path": "."})
            runner.run(s1)
            mock_popen.assert_called_once()

            # Terminal
            mock_popen.reset_mock()
            s2 = WorkspaceStep(action=WorkspaceAction.OPEN_TERMINAL, params={"path": "."})
            runner.run(s2)
            mock_popen.assert_called_once()

            # Explorer
            mock_popen.reset_mock()
            s3 = WorkspaceStep(action=WorkspaceAction.OPEN_EXPLORER, params={"path": "."})
            runner.run(s3)
            mock_popen.assert_called_once()

    def test_retry_on_failure(self, tmp_workspace):
        calls = {"n": 0}
        class FailThenSuccessRunner(ActionRunner):
            def _execute_action(self, action, params):
                calls["n"] += 1
                if calls["n"] < 2:
                    raise IOError("Disk busy")
                return "Success: Written"

        runner = FailThenSuccessRunner(tmp_workspace)
        step = WorkspaceStep(action=WorkspaceAction.WRITE_FILE, params={"path": "a.txt"})
        runner.run(step)
        assert step.status == WorkspaceStatus.SUCCESS
        assert calls["n"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# WorkspaceAgent Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkspaceAgent:
    def test_execute_pipeline(self, agent, tmp_workspace):
        result = agent.execute("create folder 'test_dir'")
        assert result.status == WorkspaceStatus.SUCCESS
        assert (tmp_workspace / "test_dir").is_dir()

    def test_handle_input_shim(self, agent):
        res = agent.handle_input("create file 'readme.md'")
        assert "readme.md" in res

    def test_cancel_signal_respected(self, tmp_workspace):
        agent = WorkspaceAgent(workspace_root=tmp_workspace)
        
        def callback(step):
            if step.status == WorkspaceStatus.RUNNING:
                agent.cancel()
                
        agent.runner.progress_callback = callback
        
        task = WorkspaceTask()
        task.add_step(WorkspaceAction.CREATE_FILE, "create", path="cancel.txt")
        task.add_step(WorkspaceAction.CREATE_FILE, "create_second", path="cancel2.txt")
        
        result = agent.execute_task(task)
        assert result.status == WorkspaceStatus.CANCELLED



# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Injection Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutiveAgentIntegration:
    def test_routes_workspace_requests(self, tmp_workspace):
        engine = MagicMock()
        workspace_agent = WorkspaceAgent(workspace_root=tmp_workspace)
        
        # Inject workspace_agent via dependency injection
        exec_agent = ExecutiveAgent(engine=engine, workspace_agent=workspace_agent)
        
        # This input matches a workspace pattern
        result = exec_agent.execute("create file 'injected_readme.md'")
        
        # Should be processed successfully by WorkspaceAgent
        assert result.status == ExecutionStatus.SUCCESS
        assert (tmp_workspace / "injected_readme.md").is_file()
        
        # Verify NovaEngine was NOT invoked
        assert len(engine.handle_input.calls if hasattr(engine.handle_input, "calls") else []) == 0

    def test_fallback_on_workspace_failure(self, tmp_workspace):
        # We simulate a fail case by passing a directory path that cannot be written
        # (e.g. read-only path or empty directory name)
        engine = MagicMock()
        engine.handle_input.return_value = "Fallback Engine Output"
        
        workspace_agent = WorkspaceAgent(workspace_root=tmp_workspace)
        exec_agent = ExecutiveAgent(engine=engine, workspace_agent=workspace_agent)
        
        # Trigger write file step but fail it with incorrect args (or path)
        # to ensure it falls back to Engine
        with patch.object(ActionRunner, "_execute_action", side_effect=IOError("Write failed")):
            result = exec_agent.execute("write file 'failed.txt'")
            
            # Should fall back to legacy engine handle_input
            engine.handle_input.assert_called_once_with("write file 'failed.txt'", stream=False)
            assert result.final_response == "Fallback Engine Output"
