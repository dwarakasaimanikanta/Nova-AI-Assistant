"""
core/project_lifecycle.py
-------------------------
End-to-end Autonomous Project Lifecycle Manager coordinating goals,
planning, software generation, self-repair execution, and previewing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LifecycleReport:
    """End-to-end report containing planning, generation, and verification statistics."""
    success: bool
    plan_tasks: List[str]
    retries_attempted: int
    errors: List[str]
    preview_url: Optional[str]
    duration: float

    def summary(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"[ProjectLifecycle] {status} | Tasks: {len(plan_tasks)} | "
            f"Retries: {self.retries_attempted} | Preview: {self.preview_url} | "
            f"Duration: {self.duration:.2f}s"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Project Lifecycle Manager
# ─────────────────────────────────────────────────────────────────────────────

class ProjectLifecycle:
    """Orchestrates goal planning, code generation, execution monitoring, and browser preview."""

    def __init__(
        self,
        planner_agent: Any,
        autonomous_coder: Any,
        browser_agent: Any,
        memory_agent: Optional[Any] = None,
    ) -> None:
        self.planner_agent = planner_agent
        self.autonomous_coder = autonomous_coder
        self.browser_agent = browser_agent
        self.memory_agent = memory_agent

    def run(self, goal: str) -> LifecycleReport:
        """Runs the end-to-end software development project lifecycle."""
        started = time.time()
        errors = []
        plan_tasks = []

        logger.info("[ProjectLifecycle] Starting project lifecycle for goal: %r", goal)

        # 1. Request plan from PlannerAgent
        if self.planner_agent:
            try:
                plan_res = self.planner_agent.execute(goal)
                plan_tasks = [t.description for t in plan_res.tasks]
                logger.info("[ProjectLifecycle] Planner parsed %d tasks.", len(plan_tasks))
            except Exception as e:
                logger.error("[ProjectLifecycle] PlannerAgent failed: %s", e)
                errors.append(f"Planning step error: {e}")

        # 2. Scaffolding, execution, error collection and retries via AutonomousCoder
        coder_report = self.autonomous_coder.execute_workflow(goal)
        errors.extend(coder_report.errors)

        # 3. Save execution report in MemoryAgent
        if self.memory_agent:
            try:
                status_str = "SUCCESS" if coder_report.success else "FAILED"
                self.memory_agent.remember(
                    category="short_term",
                    key="last_lifecycle_status",
                    value=status_str
                )
                if coder_report.preview_url:
                    self.memory_agent.remember(
                        category="short_term",
                        key="last_project_url",
                        value=coder_report.preview_url
                    )
            except Exception as mem_err:
                logger.debug("Failed logging project lifecycle to MemoryAgent: %s", mem_err)

        duration = time.time() - started
        report = LifecycleReport(
            success=coder_report.success,
            plan_tasks=plan_tasks,
            retries_attempted=coder_report.retries_attempted,
            errors=errors,
            preview_url=coder_report.preview_url,
            duration=duration
        )
        logger.info("[ProjectLifecycle] Completed. Status: %s", "SUCCESS" if report.success else "FAILED")
        return report
