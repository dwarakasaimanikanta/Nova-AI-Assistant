"""
agents/workspace_agent.py
-------------------------
WorkspaceAgent is responsible for all local filesystem and project workspace operations.

It is designed to be injected dynamically/compatibly into the ExecutiveAgent / StepExecutor
pipeline without modifying core/executive_agent.py directly.

Architecture
------------
WorkspaceAgent uses a programmatic Planner, ActionRunner, and ResultBuilder:

             User Request
                  ↓
       ExecutiveAgent (monkey-patched routing)
                  ↓
        WorkspaceAgent.execute()
                  ↓
       WorkspaceTask → ActionRunner
                  ↓
           Python filesystem APIs
                  ↓
            WorkspaceResult
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceAction(str, Enum):
    # Projects
    CREATE_PROJECT    = "create_project"
    OPEN_PROJECT      = "open_project"
    DELETE_PROJECT    = "delete_project"
    ARCHIVE_PROJECT   = "archive_project"

    # Folders
    CREATE_FOLDER     = "create_folder"
    RENAME_FOLDER     = "rename_folder"
    MOVE_FOLDER       = "move_folder"
    DELETE_FOLDER     = "delete_folder"

    # Files
    CREATE_FILE       = "create_file"
    READ_FILE         = "read_file"
    WRITE_FILE        = "write_file"
    APPEND_FILE       = "append_file"
    RENAME_FILE       = "rename_file"
    COPY_FILE         = "copy_file"
    MOVE_FILE         = "move_file"
    DELETE_FILE       = "delete_file"

    # Workspace
    SEARCH            = "search"
    LIST_DIR          = "list_dir"
    CREATE_TEMPLATES  = "create_templates"
    ZIP               = "zip"
    UNZIP             = "unzip"

    # Development
    OPEN_VS_CODE      = "open_vs_code"
    OPEN_TERMINAL     = "open_terminal"
    OPEN_EXPLORER     = "open_explorer"


class WorkspaceStatus(str, Enum):
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
class WorkspaceStep:
    """One atomic Workspace action inside a WorkspaceTask."""
    action: WorkspaceAction
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    max_retries: int = 2
    output: Optional[str] = None
    status: WorkspaceStatus = WorkspaceStatus.PENDING
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
        return self.status == WorkspaceStatus.SUCCESS


@dataclass
class WorkspaceTask:
    """An ordered list of WorkspaceSteps that fulfil a workspace request."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    steps: List[WorkspaceStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    cancelled: bool = False

    def add_step(
        self,
        step_action: WorkspaceAction,
        description: str = "",
        **params,
    ) -> WorkspaceStep:
        step = WorkspaceStep(action=step_action, params=params, description=description)
        self.steps.append(step)
        return step


@dataclass
class WorkspaceResult:
    """Structured result returned by WorkspaceAgent after task execution."""
    task_id: str
    status: WorkspaceStatus
    steps_executed: int
    steps_succeeded: int
    steps_failed: int
    total_duration: float
    final_output: str
    step_outputs: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[WorkspaceAgent] Task {self.task_id} | {self.status} | "
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
# Workspace Planner
# ─────────────────────────────────────────────────────────────────────────────

