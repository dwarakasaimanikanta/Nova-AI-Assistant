"""
core/execution_pipeline.py
--------------------------
Executive Integration Pipeline orchestrating ConversationEngine voice queries,
ExecutiveAgent, PlannerAgent, AgentRegistry resolution, and MemoryAgent logging.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Generator, Optional

from core.executive_agent import IntentType, TaskType, ExecutionStatus
from utils.logger import get_logger

logger = get_logger(__name__)


class ExecutionPipeline:
    """Unifies and coordinates the execution loop of Nova's sub-agent collective."""

    def __init__(
        self,
        executive_agent: Any,
        agent_registry: Any,
        planner_agent: Optional[Any] = None,
        memory_agent: Optional[Any] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.executive_agent = executive_agent
        self.agent_registry = agent_registry
        self.planner_agent = planner_agent
        self.memory_agent = memory_agent
        self.progress_callback = progress_callback
        self._lock = threading.Lock()

        # Connect step-level callbacks to stream progress updates
        self._register_callbacks()

    def execute(self, request_text: str) -> str:
        """
        Routes the user request, resolves specialized sub-agents,
        invokes planners if required, and records task statistics in MemoryAgent.
        """
        with self._lock:
            logger.info("[ExecutionPipeline] Processing request: %r", request_text)
            self._notify_progress("Analyzing user request...")

            # 1. Determine classification and intents
            intent = self.executive_agent.intent_analyzer.analyze(request_text)
            task_type = self.executive_agent.task_classifier.classify(request_text, intent)

            # Ensure default engine is set on registry if missing
            if hasattr(self.agent_registry, "set_engine") and not self.agent_registry.get_engine():
                self.agent_registry.set_engine(self.executive_agent.engine)

            response = ""
            status_str = "FAILED"

            # 2. Use PlannerAgent if multi-step goal planning is required
            if task_type == TaskType.PLANNING and self.planner_agent is not None:
                self._notify_progress("Complex plan detected. Activating PlannerAgent...")
                try:
                    from agents.planner_agent import PlannerState
                    res = self.planner_agent.execute(request_text)
                    response = res.final_summary or res.summary()
                    status_str = "SUCCESS" if res.status == PlannerState.SUCCESS else "FAILED"
                except Exception as plan_err:
                    logger.error("PlannerAgent raised an error: %s", plan_err)
                    response = f"Planning failed: {plan_err}"
            else:
                # 3. Route standard queries via ExecutiveAgent
                self._notify_progress("Routing command to ExecutiveAgent...")
                try:
                    res = self.executive_agent.execute(request_text)
                    response = res.final_response
                    status_str = "SUCCESS" if res.status == ExecutionStatus.SUCCESS else "FAILED"
                except Exception as exec_err:
                    logger.error("ExecutiveAgent raised an error: %s", exec_err)
                    response = f"Execution failed: {exec_err}"

            # 4. Update MemoryAgent with task outcomes
            if self.memory_agent:
                try:
                    self.memory_agent.remember(
                        category="short_term",
                        key="last_execution_status",
                        value=status_str
                    )
                    self.memory_agent.remember(
                        category="short_term",
                        key="last_execution_result",
                        value=response
                    )
                except Exception as mem_err:
                    logger.debug("Failed logging execution outcome to memory: %s", mem_err)

            self._notify_progress(f"Execution finished with status: {status_str}")
            return response

    def handle_input(self, user_input: str, stream: bool = False) -> str | Generator:
        """Compatibility shim to allow ConversationEngine to steam chunk responses."""
        final_output = self.execute(user_input)
        if stream:
            def _gen():
                yield final_output
            return _gen()
        return final_output

    # ── Internal ───────────────────────────────────────────────────────────

    def _register_callbacks(self) -> None:
        """Link internal agent callbacks to progress updates."""
        def on_step_change(step: Any) -> None:
            status_val = getattr(step.status, "value", str(step.status))
            desc = getattr(step, "description", "")
            self._notify_progress(f"Step '{desc}' status changed to: {status_val}")

        # Hook ExecutiveAgent StepExecutor
        if hasattr(self.executive_agent, "step_executor"):
            self.executive_agent.step_executor.progress_callback = on_step_change

        # Hook PlannerAgent
        if self.planner_agent:
            self.planner_agent.progress_callback = on_step_change

    def _notify_progress(self, message: str) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception as cb_err:
                logger.error("Progress callback failed: %s", cb_err)
