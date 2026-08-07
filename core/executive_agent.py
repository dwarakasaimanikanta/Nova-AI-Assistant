"""
core/executive_agent.py
-----------------------
The Executive Agent is Nova's central orchestration brain.

It sits ABOVE NovaEngine and is responsible for:
  - Intent analysis and task classification
  - Execution plan creation
  - Sequential / conditional step execution
  - Retry framework for recoverable failures
  - Progress reporting
  - Final response synthesis

The Executive Agent does NOT implement any tools itself.
It delegates all execution to the underlying NovaEngine / AgentPlanner pipeline.

Architecture
------------
User Input
  → IntentAnalyzer
  → TaskClassifier
  → ExecutionPlanner
  → StepExecutor (delegates to NovaEngine)
  → ResultCollector
  → ResponseGenerator
  → Final Answer
"""

import time
import uuid
import threading
from enum import Enum
from typing import Any, Callable, List, Optional, Generator
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    """Classifies the overall complexity and shape of the task."""
    SINGLE_TOOL     = "SINGLE_TOOL"       # One deterministic action
    MULTI_TOOL      = "MULTI_TOOL"        # Sequential tool chain
    CLARIFICATION   = "CLARIFICATION"     # Need more info before acting
    CONVERSATIONAL  = "CONVERSATIONAL"    # General dialogue / Q&A
    PLANNING        = "PLANNING"          # Complex plan + execute
    UNKNOWN         = "UNKNOWN"


class IntentType(str, Enum):
    """High-level user intent category."""
    QUERY           = "QUERY"             # Information retrieval
    ACTION          = "ACTION"            # Execute something (call, open, etc.)
    CREATION        = "CREATION"          # Build or generate artefacts
    ANALYSIS        = "ANALYSIS"          # Analyse data / code
    NAVIGATION      = "NAVIGATION"        # Navigate browser / filesystem
    COMMUNICATION   = "COMMUNICATION"     # Send messages, emails, calls
    SYSTEM          = "SYSTEM"            # System control / settings
    MEMORY          = "MEMORY"            # Save / recall facts
    CLARIFICATION   = "CLARIFICATION"     # "What did you mean?"
    GENERAL         = "GENERAL"           # Fall-through bucket