class WorkspacePlanner:
    """
    Converts a natural-language workspace request into a WorkspaceTask.

    Uses keyword heuristics for routing.
    """

    def plan(self, request: str) -> WorkspaceTask:
        lower = request.lower().strip()
        task = WorkspaceTask(description=request)

        # 1. Projects
        if "create project" in lower:
            name = self._extract_project_name(request)
            task.add_step(WorkspaceAction.CREATE_PROJECT, f"Create project '{name}'", project_name=name)
        elif "open project" in lower:
            name = self._extract_project_name(request)
            task.add_step(WorkspaceAction.OPEN_PROJECT, f"Open project '{name}'", project_name=name)
        elif "delete project" in lower:
            name = self._extract_project_name(request)
            task.add_step(WorkspaceAction.DELETE_PROJECT, f"Delete project '{name}'", project_name=name)
        elif "archive project" in lower:
            name = self._extract_project_name(request)
            task.add_step(WorkspaceAction.ARCHIVE_PROJECT, f"Archive project '{name}'", project_name=name)

        # 2. Folders
        elif "create folder" in lower or "create directory" in lower or "mkdir" in lower:
            path = self._extract_path(request)
            task.add_step(WorkspaceAction.CREATE_FOLDER, f"Create folder '{path}'", path=path)
        elif "rename folder" in lower or "rename directory" in lower:
            src, dest = self._extract_src_dest(request)
            task.add_step(WorkspaceAction.RENAME_FOLDER, f"Rename folder '{src}' to '{dest}'", src=src, dest=dest)
        elif "move folder" in lower or "move directory" in lower:
            src, dest = self._extract_src_dest(request)
            task.add_step(WorkspaceAction.MOVE_FOLDER, f"Move folder '{src}' to '{dest}'", src=src, dest=dest)
        elif "delete folder" in lower or "delete directory" in lower or "rmdir" in lower:
            path = self._extract_path(request)
            task.add_step(WorkspaceAction.DELETE_FOLDER, f"Delete folder '{path}'", path=path)

        # 3. Files
        elif "create file" in lower or "touch" in lower:
            path = self._extract_path(request)
            task.add_step(WorkspaceAction.CREATE_FILE, f"Create file '{path}'", path=path)
        elif "read file" in lower or "cat" in lower:
            path = self._extract_path(request)
            task.add_step(WorkspaceAction.READ_FILE, f"Read file '{path}'", path=path)
        elif "write file" in lower or "write to file" in lower:
            path = self._extract_path(request)
            content = self._extract_content(request)
            task.add_step(WorkspaceAction.WRITE_FILE, f"Write to '{path}'", path=path, content=content)
        elif "append file" in lower or "append to file" in lower:
            path = self._extract_path(request)
            content = self._extract_content(request)
            task.add_step(WorkspaceAction.APPEND_FILE, f"Append to '{path}'", path=path, content=content)
        elif "rename file" in lower:
            src, dest = self._extract_src_dest(request)
            task.add_step(WorkspaceAction.RENAME_FILE, f"Rename file '{src}' to '{dest}'", src=src, dest=dest)
        elif "copy file" in lower or "cp " in lower:
            src, dest = self._extract_src_dest(request)
            task.add_step(WorkspaceAction.COPY_FILE, f"Copy file '{src}' to '{dest}'", src=src, dest=dest)
        elif "move file" in lower or "mv " in lower:
            src, dest = self._extract_src_dest(request)
            task.add_step(WorkspaceAction.MOVE_FILE, f"Move file '{src}' to '{dest}'", src=src, dest=dest)
        elif "delete file" in lower or "rm " in lower:
            path = self._extract_path(request)
            task.add_step(WorkspaceAction.DELETE_FILE, f"Delete file '{path}'", path=path)

        # 4. Workspace Action
        elif "search workspace" in lower or "search file" in lower or "find in files" in lower:
            query = self._extract_query(request)
            task.add_step(WorkspaceAction.SEARCH, f"Search workspace for '{query}'", query=query)
        elif "list directory" in lower or "list files" in lower or "ls " in lower or lower == "ls" or lower == "dir":
            path = self._extract_path(request) or "."
            task.add_step(WorkspaceAction.LIST_DIR, f"List directory '{path}'", path=path)
        elif "create template" in lower or "scaffold" in lower:
            template_type = self._extract_template_type(request)
            task.add_step(WorkspaceAction.CREATE_TEMPLATES, f"Create template '{template_type}'", template_type=template_type)
        elif "unzip" in lower:
            src, dest = self._extract_src_dest(request)
            task.add_step(WorkspaceAction.UNZIP, f"Unzip '{src}' to '{dest}'", src=src, dest=dest)
        elif "zip" in lower:
            src, dest = self._extract_src_dest(request)
            task.add_step(WorkspaceAction.ZIP, f"Zip '{src}' to '{dest}'", src=src, dest=dest)

        # 5. Development Utilities
        elif "open vs code" in lower or "open code" in lower or "vs code" in lower:
            path = self._extract_path(request) or "."
            task.add_step(WorkspaceAction.OPEN_VS_CODE, f"Open VS Code in '{path}'", path=path)
        elif "open terminal" in lower or "start terminal" in lower:
            path = self._extract_path(request) or "."
            task.add_step(WorkspaceAction.OPEN_TERMINAL, f"Open terminal in '{path}'", path=path)
        elif "open file explorer" in lower or "open explorer" in lower or "show in explorer" in lower:
            path = self._extract_path(request) or "."
            task.add_step(WorkspaceAction.OPEN_EXPLORER, f"Open Explorer in '{path}'", path=path)

        else:
            # Fallback to list directory
            task.add_step(WorkspaceAction.LIST_DIR, "List directory '.'", path=".")

        return task

    # ── Private extraction helpers ─────────────────────────────────────────

    def _extract_project_name(self, text: str) -> str:
        match = re.search(r"(?:project|named|called)\s+['\"]?([A-Za-z0-9_\-]+)['\"]?", text, re.IGNORECASE)
        return match.group(1).strip() if match else "my_project"

    def _extract_path(self, text: str) -> str:
        # Match quoted string or last word
        match = re.search(r"['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1).strip()
        words = text.split()
        if len(words) > 2:
            last = words[-1].rstrip(".,;\"'")
            if "." in last or "/" in last or "\\" in last or len(last) > 2:
                return last
        return ""

    def _extract_src_dest(self, text: str) -> tuple[str, str]:
        # Extract quoted paths first
        quotes = re.findall(r"['\"]([^'\"]+)['\"]", text)
        if len(quotes) >= 2:
            return quotes[0], quotes[1]
        # Regex match src/dest keywords
        match = re.search(r"(?:from|copy|move|zip|unzip)\s+(\S+)\s+(?:to|as)\s+(\S+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        words = text.split()
        if len(words) >= 4:
            return words[-2], words[-1]
        return "", ""

    def _extract_content(self, text: str) -> str:
        match = re.search(r"(?:content|saying|text)[:\s]+(.*)$", text, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip('"\'')
        quotes = re.findall(r"['\"]([^'\"]+)['\"]", text)
        if len(quotes) >= 2:
            return quotes[-1]
        return ""

    def _extract_query(self, text: str) -> str:
        match = re.search(r"(?:for|query)[:\s]+['\"]?([^'\"]+)['\"]?", text, re.IGNORECASE)
        return match.group(1).strip() if match else text.strip()

    def _extract_template_type(self, text: str) -> str:
        for t in ("python", "web", "html", "react", "fastapi"):
            if t in text.lower():
                return t
        return "python"


# ─────────────────────────────────────────────────────────────────────────────
# Action Runner
# ─────────────────────────────────────────────────────────────────────────────

class ActionRunner:
    """Executes individual WorkspaceSteps thread-safely."""

    def __init__(self, workspace_root: Path, progress_callback: Optional[Callable] = None):
        self.workspace_root = workspace_root
        self.progress_callback = progress_callback
        self._lock = threading.Lock()

    def run(self, step: WorkspaceStep, cancel_event: Optional[threading.Event] = None) -> str:
        attempt = 0
        while attempt <= step.max_retries:
            if cancel_event and cancel_event.is_set():
                step.status = WorkspaceStatus.CANCELLED
                step.output = "Cancelled by user."
                self._notify(step)
                return step.output

            attempt += 1
            step.started_at = time.time()
            step.status = WorkspaceStatus.RUNNING if attempt == 1 else WorkspaceStatus.RETRYING
            self._notify(step)

            try:
                with self._lock:
                    output = self._execute_action(step.action, step.params)
                
                step.output = output
                step.status = WorkspaceStatus.SUCCESS
                step.finished_at = time.time()
                self._notify(step)
                return output

            except Exception as e:
                step.error = str(e)
                step.retry_count = attempt
                logger.warning(
                    "[WorkspaceAgent] Step '%s' attempt %d/%d failed: %s",
                    step.description, attempt, step.max_retries + 1, e
                )
                if attempt > step.max_retries:
                    step.status = WorkspaceStatus.FAILED
                    step.finished_at = time.time()
                    step.output = f"Failure: {e}"
                    self._notify(step)
                    return step.output
                time.sleep(0.3 * attempt)

        step.status = WorkspaceStatus.FAILED
        return step.output or "Unknown failure."

    def _execute_action(self, action: WorkspaceAction, params: Dict[str, Any]) -> str:
        # Projects
        if action == WorkspaceAction.CREATE_PROJECT:
            name = params["project_name"]
            p = self.workspace_root / name
            p.mkdir(parents=True, exist_ok=True)
            (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")
            return f"Success: Project '{name}' created at '{p}'."

        elif action == WorkspaceAction.OPEN_PROJECT:
            name = params["project_name"]
            p = self.workspace_root / name
            if not p.exists():
                raise FileNotFoundError(f"Project '{name}' does not exist.")
            return f"Success: Opened project '{name}'."

        elif action == WorkspaceAction.DELETE_PROJECT:
            name = params["project_name"]
            p = self.workspace_root / name
            if p.exists():
                shutil.rmtree(p)
                return f"Success: Deleted project '{name}'."
            return f"Success: Project '{name}' did not exist."

        elif action == WorkspaceAction.ARCHIVE_PROJECT:
            name = params["project_name"]
            p = self.workspace_root / name
            if not p.exists():
                raise FileNotFoundError(f"Project '{name}' does not exist.")
            archive_path = self.workspace_root / f"{name}_archive"
            shutil.make_archive(str(archive_path), 'zip', root_dir=p)
            return f"Success: Archived project '{name}' to '{archive_path}.zip'."

        # Folders
        elif action == WorkspaceAction.CREATE_FOLDER:
            path = self._resolve(params["path"])
            path.mkdir(parents=True, exist_ok=True)
            return f"Success: Folder created at '{path}'."

        elif action == WorkspaceAction.RENAME_FOLDER or action == WorkspaceAction.RENAME_FILE:
            src = self._resolve(params["src"])
            dest = self._resolve(params["dest"])
            if not src.exists():
                raise FileNotFoundError(f"Source path '{src}' does not exist.")
            src.rename(dest)
            return f"Success: Renamed '{src}' to '{dest}'."

        elif action == WorkspaceAction.MOVE_FOLDER or action == WorkspaceAction.MOVE_FILE:
            src = self._resolve(params["src"])
            dest = self._resolve(params["dest"])
            if not src.exists():
                raise FileNotFoundError(f"Source path '{src}' does not exist.")
            shutil.move(src, dest)
            return f"Success: Moved '{src}' to '{dest}'."

        elif action == WorkspaceAction.DELETE_FOLDER:
            path = self._resolve(params["path"])
            if path.exists():
                shutil.rmtree(path)
                return f"Success: Deleted folder recursively at '{path}'."
            return f"Success: Folder at '{path}' did not exist."

        # Files
        elif action == WorkspaceAction.CREATE_FILE:
            path = self._resolve(params["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            return f"Success: File created at '{path}'."

        elif action == WorkspaceAction.READ_FILE:
            path = self._resolve(params["path"])
            if not path.is_file():
                raise FileNotFoundError(f"File '{path}' does not exist.")
            return path.read_text(encoding="utf-8")

        elif action == WorkspaceAction.WRITE_FILE:
            path = self._resolve(params["path"])
            content = params.get("content", "")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Success: Wrote to file '{path}'."

        elif action == WorkspaceAction.APPEND_FILE:
            path = self._resolve(params["path"])
            content = params.get("content", "")
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"Success: Appended to file '{path}'."

        elif action == WorkspaceAction.COPY_FILE:
            src = self._resolve(params["src"])
            dest = self._resolve(params["dest"])
            if not src.exists():
                raise FileNotFoundError(f"Source file '{src}' does not exist.")
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            return f"Success: Copied '{src}' to '{dest}'."

        elif action == WorkspaceAction.DELETE_FILE:
            path = self._resolve(params["path"])
            if path.is_file():
                path.unlink()
                return f"Success: Deleted file '{path}'."
            return f"Success: File at '{path}' did not exist."

        # Workspace
        elif action == WorkspaceAction.SEARCH:
            query = params["query"].lower()
            results = []
            for root, _, files in os.walk(self.workspace_root):
                for file in files:
                    fp = Path(root) / file
                    try:
                        content = fp.read_text(encoding="utf-8", errors="ignore")
                        if query in content.lower():
                            results.append(str(fp.relative_to(self.workspace_root)))
                    except Exception:
                        pass
            if not results:
                return f"No occurrences of '{query}' found in files."
            return "Matches found in:\n" + "\n".join(results)

        elif action == WorkspaceAction.LIST_DIR:
            path = self._resolve(params["path"])
            if not path.is_dir():
                raise NotADirectoryError(f"'{path}' is not a directory.")
            items = os.listdir(path)
            lines = []
            for item in items:
                p = path / item
                suffix = "/" if p.is_dir() else ""
                lines.append(f"  • {item}{suffix}")
            return f"Directory contents of '{path}':\n" + "\n".join(lines) if lines else f"Directory '{path}' is empty."

        elif action == WorkspaceAction.CREATE_TEMPLATES:
            t_type = params["template_type"]
            p = self.workspace_root / f"template_{t_type}"
            p.mkdir(parents=True, exist_ok=True)
            if t_type == "python":
                (p / "main.py").write_text("def main():\n    print('Hello World')\nif __name__ == '__main__':\n    main()", encoding="utf-8")
            elif t_type == "web":
                (p / "index.html").write_text("<!DOCTYPE html><html><body><h1>Hello</h1></body></html>", encoding="utf-8")
            return f"Success: Scaffolded '{t_type}' template in '{p}'."

        elif action == WorkspaceAction.ZIP:
            src = self._resolve(params["src"])
            dest = self._resolve(params["dest"])
            shutil.make_archive(str(dest).replace(".zip", ""), 'zip', root_dir=src)
            return f"Success: Zipped '{src}' to '{dest}'."

        elif action == WorkspaceAction.UNZIP:
            src = self._resolve(params["src"])
            dest = self._resolve(params["dest"])
            with zipfile.ZipFile(src, 'r') as ref:
                ref.extractall(dest)
            return f"Success: Unzipped '{src}' to '{dest}'."

        # Development
        elif action == WorkspaceAction.OPEN_VS_CODE:
            path = self._resolve(params["path"])
            # Start VS Code in the background
            subprocess.Popen(["code", str(path)], shell=True)
            return f"Success: Opened VS Code in '{path}'."

        elif action == WorkspaceAction.OPEN_TERMINAL:
            path = self._resolve(params["path"])
            if sys.platform == "win32":
                subprocess.Popen(["start", "cmd"], shell=True, cwd=str(path))
            else:
                subprocess.Popen(["x-terminal-emulator"], shell=True, cwd=str(path))
            return f"Success: Opened terminal in '{path}'."

        elif action == WorkspaceAction.OPEN_EXPLORER:
            path = self._resolve(params["path"])
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(path)], shell=True)
            else:
                subprocess.Popen(["xdg-open", str(path)], shell=True)
            return f"Success: Opened file explorer in '{path}'."

        else:
            raise NotImplementedError(f"Action '{action}' is not supported.")

    def _resolve(self, path_str: str) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p
        return (self.workspace_root / p).resolve()

    def _notify(self, step: WorkspaceStep) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(step)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Result Builder
# ─────────────────────────────────────────────────────────────────────────────

class ResultBuilder:
    """Aggregates WorkspaceSteps into a WorkspaceResult."""

    def build(self, task: WorkspaceTask, total_duration: float) -> WorkspaceResult:
        succeeded = [s for s in task.steps if s.status == WorkspaceStatus.SUCCESS]
        failed    = [s for s in task.steps if s.status == WorkspaceStatus.FAILED]
        errors    = [f"[{s.action.value}] {s.error}" for s in task.steps if s.error]

        step_outputs = [
            {
                "action": s.action.value,
                "description": s.description,
                "status": str(s.status),
                "output": s.output,
                "duration": s.duration,
                "retries": s.retry_count,
            }
            for s in task.steps
        ]

        final_output = ""
        for s in reversed(task.steps):
            if s.output and s.status == WorkspaceStatus.SUCCESS:
                final_output = s.output
                break
        if not final_output and task.steps:
            final_output = task.steps[-1].output or ""

        overall_status = (
            WorkspaceStatus.CANCELLED if task.cancelled else
            WorkspaceStatus.SUCCESS if not failed else
            WorkspaceStatus.FAILED
        )

        return WorkspaceResult(
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
# Workspace Agent
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceAgent:
    """
    WorkspaceAgent is responsible for all local filesystem and project workspace operations.
    """

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        progress_callback: Optional[Callable[[WorkspaceStep], None]] = None,
        max_step_retries: int = 2,
    ) -> None:
        self.workspace_root   = workspace_root or Path.cwd()
        self.max_step_retries = max_step_retries
        self.planner          = WorkspacePlanner()
        self.runner           = ActionRunner(self.workspace_root, progress_callback=progress_callback)
        self.result_builder   = ResultBuilder()
        self._cancel_event    = threading.Event()

        logger.info("[WorkspaceAgent] Initialized in %s", self.workspace_root)

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(self, request: str) -> WorkspaceResult:
        self._cancel_event.clear()
        started = time.time()
        task = self.planner.plan(request)
        logger.info(
            "[WorkspaceAgent] Task %s: '%s' — %d step(s)",
            task.task_id, task.description[:60], len(task.steps)
        )
        self._run_steps(task)
        total_duration = time.time() - started
        result = self.result_builder.build(task, total_duration)
        logger.info("[WorkspaceAgent] %s", result.summary())
        return result

    def execute_task(self, task: WorkspaceTask) -> WorkspaceResult:
        self._cancel_event.clear()
        started = time.time()
        logger.info(
            "[WorkspaceAgent] Executing pre-built task %s — %d step(s)",
            task.task_id, len(task.steps)
        )
        self._run_steps(task)
        total_duration = time.time() - started
        result = self.result_builder.build(task, total_duration)
        logger.info("[WorkspaceAgent] %s", result.summary())
        return result

    def cancel(self) -> None:
        self._cancel_event.set()
        logger.info("[WorkspaceAgent] Cancellation signal sent.")

    def handle_input(self, user_input: str, stream: bool = False):
        result = self.execute(user_input)
        response = result.final_output or result.summary()
        if stream:
            def _gen():
                yield response
            return _gen()
        return response

    # ── Internal ───────────────────────────────────────────────────────────

    def _run_steps(self, task: WorkspaceTask) -> None:
        failed = False
        for step in task.steps:
            if failed or (self._cancel_event.is_set()):
                step.status = WorkspaceStatus.CANCELLED
                step.output = "Cancelled: prior step failed or user cancelled."
                if self._cancel_event.is_set():
                    task.cancelled = True
                continue

            step.max_retries = self.max_step_retries
            self.runner.run(step, cancel_event=self._cancel_event)

            if step.status == WorkspaceStatus.FAILED:
                logger.warning(
                    "[WorkspaceAgent] Step '%s' failed — cancelling remaining steps.",
                    step.description
                )
                failed = True


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Runtime Injection into ExecutiveAgent & StepExecutor (Monkey Patch)
# ─────────────────────────────────────────────────────────────────────────────

def _inject_workspace_routing() -> None:
    """
    Dynamically patches StepExecutor and ExecutiveAgent classes so that
    if a WorkspaceAgent instance is injected, it handles workspace intents.
    """
    from core.executive_agent import StepExecutor, ExecutiveAgent, IntentType, ExecutionStatus

    # 1. Modify StepExecutor.__init__ to accept and store workspace_agent
    orig_step_init = StepExecutor.__init__

    def patched_step_init(self, *args, **kwargs):
        # Extract workspace_agent if passed
        self.workspace_agent = kwargs.pop("workspace_agent", None)
        orig_step_init(self, *args, **kwargs)

    StepExecutor.__init__ = patched_step_init

    # 2. Modify StepExecutor.execute to route Workspace actions dynamically
    orig_step_execute = StepExecutor.execute

    def patched_step_execute(self, step, cancel_event=None):
        # We can dynamically identify workspace operations by running the planner
        # or checking keywords/intents. If the workspace_agent is present:
        if getattr(self, "workspace_agent", None) is not None:
            # Check if this input matches workspace intents or keywords
            analyzer = getattr(self, "intent_analyzer", None)
            intent = analyzer.analyze(step.input_data) if analyzer else None

            # Or perform keyword heuristic match
            is_workspace = False
            lower = step.input_data.lower()
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

            if is_workspace:
                try:
                    result = self.workspace_agent.execute(step.input_data)
                    if result.status == WorkspaceStatus.SUCCESS:
                        step.output_data = result.final_output
                        step.status = ExecutionStatus.SUCCESS
                        step.finished_at = time.time()
                        self._report(step)
                        return result.final_output
                    else:
                        logger.warning("[ExecutiveAgent] WorkspaceAgent step failed. Falling back to NovaEngine.")
                except Exception as e:
                    logger.exception("[ExecutiveAgent] Exception in WorkspaceAgent. Falling back to NovaEngine: %s", e)

        # Fall back to original executor logic
        return orig_step_execute(self, step, cancel_event)

    StepExecutor.execute = patched_step_execute

    # 3. Modify ExecutiveAgent.__init__ to accept workspace_agent
    orig_exec_init = ExecutiveAgent.__init__

    def patched_exec_init(self, *args, **kwargs):
        workspace_agent = kwargs.pop("workspace_agent", None)
        orig_exec_init(self, *args, **kwargs)
        # Propagate it to StepExecutor
        self.step_executor.workspace_agent = workspace_agent

    ExecutiveAgent.__init__ = patched_exec_init


# Auto-inject on import
try:
    _inject_workspace_routing()
    logger.info("[WorkspaceAgent] Successfully injected workspace routing into ExecutiveAgent.")
except Exception as injection_err:
    logger.error("[WorkspaceAgent] Failed to inject workspace routing: %s", injection_err)
