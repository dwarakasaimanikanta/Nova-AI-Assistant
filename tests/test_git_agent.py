"""
tests/test_git_agent.py
-----------------------
Comprehensive unit tests for the GitAgent subsystem.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.git_agent import GitAgent, GitResult


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestGitAgent:
    @patch("subprocess.run")
    def test_git_init_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Initialized empty Git repository in /mock"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        agent = GitAgent(workspace_root=Path("/mock"))
        res = agent.execute("git init my project")

        assert res.success is True
        assert res.action == "init"
        assert "Initialized" in res.stdout
        mock_run.assert_called_once_with(
            ["git", "init"],
            cwd=str(Path("/mock")),
            stdout=-1,
            stderr=-1,
            text=True,
            timeout=30.0
        )

    @patch("subprocess.run")
    def test_git_commit_custom_message(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "[main abc123f] custom commit message"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        agent = GitAgent()
        res = agent.execute("commit my project with message 'refactor registry'")

        assert res.success is True
        assert res.action == "commit"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "commit", "-m", "refactor registry"]

    @patch("subprocess.run")
    def test_git_clone_url_parsing(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Cloning into 'nova'..."
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        agent = GitAgent()
        res = agent.execute("clone https://github.com/nova-ai/nova.git repository")

        assert res.success is True
        assert res.action == "clone"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "clone", "https://github.com/nova-ai/nova.git"]

    def test_git_clone_missing_url_returns_failure(self):
        agent = GitAgent()
        res = agent.execute("clone repository")
        assert res.success is False
        assert "No repository URL" in res.stderr

    @patch("subprocess.run")
    def test_git_checkout_branch(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Switched to branch 'feature/git'"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        agent = GitAgent()
        res = agent.execute("checkout feature/git")

        assert res.success is True
        assert res.action == "checkout"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "checkout", "feature/git"]

    @patch("subprocess.run")
    def test_git_failure_handling(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "fatal: not a git repository"
        mock_run.return_value = mock_proc

        agent = GitAgent()
        res = agent.execute("git status")

        assert res.success is False
        assert res.exit_code == 1
        assert "not a git repository" in res.stderr
