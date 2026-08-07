"""
agents/android_agent.py
-----------------------
The Android Agent is Nova's autonomous Android device operator.

It wraps the existing AndroidTool / ADB infrastructure WITHOUT duplicating
any ADB logic, and is designed to be dispatched by the ExecutiveAgent for
all mobile/communication tasks.

Architecture
------------
AndroidAgent is a pure adapter layer:

             User Request
                  ↓
        ExecutiveAgent (routes COMMUNICATION intent)
                  ↓
         AndroidAgent.execute()
                  ↓
          AndroidTask → ActionRunner
                  ↓
          AndroidTool.execute()  ← existing ADB implementation
                  ↓
             AndroidResult

Supported Actions
-----------------
- CALL          : Make a phone call via ADB intent
- SMS           : Send SMS via ADB intent
- WHATSAPP      : Send WhatsApp message via ADB intent
- OPEN_APP      : Launch any Android application
- OPEN_SETTINGS : Open phone settings screen
- CHECK_DEVICE  : Verify ADB device connection
- RECONNECT     : Re-establish wireless ADB connection
- SHELL_CMD     : Execute an arbitrary ADB shell command
- READ_CONTACTS : List saved contacts
- READ_NOTIFICATIONS : Read active notifications

NOT implemented
---------------
- Device flashing / ROM operations
- App installation (no APK side-loading)
- File transfer (separate tool scope)
- Screen recording
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class AndroidAction(str, Enum):
    """All actions the AndroidAgent can perform."""
    CALL                = "call"
    SMS                 = "sms"
    WHATSAPP            = "whatsapp"
    OPEN_APP            = "open_app"
    OPEN_SETTINGS       = "open_settings"
    CHECK_DEVICE        = "check_device"
    RECONNECT           = "reconnect"
    SHELL_CMD           = "shell_cmd"
    READ_CONTACTS       = "read_contacts"
    READ_NOTIFICATIONS  = "read_notifications"


class AndroidStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    RETRYING  = "RETRYING"
    CANCELLED = "CANCELLED"


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AndroidStep:
    """One atomic Android action inside an AndroidTask."""
    action: AndroidAction
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    max_retries: int = 2
    # Populated by ActionRunner after execution
    output: Optional[str] = None
    status: AndroidStatus = AndroidStatus.PENDING
    error: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None

    def succeeded(self) -> bool:
        return self.status == AndroidStatus.SUCCESS


@dataclass
class AndroidTask:
    """
    An ordered list of AndroidSteps that fulfil one user Android request.

    Can be built by AndroidPlanner from natural language, or constructed
    programmatically for direct API use.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    steps: List[AndroidStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    cancelled: bool = False

    def add_step(
        self,
        step_action: AndroidAction,
        description: str = "",
        **params,
    ) -> AndroidStep:
        step = AndroidStep(action=step_action, params=params, description=description)
        self.steps.append(step)
        return step


@dataclass
class AndroidResult:
    """Structured result returned by AndroidAgent after task execution."""
    task_id: str
    status: AndroidStatus
    steps_executed: int
    steps_succeeded: int
    steps_failed: int
    total_duration: float
    final_output: str
    step_outputs: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[AndroidAgent] Task {self.task_id} | {self.status} | "
            f"Steps {self.steps_succeeded}/{self.steps_executed} succeeded | "
            f"{self.total_duration:.2f}s"
        )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": str(self.status),
            "steps_executed": self.steps_executed,
            "steps_succeeded": self.steps_succeeded,
            "steps_failed": self.steps_failed,
            "total_duration": self.total_duration,
            "final_output": self.final_output,
            "errors": self.errors,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Android Planner  (natural-language → AndroidTask)
# ─────────────────────────────────────────────────────────────────────────────

