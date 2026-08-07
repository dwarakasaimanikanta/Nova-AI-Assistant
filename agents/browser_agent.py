"""
agents/browser_agent.py
-----------------------
The Browser Agent is Nova's autonomous web operator.

It sits alongside the CodingAgent as a specialised sub-agent and is designed
to be dispatched by the ExecutiveAgent for web-related tasks.

Architecture
------------
BrowserAgent wraps the existing BrowserTool / BrowserManager Playwright
infrastructure WITHOUT duplicating any browser logic.

                 User Request
                      ↓
             ExecutiveAgent (routes)
                      ↓
              BrowserAgent.execute()
                      ↓
          BrowserTask  →  ActionRunner
                      ↓
             BrowserTool / BrowserManager
                      ↓
               BrowserResult

Capabilities
------------
- Open URLs
- Google search
- Click elements (CSS selector or visible text)
- Type into inputs
- Extract visible page text
- Capture screenshots
- Download files
- Wait for selectors
- Scroll page
- Retry transient failures
- Progress callbacks

NOT implemented
---------------
- Git operations
- Deployment
- Server-side rendering / testing suites
"""

from __future__ import annotations

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

class BrowserAction(str, Enum):
    """All actions the BrowserAgent can perform."""
    LAUNCH          = "launch_browser"
    OPEN_URL        = "open_url"
    SEARCH          = "search_google"
    CLICK           = "click_element"
    CLICK_TEXT      = "click_text"
    TYPE            = "type_text"
    EXTRACT_TEXT    = "extract_text"
    SCREENSHOT      = "capture_screenshot"
    SCROLL          = "scroll_page"
    DOWNLOAD        = "download_file"
    WAIT_SELECTOR   = "wait_for_selector"
    PRESS_KEY       = "press_key"
    CLOSE           = "close_browser"


class BrowserStatus(str, Enum):
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
class BrowserStep:
    """One atomic browser action inside a BrowserTask."""
    action: BrowserAction
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    max_retries: int = 2
    # Populated by ActionRunner after execution
    output: Optional[str] = None
    status: BrowserStatus = BrowserStatus.PENDING
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
        return self.status == BrowserStatus.SUCCESS


