"""
agents/planner_agent.py
-----------------------
PlannerAgent is Nova's autonomous reasoning engine.

It breaks down complex goals into a dependency graph of executable tasks,
routes tasks to the appropriate specialized sub-agents (Coding, Browser,
Android, Workspace, or legacy Engine), and coordinates sequential execution
with retry and cancellation policies.

Architecture
------------
PlannerAgent wraps and coordinates sub-agents programmatically:

              Goal Request
                   ↓
        ExecutiveAgent (monkey-patched routing)
                   ↓
          PlannerAgent.execute()
                   ↓
             GoalDecomposer
                   ↓
     ExecutionGraph (topological sort)
                   ↓
            Task Execution Loop  →  Sub-Agents (Coding/Browser/Android/Workspace/Engine)
                   ↓
             PlannerResult
"""

from __future__ import annotations

import collections
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class PlannerState(str, Enum):
    IDLE      = "IDLE"
    PLANNING  = "PLANNING"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    SKIPPED   = "SKIPPED"
    CANCELLED = "CANCELLED"


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExecutionTask:
    """A single node in the ExecutionGraph representing a sub-goal."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    instruction: str = ""
    assigned_agent: str = "engine"  # "coding", "browser", "android", "workspace", "engine"
    status: TaskStatus = TaskStatus.PENDING
    dependencies: Set[str] = field(default_factory=set)  # IDs of tasks that must run first
    max_retries: int = 2
    retry_count: int = 0
    output: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None


@dataclass
class ExecutionGraph:
    """A Directed Acyclic Graph (DAG) of ExecutionTasks."""
    tasks: Dict[str, ExecutionTask] = field(default_factory=dict)

    def add_task(self, task: ExecutionTask) -> None:
        self.tasks[task.task_id] = task

    def add_dependency(self, task_id: str, depends_on_id: str) -> None:
        if task_id in self.tasks and depends_on_id in self.tasks:
            self.tasks[task_id].dependencies.add(depends_on_id)

    def get_topological_order(self) -> List[str]:
        """Resolves task dependencies and returns a list of task_ids in runnable order."""
        in_degree = {tid: 0 for tid in self.tasks}
        adj = collections.defaultdict(list)

        for tid, task in self.tasks.items():
            for dep in task.dependencies:
                adj[dep].append(tid)
                in_degree[tid] += 1

        queue = [tid for tid, degree in in_degree.items() if degree == 0]
        order = []

        while queue:
            # Maintain deterministic ordering by sorting / stable queue
            queue.sort()
            curr = queue.pop(0)
            order.append(curr)

            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.tasks):
            raise ValueError("Dependency cycle detected in ExecutionGraph.")

        return order


@dataclass
class ExecutionPlan:
    """The planning structure consisting of the target goal and its dependency graph."""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = ""
    graph: ExecutionGraph = field(default_factory=ExecutionGraph)
    created_at: float = field(default_factory=time.time)


@dataclass
class PlannerResult:
    """Structured result returned by PlannerAgent after execution."""
    plan_id: str
    goal: str
    status: PlannerState
    tasks_executed: int
    tasks_succeeded: int
    tasks_failed: int
    total_duration: float
    final_summary: str
    task_results: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[PlannerAgent] Plan {self.plan_id} | {self.status} | "
            f"Tasks {self.tasks_succeeded}/{self.tasks_executed} succeeded | "
            f"{self.total_duration:.2f}s"
        )

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "status": str(self.status),
            "tasks_executed": self.tasks_executed,
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "total_duration": self.total_duration,
            "final_summary": self.final_summary,
            "errors": self.errors,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Goal Decomposer
# ─────────────────────────────────────────────────────────────────────────────

class GoalDecomposer:
    """
    Decomposes a high-level natural language goal into structured ExecutionTasks.
    Identifies target sub-agents based on instruction keywords.
    """

    def decompose(self, goal: str) -> ExecutionPlan:
        plan = ExecutionPlan(goal=goal)
        lines = [line.strip() for line in goal.splitlines() if line.strip()]

        # Check if the goal has numbered / bulleted steps
        step_descriptions = []
        for line in lines:
            # Match "1. do x", "- do y", "Step 1: do z"
            m = re.match(r"^(?:\d+\.|\*|\-|step\s+\d+:?)\s+(.*)$", line, re.IGNORECASE)
            if m:
                step_descriptions.append(m.group(1).strip())

        if not step_descriptions:
            # Fall back to splitting by sequence connectors like "and then", "after that"
            connectors = ["and then", "followed by", "after that", "next"]
            pattern = r"\s*(?:" + "|".join(re.escape(c) for c in connectors) + r")\s*"
            parts = re.split(pattern, goal, flags=re.IGNORECASE)
            step_descriptions = [p.strip() for p in parts if p.strip()]

        if not step_descriptions:
            # Fall back to single step
            step_descriptions = [goal]

        prev_task_id = None
        for idx, desc in enumerate(step_descriptions):
            agent = self._select_agent(desc)
            task = ExecutionTask(
                description=f"Task {idx + 1}: {desc[:60]}",
                instruction=desc,
                assigned_agent=agent,
            )
            if prev_task_id:
                task.dependencies.add(prev_task_id)
            plan.graph.add_task(task)
            prev_task_id = task.task_id

        return plan

    def _select_agent(self, text: str) -> str:
        lower = text.lower()

        # Coding keywords
        coding_keywords = ("create python", "write script", "write code", "generate flask", "fastapi app")
        if any(k in lower for k in coding_keywords):
            return "coding"

        # Browser keywords
        browser_keywords = ("open url", "search google", "browse website", "take screenshot of web")
        if any(k in lower for k in browser_keywords):
            return "browser"

        # Android keywords
        android_keywords = ("call contact", "send sms", "send whatsapp", "open app on phone")
        if any(k in lower for k in android_keywords):
            return "android"

        # Workspace keywords
        workspace_keywords = ("create folder", "create file", "write to file", "read file", "zip folder", "unzip archive")
        if any(k in lower for k in workspace_keywords):
            return "workspace"

        # Check intent analyzer keywords as fallback
        from core.executive_agent import IntentAnalyzer, IntentType
        analyzer = IntentAnalyzer()
        intent = analyzer.analyze(text)
        if intent == IntentType.CREATION:
            return "coding"
        elif intent == IntentType.NAVIGATION:
            return "browser"
        elif intent == IntentType.COMMUNICATION:
            return "android"

        return "engine"


# ─────────────────────────────────────────────────────────────────────────────
# Planner Agent
# ─────────────────────────────────────────────────────────────────────────────

class PlannerAgent:
    """
    PlannerAgent coordinates the decomposition and sequential execution of tasks.
    """

    def __init__(
        self,
        engine: Any,
        coding_agent: Optional[Any] = None,
        browser_agent: Optional[Any] = None,
        android_agent: Optional[Any] = None,
        workspace_agent: Optional[Any] = None,
        progress_callback: Optional[Callable[[ExecutionTask], None]] = None,
    ) -> None:
        self.engine            = engine
        self.coding_agent      = coding_agent
        self.browser_agent     = browser_agent
        self.android_agent     = android_agent
        self.workspace_agent   = workspace_agent
        self.progress_callback = progress_callback

        self.decomposer        = GoalDecomposer()
        self.state             = PlannerState.IDLE
        self._cancel_event     = threading.Event()
        self._lock             = threading.Lock()

        logger.info("[PlannerAgent] Initialized.")

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(self, goal: str) -> PlannerResult:
        with self._lock:
            self._cancel_event.clear()
            self.state = PlannerState.PLANNING
            started = time.time()

            logger.info("[PlannerAgent] Planning goal: %r", goal)
            plan = self.decomposer.decompose(goal)
            self.state = PlannerState.RUNNING

            try:
                order = plan.graph.get_topological_order()
            except ValueError as val_err:
                duration = time.time() - started
                self.state = PlannerState.FAILED
                return PlannerResult(
                    plan_id=plan.plan_id, goal=goal, status=self.state,
                    tasks_executed=0, tasks_succeeded=0, tasks_failed=0,
                    total_duration=duration, final_summary="Dependency cycle detected.",
                    errors=[str(val_err)]
                )

            succeeded_count = 0
            failed_count = 0
            cancelled_count = 0

            for tid in order:
                task = plan.graph.tasks[tid]

                if self._cancel_event.is_set():
                    task.status = TaskStatus.CANCELLED
                    task.output = "Cancelled by planner coordinator."
                    cancelled_count += 1
                    self._notify(task)
                    continue

                # Verify if dependencies succeeded
                skipped_dep = False
                for dep_id in task.dependencies:
                    dep_task = plan.graph.tasks[dep_id]
                    if dep_task.status != TaskStatus.SUCCESS:
                        skipped_dep = True
                        break

                if skipped_dep:
                    task.status = TaskStatus.SKIPPED
                    task.output = "Skipped: dependent task failed."
                    failed_count += 1
                    self._notify(task)
                    continue

                # Run task with retry
                self._run_task_with_retry(task)

                if task.status == TaskStatus.SUCCESS:
                    succeeded_count += 1
                else:
                    failed_count += 1

            duration = time.time() - started
            if self._cancel_event.is_set() or cancelled_count > 0:
                self.state = PlannerState.CANCELLED
            elif failed_count > 0:
                self.state = PlannerState.FAILED
            else:
                self.state = PlannerState.SUCCESS

            # Compile results
            task_results = []
            errors = []
            final_parts = []
            for tid in order:
                t = plan.graph.tasks[tid]
                task_results.append({
                    "task_id": t.task_id,
                    "description": t.description,
                    "status": str(t.status),
                    "output": t.output,
                    "duration": t.duration,
                })
                if t.error:
                    errors.append(f"[{t.assigned_agent}] {t.error}")
                if t.output:
                    final_parts.append(f"{t.description}: {t.output}")

            final_summary = "\n".join(final_parts) if final_parts else "No tasks successfully produced output."

            result = PlannerResult(
                plan_id=plan.plan_id,
                goal=goal,
                status=self.state,
                tasks_executed=len(order),
                tasks_succeeded=succeeded_count,
                tasks_failed=failed_count,
                total_duration=duration,
                final_summary=final_summary,
                task_results=task_results,
                errors=errors,
            )
            logger.info("[PlannerAgent] %s", result.summary())
            return result

    def cancel(self) -> None:
        self._cancel_event.set()
        logger.info("[PlannerAgent] Cancellation signal sent.")

    def handle_input(self, user_input: str, stream: bool = False):
        result = self.execute(user_input)
        response = result.final_summary or result.summary()
        if stream:
            def _gen():
                yield response
            return _gen()
        return response

    # ── Internal ───────────────────────────────────────────────────────────

    def _run_task_with_retry(self, task: ExecutionTask) -> None:
        attempt = 0
        while attempt <= task.max_retries:
            if self._cancel_event.is_set():
                task.status = TaskStatus.CANCELLED
                task.output = "Cancelled by user."
                self._notify(task)
                return

            attempt += 1
            task.started_at = time.time()
            task.status = TaskStatus.RUNNING
            self._notify(task)

            try:
                output = self._dispatch_agent(task.assigned_agent, task.instruction)
                task.output = output
                task.status = TaskStatus.SUCCESS
                task.finished_at = time.time()
                self._notify(task)
                return

            except Exception as e:
                task.error = str(e)
                task.retry_count = attempt
                logger.warning(
                    "[PlannerAgent] Task '%s' attempt %d/%d failed: %s",
                    task.description, attempt, task.max_retries + 1, e
                )
                if attempt > task.max_retries:
                    task.status = TaskStatus.FAILED
                    task.finished_at = time.time()
                    task.output = f"Failure: {e}"
                    self._notify(task)
                    return
                time.sleep(0.3 * attempt)

    def _dispatch_agent(self, agent_name: str, instruction: str) -> str:
        if agent_name == "coding" and self.coding_agent is not None:
            res = self.coding_agent.execute(instruction)
            if res.status != "SUCCESS":
                raise RuntimeError(f"CodingAgent failed: {res.errors}")
            return res.summary()

        elif agent_name == "browser" and self.browser_agent is not None:
            res = self.browser_agent.execute(instruction)
            if res.status != "SUCCESS":
                raise RuntimeError(f"BrowserAgent failed: {res.errors}")
            return res.final_output or res.summary()

        elif agent_name == "android" and self.android_agent is not None:
            res = self.android_agent.execute(instruction)
            if res.status != "SUCCESS":
                raise RuntimeError(f"AndroidAgent failed: {res.errors}")
            return res.final_output or res.summary()

        elif agent_name == "workspace" and self.workspace_agent is not None:
            res = self.workspace_agent.execute(instruction)
            if res.status != "SUCCESS":
                raise RuntimeError(f"WorkspaceAgent failed: {res.errors}")
            return res.final_output or res.summary()

        else:
            # Default fallback to engine
            res = self.engine.handle_input(instruction, stream=False)
            if hasattr(res, "__iter__") and not isinstance(res, str):
                res = "".join(res)
            return res

    def _notify(self, task: ExecutionTask) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(task)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Runtime Injection into ExecutiveAgent & StepExecutor (Monkey Patch)
# ─────────────────────────────────────────────────────────────────────────────

def _inject_planner_routing() -> None:
    """
    Dynamically patches StepExecutor and ExecutiveAgent classes so that
    if a PlannerAgent instance is injected, it routes goals/planning requests to it.
    """
    from core.executive_agent import StepExecutor, ExecutiveAgent, IntentType, ExecutionStatus

    # 1. Modify StepExecutor.__init__ to accept and store planner_agent
    orig_step_init = StepExecutor.__init__

    def patched_step_init(self, *args, **kwargs):
        self.planner_agent = kwargs.pop("planner_agent", None)
        orig_step_init(self, *args, **kwargs)

    StepExecutor.__init__ = patched_step_init

    # 2. Modify StepExecutor.execute to route Planner actions dynamically
    orig_step_execute = StepExecutor.execute

    def patched_step_execute(self, step, cancel_event=None):
        if getattr(self, "planner_agent", None) is not None:
            lower = step.input_data.lower()
            # Match common multi-step goal request patterns
            is_goal = False
            goal_keywords = (
                "plan to", "goal:", "solve goal", "steps to solve",
                "complex plan", "first do", "composite task"
            )
            if any(kw in lower for kw in goal_keywords) or "\n" in lower:
                is_goal = True

            if is_goal:
                try:
                    result = self.planner_agent.execute(step.input_data)
                    if result.status == PlannerState.SUCCESS:
                        step.output_data = result.final_summary
                        step.status = ExecutionStatus.SUCCESS
                        step.finished_at = time.time()
                        self._report(step)
                        return result.final_summary
                    else:
                        logger.warning("[ExecutiveAgent] PlannerAgent failed. Falling back to NovaEngine.")
                except Exception as e:
                    logger.exception("[ExecutiveAgent] Exception in PlannerAgent. Falling back to NovaEngine: %s", e)

        return orig_step_execute(self, step, cancel_event)

    StepExecutor.execute = patched_step_execute

    # 3. Modify ExecutiveAgent.__init__ to accept planner_agent
    orig_exec_init = ExecutiveAgent.__init__

    def patched_exec_init(self, *args, **kwargs):
        planner_agent = kwargs.pop("planner_agent", None)
        orig_exec_init(self, *args, **kwargs)
        self.step_executor.planner_agent = planner_agent

    ExecutiveAgent.__init__ = patched_exec_init


import re
try:
    _inject_planner_routing()
    logger.info("[PlannerAgent] Successfully injected planner routing into ExecutiveAgent.")
except Exception as injection_err:
    logger.error("[PlannerAgent] Failed to inject planner routing: %s", injection_err)
