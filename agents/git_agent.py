"""
agents/git_agent.py
-------------------
GitAgent executing native git CLI commands through subprocess execution.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GitResult:
    """Detailed outcome statistics of a Git invocation."""
    success: bool
    action: str
    stdout: str
    stderr: str
    exit_code: int
    duration: float


# ─────────────────────────────────────────────────────────────────────────────
# Git Agent
# ─────────────────────────────────────────────────────────────────────────────

class GitAgent:
    """Autonomous Git operator wrapping the host's native git command line interface."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = workspace_root or Path.cwd()

    def execute(self, request: str) -> GitResult:
        """Parses git intent, runs subprocess command, and captures execution metrics."""
        started = time.time()
        lower = request.lower()
        cwd = self.workspace_root

        cmd = []
        action = "unknown"

        # Match Git operations
        if "init" in lower:
            cmd = ["git", "init"]
            action = "init"
        elif "status" in lower:
            cmd = ["git", "status"]
            action = "status"
        elif "add" in lower:
            # Determine path to add (default to all)
            path = "."
            match = re.search(r"add\s+([^\s'\"]+)", request, re.IGNORECASE)
            if match:
                path = match.group(1)
            cmd = ["git", "add", path]
            action = "add"
        elif "commit" in lower:
            msg = "Update codebase"
            match = re.search(r"(?:message|commit)\s+['\"]([^'\"]+)['\"]", request, re.IGNORECASE)
            if match:
                msg = match.group(1)
            cmd = ["git", "commit", "-m", msg]
            action = "commit"
        elif "push" in lower:
            cmd = ["git", "push"]
            action = "push"
        elif "pull" in lower:
            cmd = ["git", "pull"]
            action = "pull"
        elif "clone" in lower:
            url_match = re.search(r"https?://[^\s]+|git@[^\s]+", request)
            if not url_match:
                duration = time.time() - started
                return GitResult(False, "clone", "", "No repository URL specified to clone.", -1, duration)
            url = url_match.group(0).rstrip(".,;\"'")
            cmd = ["git", "clone", url]
            action = "clone"
        elif "checkout" in lower or "switch branch" in lower:
            branch = "main"
            words = request.split()
            # Find the word immediately following 'checkout' if present, or fallback to the last word
            if "checkout" in words:
                idx = words.index("checkout")
                if idx + 1 < len(words):
                    branch = words[idx + 1].strip("'\"")
            elif len(words) >= 2:
                branch = words[-1].strip("'\"")
            cmd = ["git", "checkout", branch]
            action = "checkout"
        elif "branch" in lower or "create new branch" in lower:
            branch = None
            words = request.split()
            # If a name is passed, create the branch
            if len(words) >= 3:
                branch = words[-1].strip("'\"")
                cmd = ["git", "branch", branch]
                action = "branch_create"
            else:
                cmd = ["git", "branch"]
                action = "branch_list"
        else:
            duration = time.time() - started
            return GitResult(False, "unknown", "", f"Unsupported Git action: {request}", -1, duration)

        try:
            logger.info("Executing git command: %s in directory: %s", cmd, cwd)
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30.0
            )
            duration = time.time() - started
            return GitResult(
                success=(proc.returncode == 0),
                action=action,
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                duration=duration
            )
        except Exception as e:
            logger.error("Git execution failed: %s", e)
            duration = time.time() - started
            return GitResult(
                success=False,
                action=action,
                stdout="",
                stderr=str(e),
                exit_code=-2,
                duration=duration
            )
