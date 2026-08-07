"""
agents/autonomous_coder.py
--------------------------
Autonomous Coder Workflow driving project generation, execution,
runtime monitoring, self-healing loop retries, and browser preview.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.coding_agent import CodingAgent, CodingStatus, ProjectType
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CoderExecutionReport:
    """Report containing detailed stats of the autonomous coding workflow execution."""
    task_id: str
    success: bool
    project_type: str
    root_dir: str
    retries_attempted: int
    errors: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    preview_url: Optional[str] = None
    duration: float = 0.0

    def summary(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"[AutonomousCoder] {status} | Type: {self.project_type} | "
            f"Retries: {self.retries_attempted} | Preview: {self.preview_url} | "
            f"Duration: {self.duration:.2f}s"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Autonomous Coder
# ─────────────────────────────────────────────────────────────────────────────

class AutonomousCoder:
    """Orchestrates project scaffolding, runtime verification, self-repair loops, and browser previewing."""

    def __init__(
        self,
        coding_agent: CodingAgent,
        workspace_agent: Any,
        browser_agent: Any,
        max_retries: int = 3,
    ) -> None:
        self.coding_agent = coding_agent
        self.workspace_agent = workspace_agent
        self.browser_agent = browser_agent
        self.max_retries = max_retries
        self._lock = threading.Lock()

    def execute_workflow(self, request: str) -> CoderExecutionReport:
        """
        Runs the full autonomous coding cycle:
        1. Generate codebase using CodingAgent.
        2. Run application/codebase and monitor.
        3. Catch runtime failures and send them back to CodingAgent for patches.
        4. Auto-retry code fixes.
        5. Trigger BrowserAgent for local preview verification on success.
        """
        started = time.time()
        task_id = str(uuid.uuid4())[:8] if "uuid" in sys.modules or True else "coder_task"
        import uuid
        task_id = str(uuid.uuid4())[:8]

        logger.info("[AutonomousCoder] Commencing workflow for request: %r", request)

        # ── 1. Codebase Generation ─────────────────────────────────────────
        coding_res = self.coding_agent.execute(request)
        if coding_res.status != CodingStatus.SUCCESS:
            duration = time.time() - started
            return CoderExecutionReport(
                task_id=task_id, success=False, project_type=coding_res.project_type.value,
                root_dir=str(coding_res.root_dir), retries_attempted=0,
                errors=coding_res.errors, duration=duration
            )

        root_dir = coding_res.root_dir
        project_type = coding_res.project_type
        logger.info("[AutonomousCoder] Scaffolding complete for type '%s' at '%s'.", project_type, root_dir)

        # ── 2. Run & Self-Healing Loop ─────────────────────────────────────
        retries = 0
        success = False
        last_stdout = ""
        last_stderr = ""
        errors = []
        app_proc: Optional[subprocess.Popen] = None
        http_proc: Optional[subprocess.Popen] = None
        preview_url = None

        while retries <= self.max_retries:
            # Shutdown previous processes if active
            self._shutdown_process(app_proc)
            self._shutdown_process(http_proc)
            app_proc = None
            http_proc = None

            # Launch process based on project type
            logger.info("[AutonomousCoder] Running project (Attempt %d/%d)...", retries + 1, self.max_retries + 1)
            app_proc, preview_url, run_err = self._launch_project(project_type, root_dir)

            if run_err:
                errors.append(f"Launch Error: {run_err}")
                last_stderr = run_err
                # Apply code patch
                patch_success = self._apply_healing_patch(request, root_dir, last_stderr)
                if not patch_success:
                    errors.append("CodingAgent failed to generate code repair patch.")
                retries += 1
                continue

            # Wait to monitor runtime errors
            time.sleep(2.0)
            
            # Check status
            exit_code = app_proc.poll()
            if exit_code is not None and exit_code != 0:
                # Capture logs
                stdout, stderr = app_proc.communicate()
                last_stdout = stdout or ""
                last_stderr = stderr or ""
                error_msg = last_stderr or last_stdout or f"Process exited with code {exit_code}"
                errors.append(f"Runtime Exit Code {exit_code}: {error_msg}")

                logger.warning("[AutonomousCoder] Application crashed on startup: %s", error_msg)
                
                # Apply code patch
                patch_success = self._apply_healing_patch(request, root_dir, last_stderr or error_msg)
                if not patch_success:
                    errors.append("CodingAgent failed to generate code repair patch.")
                retries += 1
                continue

            # Non-zero exit code check passed
            success = True
            break

        # ── 3. Browser Verification ────────────────────────────────────────
        if success and preview_url:
            # Handle static HTML files server start
            if project_type == ProjectType.HTML:
                http_proc, preview_url = self._start_static_server(root_dir)

            logger.info("[AutonomousCoder] Project running successfully. Opening preview: %s", preview_url)
            try:
                self.browser_agent.execute(f"Open {preview_url}")
            except Exception as e:
                logger.error("[AutonomousCoder] Failed triggering BrowserAgent preview: %s", e)

        # Cleanup running process after short delay (or keep running for user preview)
        # We keep them running but register exit handlers, or terminate if finishing
        # To make tests deterministic we terminate them upon exiting workflow:
        self._shutdown_process(app_proc)
        self._shutdown_process(http_proc)

        duration = time.time() - started
        report = CoderExecutionReport(
            task_id=task_id,
            success=success,
            project_type=project_type.value,
            root_dir=str(root_dir),
            retries_attempted=retries,
            errors=errors,
            stdout=last_stdout,
            stderr=last_stderr,
            preview_url=preview_url,
            duration=duration
        )
        logger.info("[AutonomousCoder] %s", report.summary())
        return report

    # ── Internal Helpers ───────────────────────────────────────────────────

    def _launch_project(self, proj_type: ProjectType, root: Path) -> tuple[Optional[subprocess.Popen], Optional[str], Optional[str]]:
        """Launch the project and determine its target preview url."""
        try:
            if proj_type in (ProjectType.PYTHON, ProjectType.FLASK):
                entry = root / "app.py" if (root / "app.py").exists() else root / "main.py"
                proc = subprocess.Popen(
                    [sys.executable, str(entry)],
                    cwd=str(root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                port = "5000" if proj_type == ProjectType.FLASK else None
                url = f"http://localhost:{port}" if port else None
                return proc, url, None

            elif proj_type == ProjectType.FASTAPI:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "main:app", "--port", "8000"],
                    cwd=str(root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return proc, "http://localhost:8000", None

            elif proj_type == ProjectType.HTML:
                # Return dummy process, server started in static server
                dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(100)"])
                return dummy, "http://localhost:8080", None

            elif proj_type == ProjectType.NODEJS:
                proc = subprocess.Popen(
                    ["node", "index.js"],
                    cwd=str(root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return proc, "http://localhost:3000", None

            else:
                raise ValueError(f"Unsupported project launch type: {proj_type}")
        except Exception as e:
            return None, None, str(e)

    def _start_static_server(self, root: Path) -> tuple[Optional[subprocess.Popen], str]:
        """Start a background Python HTTP server for static files."""
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "http.server", "8080"],
                cwd=str(root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return proc, "http://localhost:8080"
        except Exception as e:
            logger.error("Failed to start static http server: %s", e)
            return None, f"file:///{root.resolve()}/index.html"

    def _apply_healing_patch(self, request: str, root_dir: Path, error_msg: str) -> bool:
        """Invokes CodingAgent to correct code logic based on error feedback."""
        logger.info("[AutonomousCoder] Dispatching error feedback to CodingAgent...")
        prompt = (
            f"Fix code error in project directory '{root_dir}'.\n"
            f"Original Goal: {request}\n"
            f"Runtime Error Trace:\n{error_msg}"
        )
        res = self.coding_agent.execute(prompt)
        return res.status == CodingStatus.SUCCESS

    def _shutdown_process(self, proc: Optional[subprocess.Popen]) -> None:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