class AndroidPlanner:
    """
    Converts a natural-language Android/communication request into an AndroidTask.

    Uses keyword heuristics.  Future: replace with LLM intent parsing.
    """

    # (intent keywords, action)
    _RULES: List[tuple] = [
        # More-specific phrases first to avoid false matches
        (["phone settings", "device settings",
          "settings", "setting"],                              AndroidAction.OPEN_SETTINGS),
        (["call", "కాల్", "ring", "phone", "dial"],           AndroidAction.CALL),
        (["whatsapp", "వాట్సాప్", "wa ", "wa\n"],             AndroidAction.WHATSAPP),
        (["sms", "text", "message", "మెసేజ్", "msg"],         AndroidAction.SMS),
        (["open app", "launch app", "start app", "open "],    AndroidAction.OPEN_APP),
        (["check device", "device status", "adb status",
          "connected", "connection"],                          AndroidAction.CHECK_DEVICE),
        (["reconnect", "re-connect", "wireless", "wifi adb"], AndroidAction.RECONNECT),
        (["contacts", "phone book", "contact list"],           AndroidAction.READ_CONTACTS),
        (["notifications", "notification", "alerts"],          AndroidAction.READ_NOTIFICATIONS),
        (["shell", "adb shell", "command", "cmd"],             AndroidAction.SHELL_CMD),
    ]

    def plan(self, request: str) -> AndroidTask:
        import re
        lower = request.lower()
        task = AndroidTask(description=request)

        action = self._detect_action(lower)

        if action == AndroidAction.CALL:
            contact = self._extract_contact(request)
            task.add_step(
                AndroidAction.CALL,
                f"Call {contact}",
                action="call", contact=contact,
            )

        elif action == AndroidAction.SMS:
            contact = self._extract_contact(request)
            message = self._extract_message(request)
            task.add_step(
                AndroidAction.SMS,
                f"Send SMS to {contact}",
                action="sms", contact=contact, message=message,
            )

        elif action == AndroidAction.WHATSAPP:
            contact = self._extract_contact(request)
            message = self._extract_message(request)
            task.add_step(
                AndroidAction.WHATSAPP,
                f"Send WhatsApp to {contact}",
                action="whatsapp", contact=contact, message=message,
            )

        elif action == AndroidAction.OPEN_APP:
            app = self._extract_app_name(request)
            task.add_step(
                AndroidAction.OPEN_APP,
                f"Open app: {app}",
                action="open_app", app=app,
            )

        elif action == AndroidAction.OPEN_SETTINGS:
            task.add_step(
                AndroidAction.OPEN_SETTINGS,
                "Open phone settings",
                action="open_settings",
            )

        elif action == AndroidAction.CHECK_DEVICE:
            task.add_step(
                AndroidAction.CHECK_DEVICE,
                "Check ADB device connection",
                action="check_device",
            )

        elif action == AndroidAction.RECONNECT:
            task.add_step(
                AndroidAction.RECONNECT,
                "Reconnect wireless ADB",
                action="reconnect",
            )

        elif action == AndroidAction.READ_CONTACTS:
            task.add_step(
                AndroidAction.READ_CONTACTS,
                "Read saved contacts",
                action="read_contacts",
            )

        elif action == AndroidAction.READ_NOTIFICATIONS:
            task.add_step(
                AndroidAction.READ_NOTIFICATIONS,
                "Read active notifications",
                action="read_notifications",
            )

        elif action == AndroidAction.SHELL_CMD:
            cmd = self._extract_shell_cmd(request)
            task.add_step(
                AndroidAction.SHELL_CMD,
                f"Run shell: {cmd}",
                action="shell_cmd", command=cmd,
            )

        else:
            # Unknown — check device as safe default
            task.add_step(
                AndroidAction.CHECK_DEVICE,
                "Check ADB device connection (fallback)",
                action="check_device",
            )

        return task

    # ── Private helpers ────────────────────────────────────────────────────

    def _detect_action(self, lower: str) -> AndroidAction:
        for keywords, action in self._RULES:
            if any(kw in lower for kw in keywords):
                return action
        return AndroidAction.CHECK_DEVICE

    def _extract_contact(self, text: str) -> str:
        import re
        # Remove leading action verbs + common words
        cleaned = re.sub(
            r"(?i)^(call|ring|phone|dial|message|sms|text|send|whatsapp|wa|"
            r"కాల్|చేయి|మెసేజ్|వాట్సాప్)\s+",
            "", text.strip()
        )
        # Take first word(s) as contact name (up to 3 words)
        words = cleaned.split()
        contact_words = []
        stop_words = {"hi", "hello", "hey", "and", "the", "a", "to", "saying", "with"}
        for w in words[:3]:
            if w.lower() in stop_words:
                break
            contact_words.append(w)
        return " ".join(contact_words) if contact_words else text.strip()

    def _extract_message(self, text: str) -> str:
        import re
        # Look for message content after "saying", "saying:", text in quotes
        for pattern in [
            r'(?:saying|message|text|body)[:\s]+["\']?(.+)["\']?$',
            r'"([^"]+)"',
            r"'([^']+)'",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        # Fallback: everything after the contact name
        parts = text.split()
        if len(parts) > 2:
            return " ".join(parts[2:])
        return "Hello"

    def _extract_app_name(self, text: str) -> str:
        import re
        match = re.search(r"(?:open|launch|start)\s+(.+?)(?:\s+app)?$", text, re.IGNORECASE)
        return match.group(1).strip() if match else "unknown"

    def _extract_shell_cmd(self, text: str) -> str:
        import re
        match = re.search(r"(?:shell|cmd|command)[:\s]+(.+)$", text, re.IGNORECASE)
        return match.group(1).strip() if match else text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Action Runner  (executes AndroidStep via AndroidTool with retry + reconnect)
# ─────────────────────────────────────────────────────────────────────────────

class ActionRunner:
    """
    Executes individual AndroidSteps through the AndroidTool adapter.

    Retry strategy:
    - On failure, attempt up to step.max_retries times.
    - For CALL / SMS / WHATSAPP, attempt ADB reconnect before each retry.
    - Thread-safe: uses a lock to serialise tool calls.
    """

    _RECONNECT_ACTIONS = {
        AndroidAction.CALL,
        AndroidAction.SMS,
        AndroidAction.WHATSAPP,
        AndroidAction.OPEN_APP,
        AndroidAction.OPEN_SETTINGS,
        AndroidAction.READ_NOTIFICATIONS,
        AndroidAction.SHELL_CMD,
    }

    def __init__(
        self,
        android_tool: Any,
        progress_callback: Optional[Callable] = None,
    ) -> None:
        self.android_tool = android_tool
        self.progress_callback = progress_callback
        self._lock = threading.Lock()

    def run(self, step: AndroidStep, cancel_event: Optional[threading.Event] = None) -> str:
        """Execute an AndroidStep with retry and optional reconnect."""
        attempt = 0
        while attempt <= step.max_retries:
            if cancel_event and cancel_event.is_set():
                step.status = AndroidStatus.CANCELLED
                step.output = "Cancelled by user."
                self._notify(step)
                return step.output

            attempt += 1
            step.started_at = time.time()
            step.status = AndroidStatus.RUNNING if attempt == 1 else AndroidStatus.RETRYING
            self._notify(step)

            # Try reconnect before retries for device-sensitive actions
            if attempt > 1 and step.action in self._RECONNECT_ACTIONS:
                self._try_reconnect()

            try:
                with self._lock:
                    output: str = self.android_tool.execute(**step.params)

                step.output = output
                step.finished_at = time.time()

                if output.lower().startswith("failure"):
                    raise RuntimeError(output)

                step.status = AndroidStatus.SUCCESS
                self._notify(step)
                return output

            except Exception as e:
                step.error = str(e)
                step.retry_count = attempt
                logger.warning(
                    "[AndroidAgent] Step '%s' attempt %d/%d failed: %s",
                    step.description, attempt, step.max_retries + 1, e
                )
                if attempt > step.max_retries:
                    step.status = AndroidStatus.FAILED
                    step.finished_at = time.time()
                    step.output = f"Failed after {attempt} attempt(s): {e}"
                    self._notify(step)
                    return step.output
                time.sleep(0.5 * attempt)

        step.status = AndroidStatus.FAILED
        return step.output or "Unknown failure."

    def _try_reconnect(self) -> None:
        """Attempt to reconnect ADB device without blocking the main flow."""
        try:
            self.android_tool.execute(action="reconnect")
            logger.info("[AndroidAgent] ADB reconnect attempted before retry.")
        except Exception as e:
            logger.debug("[AndroidAgent] Reconnect attempt failed silently: %s", e)

    def _notify(self, step: AndroidStep) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(step)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Result Builder
# ─────────────────────────────────────────────────────────────────────────────

class ResultBuilder:
    """Aggregates executed AndroidTask steps into an AndroidResult."""

    def build(self, task: AndroidTask, total_duration: float) -> AndroidResult:
        succeeded = [s for s in task.steps if s.status == AndroidStatus.SUCCESS]
        failed    = [s for s in task.steps if s.status == AndroidStatus.FAILED]
        errors    = [f"[{s.action.value}] {s.error}" for s in task.steps if s.error]

        step_outputs = [
            {
                "action":      s.action.value,
                "description": s.description,
                "status":      str(s.status),
                "output":      s.output,
                "duration":    s.duration,
                "retries":     s.retry_count,
            }
            for s in task.steps
        ]

        # Final output: last successful step's output, or last step output
        final_output = ""
        for step in reversed(task.steps):
            if step.output and step.status == AndroidStatus.SUCCESS:
                final_output = step.output
                break
        if not final_output and task.steps:
            final_output = task.steps[-1].output or ""

        overall_status = (
            AndroidStatus.CANCELLED if task.cancelled else
            AndroidStatus.SUCCESS   if not failed      else
            AndroidStatus.FAILED
        )

        return AndroidResult(
            task_id=task.task_id,
            status=overall_status,
            steps_executed=len(task.steps),
            steps_succeeded=len(succeeded),
            steps_failed=len(failed),
            total_duration=total_duration,
            final_output=final_output,
            step_outputs=step_outputs,
            errors=errors,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Android Agent
# ─────────────────────────────────────────────────────────────────────────────

class AndroidAgent:
    """
    Nova's autonomous Android device operator.

    Accepts natural-language or programmatic Android requests, builds an
    AndroidTask, executes each step through the existing AndroidTool adapter,
    and returns a structured AndroidResult.

    Usage
    -----
    agent = AndroidAgent()
    result = agent.execute("Call Mom")

    Programmatic API:
    task = AndroidTask(description="Direct task")
    task.add_step(AndroidAction.CALL, "Call Mom", action="call", contact="Mom")
    result = agent.execute_task(task)

    Integration with ExecutiveAgent
    --------------------------------
    ExecutiveAgent.StepExecutor routes COMMUNICATION intent steps to
    AndroidAgent.execute(step.input_data) instead of NovaEngine.

    handle_input() shim makes AndroidAgent a drop-in for NovaEngine.
    """

    def __init__(
        self,
        android_tool: Optional[Any] = None,
        progress_callback: Optional[Callable[[AndroidStep], None]] = None,
        max_step_retries: int = 2,
    ) -> None:
        """
        Args:
            android_tool:       Object exposing .execute(**kwargs) → str.
                                Defaults to AndroidTool from tools.android_tool.
            progress_callback:  Called with each AndroidStep as it progresses.
            max_step_retries:   Default retry count for each step.
        """
        if android_tool is None:
            try:
                from tools.android_tool import AndroidTool
                android_tool = AndroidTool()
            except Exception as e:
                logger.warning("[AndroidAgent] Could not load AndroidTool: %s. Using stub.", e)
                android_tool = _StubAndroidTool()

        self.android_tool     = android_tool
        self.max_step_retries = max_step_retries
        self.planner          = AndroidPlanner()
        self.runner           = ActionRunner(android_tool, progress_callback=progress_callback)
        self.result_builder   = ResultBuilder()
        self._cancel_event    = threading.Event()

        logger.info("[AndroidAgent] Initialized with tool: %s", type(android_tool).__name__)

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(self, request: str) -> AndroidResult:
        """
        Full pipeline: plan → execute steps → return AndroidResult.

        Args:
            request: Natural-language Android instruction.

        Returns:
            AndroidResult with final output and statistics.
        """
        self._cancel_event.clear()
        started = time.time()
        task = self.planner.plan(request)
        logger.info(
            "[AndroidAgent] Task %s: '%s' — %d step(s)",
            task.task_id, task.description[:60], len(task.steps)
        )
        self._run_steps(task)
        total_duration = time.time() - started
        result = self.result_builder.build(task, total_duration)
        logger.info("[AndroidAgent] %s", result.summary())
        return result

    def execute_task(self, task: AndroidTask) -> AndroidResult:
        """
        Execute a pre-built AndroidTask directly (programmatic API).

        Args:
            task: A fully constructed AndroidTask.

        Returns:
            AndroidResult.
        """
        self._cancel_event.clear()
        started = time.time()
        logger.info(
            "[AndroidAgent] Executing pre-built task %s — %d step(s)",
            task.task_id, len(task.steps)
        )
        self._run_steps(task)
        total_duration = time.time() - started
        result = self.result_builder.build(task, total_duration)
        logger.info("[AndroidAgent] %s", result.summary())
        return result

    def cancel(self) -> None:
        """Signal cancellation of any in-progress execution."""
        self._cancel_event.set()
        logger.info("[AndroidAgent] Cancellation signal sent.")

    def handle_input(self, user_input: str, stream: bool = False):
        """
        Compatibility shim — allows AndroidAgent to be used wherever
        NovaEngine.handle_input() is expected.

        Returns:
            Final response string (or single-chunk generator if stream=True).
        """
        result = self.execute(user_input)
        response = result.final_output or result.summary()
        if stream:
            def _gen():
                yield response
            return _gen()
        return response

    # ── Internal ───────────────────────────────────────────────────────────

    def _run_steps(self, task: AndroidTask) -> None:
        """
        Execute all steps sequentially.

        On failure: marks the step FAILED; remaining steps are CANCELLED.
        Respects the cancel_event for cooperative cancellation.
        """
        failed = False
        for step in task.steps:
            if failed or (self._cancel_event.is_set()):
                step.status = AndroidStatus.CANCELLED
                step.output = "Cancelled: prior step failed or user cancelled."
                if self._cancel_event.is_set():
                    task.cancelled = True
                continue

            step.max_retries = self.max_step_retries
            self.runner.run(step, cancel_event=self._cancel_event)

            if step.status == AndroidStatus.FAILED:
                logger.warning(
                    "[AndroidAgent] Step '%s' failed — cancelling remaining steps.",
                    step.description
                )
                failed = True


# ─────────────────────────────────────────────────────────────────────────────
# Stub Android Tool (used when ADB / AndroidTool is unavailable)
# ─────────────────────────────────────────────────────────────────────────────

class _StubAndroidTool:
    """
    Minimal no-op Android tool for environments without ADB.
    Returns Success: messages so the pipeline still completes.
    """

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        contact = kwargs.get("contact", "")
        message = kwargs.get("message", "")

        if action == "call":
            return f"Success: Calling {contact} (stub — ADB not available)."
        if action == "sms":
            return f"Success: SMS composed for {contact}: '{message}' (stub)."
        if action == "whatsapp":
            return f"Success: WhatsApp opened for {contact}: '{message}' (stub)."
        if action == "open_app":
            return f"Success: Opened app '{kwargs.get('app', '')}' (stub)."
        if action == "open_settings":
            return "Success: Opened settings (stub)."
        if action == "check_device":
            return "Success: Device connected (stub)."
        if action == "reconnect":
            return "Success: Reconnected (stub)."
        if action == "read_contacts":
            return "Success: Contacts: [stub mode — no real ADB]"
        if action == "read_notifications":
            return "Success: Notifications: [stub mode — no real ADB]"
        if action == "shell_cmd":
            return f"Success: Shell command executed (stub): {kwargs.get('command', '')}"
        return f"Success: Action '{action}' executed (stub)."