@dataclass
class BrowserTask:
    """
    An ordered list of BrowserSteps that fulfil one user browser request.

    Built by BrowserPlanner from a natural-language request or constructed
    programmatically when used as a library.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    steps: List[BrowserStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_step(
        self,
        action: BrowserAction,
        description: str = "",
        **params,
    ) -> "BrowserStep":
        step = BrowserStep(action=action, params=params, description=description)
        self.steps.append(step)
        return step


@dataclass
class BrowserResult:
    """Final structured result returned by BrowserAgent.execute()."""
    task_id: str
    status: BrowserStatus
    steps_executed: int
    steps_succeeded: int
    steps_failed: int
    total_duration: float
    final_output: str
    step_outputs: List[dict] = field(default_factory=list)
    screenshot_paths: List[str] = field(default_factory=list)
    extracted_texts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[BrowserAgent] Task {self.task_id} | {self.status} | "
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
            "screenshot_paths": self.screenshot_paths,
            "extracted_texts": self.extracted_texts,
            "errors": self.errors,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Browser Planner  (natural-language → BrowserTask)
# ─────────────────────────────────────────────────────────────────────────────

class BrowserPlanner:
    """
    Converts a natural-language web request into a BrowserTask.

    Uses keyword heuristics.  Future: replace with LLM intent parsing.
    """

    # (keywords, action, extra_param_extractor)
    _RULES: List[tuple] = []

    def __init__(self) -> None:
        import re
        self._re = re

    def plan(self, request: str) -> BrowserTask:
        """Build a BrowserTask from a natural-language string."""
        import re
        lower = request.lower()
        task = BrowserTask(description=request)

        # ── Heuristic routing ─────────────────────────────────────────────

        # Always launch browser first
        task.add_step(BrowserAction.LAUNCH, "Launch browser", headless=True)

        # 1. Screenshot request
        if any(kw in lower for kw in ("screenshot", "capture screen", "take a screenshot")):
            if any(kw in lower for kw in ("search", "google", "find")):
                query = self._extract_query(request)
                task.add_step(BrowserAction.SEARCH, f"Search for '{query}'", query=query)
            elif url := self._extract_url(request):
                task.add_step(BrowserAction.OPEN_URL, f"Open {url}", url=url)
            task.add_step(BrowserAction.SCREENSHOT, "Capture screenshot")
            task.add_step(BrowserAction.CLOSE, "Close browser")
            return task

        # 2. Extract text request
        if any(kw in lower for kw in ("extract text", "get text", "read page", "scrape")):
            if url := self._extract_url(request):
                task.add_step(BrowserAction.OPEN_URL, f"Open {url}", url=url)
            elif any(kw in lower for kw in ("search", "google")):
                query = self._extract_query(request)
                task.add_step(BrowserAction.SEARCH, f"Search for '{query}'", query=query)
            task.add_step(BrowserAction.EXTRACT_TEXT, "Extract page text")
            task.add_step(BrowserAction.CLOSE, "Close browser")
            return task

        # 3. Download request
        if any(kw in lower for kw in ("download", "save file")):
            url = self._extract_url(request) or "https://example.com"
            save_path = self._extract_save_path(request) or "downloads/file"
            task.add_step(BrowserAction.OPEN_URL, f"Open {url}", url=url)
            task.add_step(BrowserAction.DOWNLOAD, "Download file",
                          selector_or_url=url, save_path=save_path)
            task.add_step(BrowserAction.CLOSE, "Close browser")
            return task

        # 4. Search request
        if any(kw in lower for kw in ("search", "google", "look up", "find online")):
            query = self._extract_query(request)
            task.add_step(BrowserAction.SEARCH, f"Search Google for '{query}'", query=query)
            task.add_step(BrowserAction.EXTRACT_TEXT, "Extract search results")
            task.add_step(BrowserAction.CLOSE, "Close browser")
            return task

        # 5. Plain URL open
        if url := self._extract_url(request):
            task.add_step(BrowserAction.OPEN_URL, f"Open {url}", url=url)
            task.add_step(BrowserAction.EXTRACT_TEXT, "Read page")
            task.add_step(BrowserAction.CLOSE, "Close browser")
            return task

        # 6. Generic: open google
        task.add_step(BrowserAction.SEARCH, "Search Google",
                      query=request.strip())
        task.add_step(BrowserAction.EXTRACT_TEXT, "Extract results")
        task.add_step(BrowserAction.CLOSE, "Close browser")
        return task

    # ── Private helpers ────────────────────────────────────────────────────

    def _extract_url(self, text: str) -> Optional[str]:
        import re
        match = re.search(r"https?://[^\s]+|www\.[^\s]+", text)
        if match:
            url = match.group(0).rstrip(".,;\"'")
            if not url.startswith("http"):
                url = "https://" + url
            return url
        return None

    def _extract_query(self, text: str) -> str:
        import re
        # Strip leading verb phrases
        cleaned = re.sub(
            r"(?i)^(search(?: for)?|google|look up|find(?: online)?|please)\s+",
            "", text.strip()
        )
        return cleaned or text.strip()

    def _extract_save_path(self, text: str) -> Optional[str]:
        import re
        match = re.search(r"(?:save|download|to)\s+['\"]?([^\s'\"]+\.\w+)['\"]?", text, re.IGNORECASE)
        return match.group(1) if match else None


# ─────────────────────────────────────────────────────────────────────────────
# Action Runner  (executes BrowserStep via BrowserTool)
# ─────────────────────────────────────────────────────────────────────────────

class ActionRunner:
    """
    Executes individual BrowserSteps through the BrowserTool adapter.

    Isolates retry logic and status tracking per step.
    Uses the existing BrowserTool.execute() interface so no Playwright
    code is duplicated here.
    """

    def __init__(
        self,
        browser_tool: Any,
        progress_callback: Optional[Callable] = None,
    ) -> None:
        self.browser_tool = browser_tool
        self.progress_callback = progress_callback

    def run(self, step: BrowserStep) -> str:
        """Execute a BrowserStep with retry on transient failure."""
        attempt = 0
        while attempt <= step.max_retries:
            attempt += 1
            step.started_at = time.time()
            step.status = BrowserStatus.RUNNING if attempt == 1 else BrowserStatus.RETRYING
            self._notify(step)

            try:
                # Build kwargs for BrowserTool.execute()
                kwargs = {"action": step.action.value, **step.params}
                output: str = self.browser_tool.execute(**kwargs)

                step.output = output
                step.finished_at = time.time()

                # BrowserTool signals failure with "Failure:" prefix
                if output.lower().startswith("failure"):
                    raise RuntimeError(output)

                step.status = BrowserStatus.SUCCESS
                self._notify(step)
                return output

            except Exception as e:
                step.error = str(e)
                step.retry_count = attempt
                logger.warning(
                    "[BrowserAgent] Step '%s' attempt %d/%d failed: %s",
                    step.description, attempt, step.max_retries + 1, e
                )
                if attempt > step.max_retries:
                    step.status = BrowserStatus.FAILED
                    step.finished_at = time.time()
                    step.output = f"Failed after {attempt} attempt(s): {e}"
                    self._notify(step)
                    return step.output
                time.sleep(0.5 * attempt)

        # Should not reach
        step.status = BrowserStatus.FAILED
        return step.output or "Unknown failure."

    def _notify(self, step: BrowserStep) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(step)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Result Builder
# ─────────────────────────────────────────────────────────────────────────────

class ResultBuilder:
    """Aggregates executed BrowserTask steps into a BrowserResult."""

    def build(self, task: BrowserTask, total_duration: float) -> BrowserResult:
        succeeded = [s for s in task.steps if s.status == BrowserStatus.SUCCESS]
        failed    = [s for s in task.steps if s.status == BrowserStatus.FAILED]

        # Collect special outputs
        screenshot_paths: List[str] = []
        extracted_texts:  List[str] = []
        errors:           List[str] = []
        step_outputs:     List[dict] = []

        for step in task.steps:
            step_outputs.append({
                "action":      step.action.value,
                "description": step.description,
                "status":      str(step.status),
                "output":      step.output,
                "duration":    step.duration,
                "retries":     step.retry_count,
            })
            if step.error:
                errors.append(f"[{step.action.value}] {step.error}")
            if step.action == BrowserAction.SCREENSHOT and step.output and "Success" in step.output:
                # Extract path from "Success: Screenshot saved to screenshots/..."
                import re
                m = re.search(r"screenshots[^\s]+", step.output)
                if m:
                    screenshot_paths.append(m.group(0))
            if step.action == BrowserAction.EXTRACT_TEXT and step.output:
                extracted_texts.append(step.output)

        # Derive final_output: last successful extract_text or last step output
        final_output = ""
        for step in reversed(task.steps):
            if step.output and step.status == BrowserStatus.SUCCESS:
                final_output = step.output
                break

        overall_status = (
            BrowserStatus.SUCCESS if not failed else
            BrowserStatus.FAILED  if not succeeded else
            BrowserStatus.FAILED   # partial failure still counts as failed
        )

        return BrowserResult(
            task_id=task.task_id,
            status=overall_status,
            steps_executed=len(task.steps),
            steps_succeeded=len(succeeded),
            steps_failed=len(failed),
            total_duration=total_duration,
            final_output=final_output,
            step_outputs=step_outputs,
            screenshot_paths=screenshot_paths,
            extracted_texts=extracted_texts,
            errors=errors,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Browser Agent
# ─────────────────────────────────────────────────────────────────────────────

class BrowserAgent:
    """
    Nova's autonomous web operator.

    Accepts natural-language web requests, plans a BrowserTask, executes
    each step through the existing BrowserTool adapter, and returns a
    structured BrowserResult.

    Usage
    -----
    agent = BrowserAgent()
    result = agent.execute("Search Google for Nova AI assistant")

    With custom tool (testing / DI):
    agent = BrowserAgent(browser_tool=mock_tool)

    Integration with ExecutiveAgent
    --------------------------------
    ExecutiveAgent.StepExecutor routes NAVIGATION intent steps to
    BrowserAgent.execute(step.input_data) instead of NovaEngine.
    """

    def __init__(
        self,
        browser_tool: Optional[Any] = None,
        progress_callback: Optional[Callable[[BrowserStep], None]] = None,
        max_step_retries: int = 2,
    ) -> None:
        """
        Args:
            browser_tool:       An instance exposing .execute(**kwargs) → str.
                                Defaults to BrowserTool from tools.browser_tool.
            progress_callback:  Called with each BrowserStep as it progresses.
            max_step_retries:   Default max retries applied to each step.
        """
        if browser_tool is None:
            try:
                from tools.browser_tool import BrowserTool
                browser_tool = BrowserTool()
            except Exception as e:
                logger.warning("[BrowserAgent] Could not load BrowserTool: %s. Using stub.", e)
                browser_tool = _StubBrowserTool()

        self.browser_tool      = browser_tool
        self.max_step_retries  = max_step_retries
        self.planner           = BrowserPlanner()
        self.runner            = ActionRunner(browser_tool, progress_callback=progress_callback)
        self.result_builder    = ResultBuilder()

        logger.info("[BrowserAgent] Initialized with tool: %s", type(browser_tool).__name__)

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(self, request: str) -> BrowserResult:
        """
        Full pipeline: plan → execute steps → return BrowserResult.

        Args:
            request: Natural-language web request.

        Returns:
            BrowserResult with final output, screenshots, and statistics.
        """
        started = time.time()
        task = self.planner.plan(request)
        logger.info(
            "[BrowserAgent] Task %s: '%s' — %d step(s)",
            task.task_id, task.description[:60], len(task.steps)
        )
        self._run_steps(task)
        total_duration = time.time() - started
        result = self.result_builder.build(task, total_duration)
        logger.info("[BrowserAgent] %s", result.summary())
        return result

    def execute_task(self, task: BrowserTask) -> BrowserResult:
        """
        Execute a pre-built BrowserTask directly (programmatic API).

        Useful when the caller constructs the task with precise steps
        rather than going through the natural-language planner.

        Args:
            task: A fully constructed BrowserTask.

        Returns:
            BrowserResult.
        """
        started = time.time()
        logger.info(
            "[BrowserAgent] Executing pre-built task %s — %d step(s)",
            task.task_id, len(task.steps)
        )
        self._run_steps(task)
        total_duration = time.time() - started
        result = self.result_builder.build(task, total_duration)
        logger.info("[BrowserAgent] %s", result.summary())
        return result

    def _run_steps(self, task: BrowserTask) -> None:
        """
        Execute all steps in a task with halt-on-failure semantics.

        On a non-CLOSE step failure:
          - Marks all subsequent non-CLOSE steps as CANCELLED.
          - Still executes any CLOSE steps to ensure browser cleanup.
        """
        failed = False
        for step in task.steps:
            if failed and step.action != BrowserAction.CLOSE:
                step.status = BrowserStatus.CANCELLED
                step.output = "Cancelled: prior step failed."
                continue

            step.max_retries = self.max_step_retries
            self.runner.run(step)

            if step.status == BrowserStatus.FAILED and step.action != BrowserAction.CLOSE:
                logger.warning(
                    "[BrowserAgent] Step '%s' failed — cancelling non-CLOSE remaining steps.",
                    step.description
                )
                failed = True

    def handle_input(self, user_input: str, stream: bool = False):
        """
        Compatibility shim — allows BrowserAgent to be used wherever
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


# ─────────────────────────────────────────────────────────────────────────────
# Stub Browser Tool (used when Playwright is unavailable)
# ─────────────────────────────────────────────────────────────────────────────

class _StubBrowserTool:
    """
    Minimal no-op browser tool used when Playwright is not installed.
    Returns Success: messages so the BrowserAgent pipeline still completes.
    """

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        if action == "launch_browser":
            return "Success: Browser launched (stub mode — Playwright not available)."
        if action == "open_url":
            return f"Success: Opened {kwargs.get('url', 'URL')} (stub)."
        if action == "search_google":
            return f"Success: Searched for '{kwargs.get('query', '')}' (stub)."
        if action == "extract_text":
            return "Success: Extracted text (stub): [No real browser available]"
        if action == "capture_screenshot":
            return "Success: Screenshot captured (stub)."
        if action == "close_browser":
            return "Success: Browser closed (stub)."
        return f"Success: Action '{action}' executed (stub)."