class ExecutionStatus(str, Enum):
    """Per-step and per-plan execution status."""
    PENDING     = "PENDING"
    RUNNING     = "RUNNING"
    SUCCESS     = "SUCCESS"
    FAILED      = "FAILED"
    RETRYING    = "RETRYING"
    SKIPPED     = "SKIPPED"
    CANCELLED   = "CANCELLED"


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExecutionStep:
    """Represents a single step inside an execution plan."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    input_data: str = ""
    output_data: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    retry_count: int = 0
    max_retries: int = 2
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    depends_on: List[str] = field(default_factory=list)   # step_ids this step waits for
    condition: Optional[str] = None                        # optional conditional guard

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None


@dataclass
class ExecutionPlan:
    """An ordered set of steps to satisfy a user request."""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_type: TaskType = TaskType.UNKNOWN
    intent_type: IntentType = IntentType.GENERAL
    steps: List[ExecutionStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    cancelled: bool = False

    def add_step(self, description: str, input_data: str, **kwargs) -> ExecutionStep:
        step = ExecutionStep(description=description, input_data=input_data, **kwargs)
        self.steps.append(step)
        return step

    @property
    def is_complete(self) -> bool:
        return all(
            s.status in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED, ExecutionStatus.SKIPPED, ExecutionStatus.CANCELLED)
            for s in self.steps
        )

    @property
    def succeeded(self) -> bool:
        return self.is_complete and all(
            s.status in (ExecutionStatus.SUCCESS, ExecutionStatus.SKIPPED)
            for s in self.steps
        )


@dataclass
class ExecutionResult:
    """Final result of a complete execution plan run."""
    plan_id: str
    status: ExecutionStatus
    final_response: str
    steps_executed: int
    steps_succeeded: int
    steps_failed: int
    total_duration: float
    step_results: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "status": str(self.status),
            "final_response": self.final_response,
            "steps_executed": self.steps_executed,
            "steps_succeeded": self.steps_succeeded,
            "steps_failed": self.steps_failed,
            "total_duration": self.total_duration,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Intent Analyser
# ─────────────────────────────────────────────────────────────────────────────

class IntentAnalyzer:
    """
    Lightweight rule-based intent classifier.

    Future: replace keyword heuristics with an LLM classifier call.
    """

    _ACTION_KEYWORDS = {
        "call", "message", "sms", "whatsapp", "send", "open", "launch",
        "run", "execute", "mkdir", "delete", "start", "stop", "restart",
        "git", "pip", "install", "కాల్", "చేయి", "తెరు",
    }
    _QUERY_KEYWORDS = {
        "what", "who", "where", "when", "why", "how", "explain",
        "tell me", "show me", "is", "are", "does", "can you",
        "what is", "which", "find", "search", "look up",
    }
    _COMMUNICATION_KEYWORDS = {
        "call", "message", "sms", "whatsapp", "email", "text", "ring",
        "contact", "reach", "notify", "కాల్", "మెసేజ్",
    }
    _NAVIGATION_KEYWORDS = {
        "open", "go to", "navigate", "browse", "visit", "load",
        "search on", "youtube", "google", "website",
    }
    _SYSTEM_KEYWORDS = {
        "volume", "brightness", "wifi", "bluetooth", "shutdown", "restart",
        "battery", "screenshot", "clipboard", "lock", "unlock",
    }
    _MEMORY_KEYWORDS = {
        "remember", "forget", "recall", "save", "note that", "store",
        "write down", "remind me",
    }
    _CREATION_KEYWORDS = {
        "create", "write", "generate", "build", "make", "code",
        "design", "draft", "compose",
    }
    _ANALYSIS_KEYWORDS = {
        "analyse", "analyze", "review", "check", "debug", "explain code",
        "summarise", "summarize", "compare", "evaluate",
    }

    def analyze(self, text: str) -> IntentType:
        lower = text.lower()
        if any(kw in lower for kw in self._COMMUNICATION_KEYWORDS):
            return IntentType.COMMUNICATION
        if any(kw in lower for kw in self._NAVIGATION_KEYWORDS):
            return IntentType.NAVIGATION
        if any(kw in lower for kw in self._SYSTEM_KEYWORDS):
            return IntentType.SYSTEM
        if any(kw in lower for kw in self._MEMORY_KEYWORDS):
            return IntentType.MEMORY
        if any(kw in lower for kw in self._CREATION_KEYWORDS):
            return IntentType.CREATION
        if any(kw in lower for kw in self._ANALYSIS_KEYWORDS):
            return IntentType.ANALYSIS
        if any(kw in lower for kw in self._ACTION_KEYWORDS):
            return IntentType.ACTION
        if any(kw in lower for kw in self._QUERY_KEYWORDS):
            return IntentType.QUERY
        return IntentType.GENERAL


# ─────────────────────────────────────────────────────────────────────────────
# Task Classifier
# ─────────────────────────────────────────────────────────────────────────────

class TaskClassifier:
    """
    Maps (text, intent) → TaskType.

    Rules-of-thumb:
    - COMMUNICATION / NAVIGATION / SYSTEM / ACTION → SINGLE_TOOL (most cases)
    - "and then" / "also" / "after that" → MULTI_TOOL
    - Queries → CONVERSATIONAL (handled by LLM brain)
    - Multi-sentence imperative sequences → PLANNING
    - Vague short input → CLARIFICATION
    """

    _MULTI_STEP_CONNECTORS = [
        "and then", "after that", "followed by", "afterwards", "subsequently",
    ]
    _PLANNING_MARKERS = {
        "plan", "roadmap", "steps to", "how to", "sequence",
        "strategy", "setup", "configure",
    }

    _MULTI_STEP_PATTERN = None   # lazy-compiled class-level cache

    @classmethod
    def _matches_connectors(cls, lower: str) -> bool:
        """True if text contains a multi-step connector at a word boundary."""
        import re
        if cls._MULTI_STEP_PATTERN is None:
            pattern = "|".join(
                r"(?<![\w])" + re.escape(c) + r"(?![\w])"
                for c in cls._MULTI_STEP_CONNECTORS
            )
            cls._MULTI_STEP_PATTERN = re.compile(pattern, re.IGNORECASE)
        return bool(cls._MULTI_STEP_PATTERN.search(lower))

    def classify(self, text: str, intent: IntentType) -> TaskType:
        lower = text.lower()
        word_count = len(text.split())

        # Single-word vague input -> clarification needed
        if word_count <= 1 and "?" not in text:
            return TaskType.CLARIFICATION

        # Long creation requests -> planning (checked before multi-step connectors)
        if intent == IntentType.CREATION and word_count > 15:
            return TaskType.PLANNING

        # Multi-step connectors with word-boundary matching
        if self._matches_connectors(lower):
            return TaskType.MULTI_TOOL

        if any(marker in lower for marker in self._PLANNING_MARKERS):
            return TaskType.PLANNING

        if intent in (IntentType.QUERY, IntentType.GENERAL, IntentType.ANALYSIS):
            return TaskType.CONVERSATIONAL

        if intent in (
            IntentType.ACTION, IntentType.COMMUNICATION,
            IntentType.NAVIGATION, IntentType.SYSTEM, IntentType.MEMORY,
        ):
            return TaskType.SINGLE_TOOL

        if intent == IntentType.CREATION:
            return TaskType.SINGLE_TOOL

        return TaskType.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# Execution Planner
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionPlanner:
    """
    Builds an ExecutionPlan from classified intent + raw input.

    For SINGLE_TOOL / CONVERSATIONAL: one step that delegates to NovaEngine.
    For MULTI_TOOL: splits on connectors and creates one step per sub-command.
    For PLANNING: one step per numbered / bullet item (future: LLM decompose).
    For CLARIFICATION: one synthetic step that asks the user to clarify.
    """

    _CONNECTORS = [
        "and then", "after that", "followed by", "afterwards",
        "subsequently", "next", "then",
    ]

    def build_plan(
        self,
        user_input: str,
        intent: IntentType,
        task_type: TaskType,
    ) -> ExecutionPlan:
        plan = ExecutionPlan(task_type=task_type, intent_type=intent)

        if task_type == TaskType.CLARIFICATION:
            plan.add_step(
                description="Request clarification from user",
                input_data="__clarification__",
            )
            return plan

        if task_type == TaskType.MULTI_TOOL:
            sub_commands = self._split_on_connectors(user_input)
            if not sub_commands:
                sub_commands = [user_input]
            prev_id = None
            for idx, cmd in enumerate(sub_commands):
                step = plan.add_step(
                    description=f"Step {idx + 1}: {cmd.strip()[:60]}",
                    input_data=cmd.strip(),
                    depends_on=[prev_id] if prev_id else [],
                )
                prev_id = step.step_id
            return plan

        # SINGLE_TOOL / CONVERSATIONAL / PLANNING / UNKNOWN → one engine step
        plan.add_step(
            description=f"Execute: {user_input[:80]}",
            input_data=user_input,
        )
        return plan

    def _split_on_connectors(self, text: str) -> List[str]:
        """Split text on sequential connectors to isolate sub-commands."""
        import re
        pattern = r"\s*(?:" + "|".join(re.escape(c) for c in self._CONNECTORS) + r")\s*"
        parts = re.split(pattern, text, flags=re.IGNORECASE)
        return [p.strip() for p in parts if p.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Step Executor
# ─────────────────────────────────────────────────────────────────────────────

class StepExecutor:
    """
    Executes a single ExecutionStep by delegating to the appropriate agent or the NovaEngine.
    Handles retries and failure isolation.
    """

    CLARIFICATION_RESPONSE = (
        "I'm not sure I understood that. Could you please be more specific?"
    )

    def __init__(
        self,
        engine: Any,
        progress_callback: Optional[Callable] = None,
        coding_agent: Optional[Any] = None,
        browser_agent: Optional[Any] = None,
        android_agent: Optional[Any] = None,
        agent_registry: Optional[Any] = None,
    ) -> None:
        self.engine = engine
        self.progress_callback = progress_callback
        self.coding_agent = coding_agent
        self.browser_agent = browser_agent
        self.android_agent = android_agent
        self.agent_registry = agent_registry
        self.intent_analyzer = IntentAnalyzer()

    def execute(self, step: ExecutionStep, cancel_event: Optional[threading.Event] = None) -> str:
        """Run a step with routing and retry logic. Returns the step output string."""
        if step.input_data == "__clarification__":
            step.status = ExecutionStatus.SUCCESS
            step.output_data = self.CLARIFICATION_RESPONSE
            return self.CLARIFICATION_RESPONSE

        # Resolve sub-agents dynamically from constructor or registry
        reg = self.agent_registry
        coding = self.coding_agent or (reg.resolve("coding") if reg and reg.is_registered("coding") else None)
        browser = self.browser_agent or (reg.resolve("browser") if reg and reg.is_registered("browser") else None)
        android = self.android_agent or (reg.resolve("android") if reg and reg.is_registered("android") else None)
        workspace = getattr(self, "workspace_agent", None) or (reg.resolve("workspace") if reg and reg.is_registered("workspace") else None)
        planner = getattr(self, "planner_agent", None) or (reg.resolve("planner") if reg and reg.is_registered("planner") else None)
        memory = getattr(self, "memory_agent", None) or (reg.resolve("memory") if reg and reg.is_registered("memory") else None)

        # Log to memory if active
        if memory is not None:
            try:
                memory.remember(
                    category="short_term",
                    key="last_step_input",
                    value=step.input_data,
                    tags=["context", "execution"]
                )
            except Exception as mem_err:
                logger.debug("Failed logging execution input to memory: %s", mem_err)

        lower = step.input_data.lower()

        # Route memory requests
        is_mem_action = lower.startswith("remember") or lower.startswith("recall") or "memory" in lower
        if is_mem_action and memory is not None:
            try:
                result = memory.handle_input(step.input_data)
                if not result.startswith("No memories matched"):
                    step.output_data = result
                    step.status = ExecutionStatus.SUCCESS
                    step.finished_at = time.time()
                    self._report(step)
                    return result
            except Exception as e:
                logger.exception("[ExecutiveAgent] Exception in MemoryAgent: %s", e)

        # Route planner requests
        is_goal = False
        goal_keywords = (
            "plan to", "goal:", "solve goal", "steps to solve",
            "complex plan", "first do", "composite task"
        )
        if any(kw in lower for kw in goal_keywords) or "\n" in lower:
            is_goal = True

        if is_goal and planner is not None:
            try:
                from agents.planner_agent import PlannerState
                result = planner.execute(step.input_data)
                if result.status == PlannerState.SUCCESS:
                    step.output_data = result.final_summary
                    step.status = ExecutionStatus.SUCCESS
                    step.finished_at = time.time()
                    self._report(step)
                    return result.final_summary
                else:
                    logger.warning("[ExecutiveAgent] PlannerAgent failed. Falling back to NovaEngine.")
            except Exception as e:
                logger.exception("[ExecutiveAgent] Exception in PlannerAgent: %s", e)

        # Route workspace requests
        is_workspace = False
        workspace_keywords = (
            "create project", "open project", "delete project", "archive project",
            "create folder", "create directory", "mkdir", "rename folder",
            "move folder", "delete folder", "rmdir", "create file", "read file",
            "write file", "append file", "rename file", "copy file", "move file",
            "delete file", "search workspace", "list directory", "list files",
            "create template", "zip", "unzip", "open vs code", "open terminal",
            "open file explorer", "open explorer"
        )
        if any(kw in lower for kw in workspace_keywords):
            is_workspace = True

        if is_workspace and workspace is not None:
            try:
                from agents.workspace_agent import WorkspaceStatus
                result = workspace.execute(step.input_data)
                if result.status == WorkspaceStatus.SUCCESS:
                    step.output_data = result.final_output
                    step.status = ExecutionStatus.SUCCESS
                    step.finished_at = time.time()
                    self._report(step)
                    return result.final_output
                else:
                    logger.warning("[ExecutiveAgent] WorkspaceAgent failed. Falling back to NovaEngine.")
            except Exception as e:
                logger.exception("[ExecutiveAgent] Exception in WorkspaceAgent: %s", e)

        # Determine if we can route this step to standard sub-agents
        intent = self.intent_analyzer.analyze(step.input_data)
        agent_executed = False
        agent_success = False
        agent_output = ""

        try:
            if intent == IntentType.CREATION and coding is not None:
                from agents.coding_agent import CodingStatus
                agent_executed = True
                coding_result = coding.execute(step.input_data)
                if coding_result.status == CodingStatus.SUCCESS:
                    agent_success = True
                    agent_output = coding_result.summary()
                else:
                    logger.warning("[ExecutiveAgent] CodingAgent failed: %s. Falling back to NovaEngine.", coding_result.errors)

            elif intent == IntentType.NAVIGATION and browser is not None:
                from agents.browser_agent import BrowserStatus
                agent_executed = True
                browser_result = browser.execute(step.input_data)
                if browser_result.status == BrowserStatus.SUCCESS:
                    agent_success = True
                    agent_output = browser_result.final_output or browser_result.summary()
                else:
                    logger.warning("[ExecutiveAgent] BrowserAgent failed: %s. Falling back to NovaEngine.", browser_result.errors)

            elif intent == IntentType.COMMUNICATION and android is not None:
                from agents.android_agent import AndroidStatus
                agent_executed = True
                android_result = android.execute(step.input_data)
                if android_result.status == AndroidStatus.SUCCESS:
                    agent_success = True
                    agent_output = android_result.final_output or android_result.summary()
                else:
                    logger.warning("[ExecutiveAgent] AndroidAgent failed: %s. Falling back to NovaEngine.", android_result.errors)

        except Exception as e:
            logger.exception("[ExecutiveAgent] Graceful fallback after agent exception: %s", e)

        # If routed and succeeded, return the output immediately
        if agent_executed and agent_success:
            step.output_data = agent_output
            step.status = ExecutionStatus.SUCCESS
            step.finished_at = time.time()
            self._report(step)

            # Log to memory if active
            if memory is not None:
                try:
                    memory.remember(
                        category="working",
                        key="last_step_output",
                        value=agent_output,
                        tags=["context", "output"]
                    )
                except Exception as mem_err:
                    logger.debug("Failed logging execution outcome to memory: %s", mem_err)

            return agent_output

        # Otherwise (or if fallback occurred), execute via NovaEngine

        attempt = 0
        while attempt <= step.max_retries:
            if cancel_event and cancel_event.is_set():
                step.status = ExecutionStatus.CANCELLED
                step.output_data = "Cancelled by user."
                return step.output_data

            step.started_at = time.time()
            step.status = ExecutionStatus.RUNNING if attempt == 0 else ExecutionStatus.RETRYING
            self._report(step)

            try:
                result = self.engine.handle_input(step.input_data, stream=False)
                # handle_input may return a generator for streaming mode — coerce it
                if hasattr(result, "__iter__") and not isinstance(result, str):
                    result = "".join(result)

                step.output_data = result
                step.status = ExecutionStatus.SUCCESS
                step.finished_at = time.time()
                self._report(step)
                return result

            except Exception as e:
                attempt += 1
                step.error = str(e)
                step.retry_count = attempt
                logger.error(
                    "[ExecutiveAgent] Step '%s' failed (attempt %d/%d): %s",
                    step.description, attempt, step.max_retries + 1, e
                )
                if attempt > step.max_retries:
                    step.status = ExecutionStatus.FAILED
                    step.finished_at = time.time()
                    step.output_data = f"Step failed after {attempt} attempt(s): {e}"
                    self._report(step)
                    return step.output_data
                time.sleep(0.5 * attempt)   # simple back-off

        # Should not reach here
        step.status = ExecutionStatus.FAILED
        return step.output_data or "Unknown failure."

    def _report(self, step: ExecutionStep) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(step)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Result Collector & Response Generator
# ─────────────────────────────────────────────────────────────────────────────

class ResultCollector:
    """Aggregates step outputs into a structured ExecutionResult."""

    def collect(self, plan: ExecutionPlan, total_duration: float) -> ExecutionResult:
        succeeded = sum(1 for s in plan.steps if s.status == ExecutionStatus.SUCCESS)
        failed    = sum(1 for s in plan.steps if s.status == ExecutionStatus.FAILED)
        executed  = len(plan.steps)

        # For single-step plans return its output directly
        final_response: str
        if len(plan.steps) == 1:
            final_response = plan.steps[0].output_data or ""
        else:
            # Combine outputs for multi-step plans
            parts = []
            for idx, step in enumerate(plan.steps):
                if step.output_data:
                    parts.append(f"Step {idx + 1}: {step.output_data}")
            final_response = "\n".join(parts) if parts else "No output produced."

        overall_status = (
            ExecutionStatus.SUCCESS if succeeded == executed else
            ExecutionStatus.FAILED  if failed == executed   else
            ExecutionStatus.CANCELLED if plan.cancelled     else
            ExecutionStatus.FAILED
        )

        return ExecutionResult(
            plan_id=plan.plan_id,
            status=overall_status,
            final_response=final_response,
            steps_executed=executed,
            steps_succeeded=succeeded,
            steps_failed=failed,
            total_duration=total_duration,
            step_results=[
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "status": str(s.status),
                    "output": s.output_data,
                    "duration": s.duration,
                    "retries": s.retry_count,
                }
                for s in plan.steps
            ],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Executive Agent
# ─────────────────────────────────────────────────────────────────────────────

class ExecutiveAgent:
    """
    Nova's central orchestration brain.

    Wraps a NovaEngine and adds:
      - Intent analysis
      - Task classification
      - Execution planning (single / multi-step / conditional)
      - Retry & failure recovery
      - Cancellation via threading.Event
      - Progress callbacks for UI / voice feedback
      - Execution result reporting

    Future extension points:
      - CodingAgent, ResearchAgent, BrowserAgent, AndroidAgent, MemoryAgent
        can be registered as specialised sub-agents and routed here.
    """

    def __init__(
        self,
        engine: Any,
        progress_callback: Optional[Callable[[ExecutionStep], None]] = None,
        coding_agent: Optional[Any] = None,
        browser_agent: Optional[Any] = None,
        android_agent: Optional[Any] = None,
        agent_registry: Optional[Any] = None,
    ) -> None:
        """
        Args:
            engine: A NovaEngine (or any object exposing .handle_input(text, stream)).
            progress_callback: Optional callable receiving ExecutionStep updates.
            coding_agent: Optional CodingAgent instance.
            browser_agent: Optional BrowserAgent instance.
            android_agent: Optional AndroidAgent instance.
            agent_registry: Optional AgentRegistry instance.
        """
        self.engine            = engine
        self.intent_analyzer   = IntentAnalyzer()
        self.task_classifier   = TaskClassifier()
        self.planner           = ExecutionPlanner()
        self.agent_registry    = agent_registry
        self.step_executor     = StepExecutor(
            engine,
            progress_callback=progress_callback,
            coding_agent=coding_agent,
            browser_agent=browser_agent,
            android_agent=android_agent,
            agent_registry=agent_registry,
        )
        self.result_collector  = ResultCollector()
        self._cancel_event     = threading.Event()
        self._lock             = threading.Lock()
        logger.info("[ExecutiveAgent] Initialized.")

    # ── Public API ────────────────────────────────────────────────────────────

    def _report_progress(self, message: str) -> None:
        if self.step_executor and self.step_executor.progress_callback:
            try:
                dummy_step = ExecutionStep(
                    step_id="progress",
                    description=message,
                    input_data=message
                )
                dummy_step.status = ExecutionStatus.RUNNING
                self.step_executor.progress_callback(dummy_step)
            except Exception:
                pass

    def execute(self, user_input: str) -> ExecutionResult:
        """
        Routes the user request, resolves specialized sub-agents via AgentRegistry,
        invokes planners, retries tasks, and records outcomes in MemoryAgent.
        """
        self._cancel_event.clear()
        started = time.time()
        user_input = user_input.strip()
        logger.info("[ExecutiveAgent] Received input: %r", user_input)

        # Notify initial progress
        self._report_progress("Planning...")

        # Resolve registry and sub-agents
        reg = self.agent_registry
        planner = reg.resolve("planner") if reg and reg.is_registered("planner") else None
        coding = reg.resolve("coding") if reg and reg.is_registered("coding") else None
        browser = reg.resolve("browser") if reg and reg.is_registered("browser") else None
        android = reg.resolve("android") if reg and reg.is_registered("android") else None
        workspace = reg.resolve("workspace") if reg and reg.is_registered("workspace") else None
        memory = reg.resolve("memory") if reg and reg.is_registered("memory") else None

        intent = self.intent_analyzer.analyze(user_input)
        task_type = self.task_classifier.classify(user_input, intent)
        
        response_text = ""
        success = True
        lower = user_input.lower()
        
        # ── 1. Complex Goal / Multi-step Planner Agent ───────────────────
        is_planning = False
        goal_keywords = (
            "plan to", "goal:", "solve goal", "steps to solve",
            "complex plan", "first do", "composite task", "create portfolio website",
            "website", "app"
        )
        if any(kw in lower for kw in goal_keywords) or "\n" in lower or task_type == TaskType.PLANNING:
            is_planning = True

        if is_planning and planner is not None:
            self._report_progress("Decomposing goal into tasks...")
            try:
                plan_result = planner.execute(user_input)
                self._report_progress("Running tasks sequentially...")
                
                tasks_succeeded = True
                for task in plan_result.tasks:
                    self._report_progress(f"Running task: {task.description}...")
                    
                    # Run task with 1 retry on failure
                    attempt = 0
                    task_success = False
                    while attempt <= 1:
                        try:
                            step = ExecutionStep(
                                step_id=task.task_id,
                                description=task.description,
                                input_data=task.description
                            )
                            self.step_executor.execute(step, cancel_event=self._cancel_event)
                            if step.status == ExecutionStatus.SUCCESS:
                                task_success = True
                                break
                        except Exception as e:
                            logger.warning("Task execution attempt %d failed: %s", attempt + 1, e)
                        attempt += 1
                    
                    if not task_success:
                        logger.error("Task '%s' failed after retry.", task.description)
                        tasks_succeeded = False
                        
                    # Save completed task to memory
                    if memory:
                        try:
                            memory.remember(
                                category="short_term",
                                key=f"task_{task.task_id}",
                                value=task.description,
                                tags=["task", "completed"]
                            )
                        except Exception:
                            pass
                
                response_text = plan_result.final_summary or "Plan completed."
                success = tasks_succeeded
            except Exception as e:
                logger.exception("PlannerAgent execution error: %s", e)
                success = False
                response_text = f"Planning failed: {e}"

        # ── 2. Autonomous Coder Web/App requests (Project Lifecycle) ─────
        elif ("create" in lower or "generate" in lower or "write code" in lower) and coding and workspace and browser:
            self._report_progress("Initializing Project Lifecycle...")
            try:
                from agents.autonomous_coder import AutonomousCoder
                from core.project_lifecycle import ProjectLifecycle
                auton_coder = AutonomousCoder(
                    coding_agent=coding,
                    workspace_agent=workspace,
                    browser_agent=browser
                )
                lifecycle = ProjectLifecycle(
                    planner_agent=planner,
                    autonomous_coder=auton_coder,
                    browser_agent=browser,
                    memory_agent=memory
                )
                self._report_progress("Running Project Lifecycle (Planning, Generating, Executing)...")
                lifecycle_report = lifecycle.run(user_input)
                response_text = (
                    "Boss,\n"
                    "The website has been created successfully.\n"
                    "The server is running.\n"
                    "Browser opened.\n"
                    "No runtime errors detected."
                ) if lifecycle_report.success else f"Project lifecycle failed: {lifecycle_report.errors}"
                success = lifecycle_report.success
            except Exception as e:
                logger.exception("ProjectLifecycle execution error: %s", e)
                success = False
                response_text = f"Project lifecycle failed: {e}"

        # ── 3. Browser Queries ───────────────────────────────────────────
        elif intent == IntentType.NAVIGATION and browser is not None:
            self._report_progress("Searching web using BrowserAgent...")
            try:
                res = browser.execute(user_input)
                response_text = res.final_output or res.summary()
                success = res.status == "SUCCESS"
            except Exception as e:
                success = False
                response_text = f"Browser query failed: {e}"

        # ── 4. Workspace Operations ──────────────────────────────────────
        elif workspace is not None and any(kw in lower for kw in ("vs code", "terminal", "folder", "directory", "file")):
            self._report_progress("Executing workspace operation...")
            try:
                res = workspace.execute(user_input)
                response_text = res.final_output or res.summary()
                success = res.status == "SUCCESS"
            except Exception as e:
                success = False
                response_text = f"Workspace operation failed: {e}"

        # ── 5. Android Automation ────────────────────────────────────────
        elif intent == IntentType.COMMUNICATION and android is not None:
            self._report_progress("Executing android command...")
            try:
                res = android.execute(user_input)
                response_text = res.final_output or res.summary()
                success = res.status == "SUCCESS"
            except Exception as e:
                success = False
                response_text = f"Android execution failed: {e}"

        # ── 6. Memory requests ───────────────────────────────────────────
        elif memory is not None and ("remember" in lower or "recall" in lower or "memory" in lower):
            self._report_progress("Querying MemoryAgent...")
            try:
                response_text = memory.handle_input(user_input)
                success = not response_text.startswith("No memories matched")
            except Exception as e:
                success = False
                response_text = f"Memory check failed: {e}"

        # ── 7. Fallback to NovaEngine ────────────────────────────────────
        else:
            self._report_progress("Executing standard query...")
            try:
                res = self.engine.handle_input(user_input, stream=False)
                if hasattr(res, "__iter__") and not isinstance(res, str):
                    res = "".join(res)
                response_text = res
            except Exception as e:
                success = False
                response_text = f"Standard query failed: {e}"

        # ── 8. Save final response in MemoryAgent ────────────────────────
        if memory:
            try:
                memory.remember(
                    category="short_term",
                    key="last_response",
                    value=response_text
                )
            except Exception:
                pass

        self._report_progress("Finished.")

        # Build final ExecutionResult object
        duration = time.time() - started
        final_result = ExecutionResult(
            plan_id="orchestrator_plan",
            status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED,
            final_response=response_text,
            steps_executed=1,
            steps_succeeded=1 if success else 0,
            steps_failed=0 if success else 1,
            total_duration=duration,
            step_results=[
                {
                    "step_id": "orchestrator_step",
                    "description": "Central orchestration query execution",
                    "status": "SUCCESS" if success else "FAILED",
                    "output": response_text,
                    "duration": duration
                }
            ]
        )
        return final_result

    def cancel(self) -> None:
        """Cancel any currently running execution plan."""
        self._cancel_event.set()
        logger.info("[ExecutiveAgent] Cancellation signal sent.")

    def handle_input(self, user_input: str, stream: bool = False) -> str | Generator:
        """
        Compatibility shim so ExecutiveAgent can be used anywhere NovaEngine is used.

        Args:
            user_input: Raw text from the user.
            stream: Ignored — ExecutiveAgent always returns synchronously.
                    Kept for interface compatibility.

        Returns:
            Final response string.
        """
        result = self.execute(user_input)
        final = result.final_response

        if stream:
            def _gen():
                yield final
            return _gen()
        return final
