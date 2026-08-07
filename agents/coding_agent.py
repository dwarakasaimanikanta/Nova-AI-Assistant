"""
agents/coding_agent.py
----------------------
The Coding Agent is a specialised sub-agent that handles software development
tasks delegated by the ExecutiveAgent.

Responsibilities
----------------
- Receive an ExecutionPlan or a plain natural-language coding request.
- Parse the project type and target directory from the request.
- Generate source files and directory structures for supported project types.
- Modify existing source files with targeted patch operations.
- Detect compilation / runtime failures via subprocess execution.
- Request retries with a configurable back-off strategy.
- Report structured progress via CodingProgress objects.

Supported project types (via ProjectProvider interface)
-------------------------------------------------------
- Python          (bare script / package)
- Flask           (Python web server)
- FastAPI         (Python async web server)
- HTML/CSS/JS     (static front-end)
- React           (Node/NPM front-end)
- Node.js         (Express back-end)

NOT implemented here
--------------------
- Deployment
- Git operations
- Cloud/container provisioning
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class ProjectType(str, Enum):
    PYTHON  = "python"
    FLASK   = "flask"
    FASTAPI = "fastapi"
    HTML    = "html"
    REACT   = "react"
    NODEJS  = "nodejs"
    UNKNOWN = "unknown"


class CodingStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    RETRYING  = "RETRYING"
    CANCELLED = "CANCELLED"


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GeneratedFile:
    """Represents a file that was written (or would be written) to disk."""
    path: Path
    content: str
    overwritten: bool = False


@dataclass
class CodingProgress:
    """Structured progress update emitted during coding task execution."""
    task_id: str
    status: CodingStatus
    message: str
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": str(self.status),
            "message": self.message,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "errors": self.errors,
        }


@dataclass
class CodingResult:
    """Final result returned after a CodingAgent task completes."""
    task_id: str
    status: CodingStatus
    project_type: ProjectType
    root_dir: Path
    generated_files: List[GeneratedFile] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    total_duration: float = 0.0
    retry_count: int = 0

    def summary(self) -> str:
        files = [str(f.path) for f in self.generated_files]
        status_str = str(self.status)
        return (
            f"[CodingAgent] Task {self.task_id} | {status_str} | "
            f"Project: {self.project_type.value} | "
            f"Root: {self.root_dir} | "
            f"Files: {len(files)}"
        )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": str(self.status),
            "project_type": self.project_type.value,
            "root_dir": str(self.root_dir),
            "files_created": [str(f.path) for f in self.generated_files if not f.overwritten],
            "files_modified": [str(f.path) for f in self.generated_files if f.overwritten],
            "errors": self.errors,
            "total_duration": self.total_duration,
            "retry_count": self.retry_count,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Project Provider Interface
# ─────────────────────────────────────────────────────────────────────────────

class ProjectProvider(ABC):
    """Abstract base for project-type-specific file generators."""

    @property
    @abstractmethod
    def project_type(self) -> ProjectType:
        ...

    @abstractmethod
    def generate(self, root: Path, project_name: str, **options) -> List[GeneratedFile]:
        """Generate all project files under `root` and return the list."""
        ...

    # ── shared helpers ─────────────────────────────────────────────────────

    @staticmethod
    def write_file(path: Path, content: str) -> GeneratedFile:
        """Create parent dirs, write content, return GeneratedFile."""
        path.parent.mkdir(parents=True, exist_ok=True)
        overwritten = path.exists()
        path.write_text(content, encoding="utf-8")
        logger.debug("[CodingAgent] Wrote %s (%s)", path, "overwrite" if overwritten else "new")
        return GeneratedFile(path=path, content=content, overwritten=overwritten)


# ─────────────────────────────────────────────────────────────────────────────
# Built-in Project Providers
# ─────────────────────────────────────────────────────────────────────────────

class PythonProvider(ProjectProvider):
    """Generates a minimal Python package / script structure."""

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.PYTHON

    def generate(self, root: Path, project_name: str, **options) -> List[GeneratedFile]:
        safe = _safe_name(project_name)
        files: List[GeneratedFile] = []

        files.append(self.write_file(root / f"{safe}.py", _PYTHON_MAIN.format(name=safe)))
        files.append(self.write_file(root / "requirements.txt", "# Add dependencies here\n"))
        files.append(self.write_file(root / "README.md", f"# {project_name}\n\nA Python project.\n"))
        return files


class FlaskProvider(ProjectProvider):
    """Generates a minimal Flask application scaffold."""

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.FLASK

    def generate(self, root: Path, project_name: str, **options) -> List[GeneratedFile]:
        safe = _safe_name(project_name)
        files: List[GeneratedFile] = []

        files.append(self.write_file(root / "app.py", _FLASK_APP.format(name=safe)))
        files.append(self.write_file(root / "requirements.txt", "flask>=3.0\n"))
        files.append(self.write_file(root / "templates" / "index.html", _HTML_TEMPLATE.format(title=project_name)))
        files.append(self.write_file(root / "static" / "style.css", _CSS_BASE))
        files.append(self.write_file(root / "README.md", f"# {project_name}\n\nA Flask application.\n\n## Run\n\n```bash\npython app.py\n```\n"))
        return files


class FastAPIProvider(ProjectProvider):
    """Generates a minimal FastAPI application scaffold."""

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.FASTAPI

    def generate(self, root: Path, project_name: str, **options) -> List[GeneratedFile]:
        safe = _safe_name(project_name)
        files: List[GeneratedFile] = []

        files.append(self.write_file(root / "main.py", _FASTAPI_APP.format(name=safe)))
        files.append(self.write_file(root / "requirements.txt", "fastapi>=0.110\nuvicorn[standard]>=0.29\n"))
        files.append(self.write_file(root / "README.md", f"# {project_name}\n\nA FastAPI application.\n\n## Run\n\n```bash\nuvicorn main:app --reload\n```\n"))
        return files


class HTMLProvider(ProjectProvider):
    """Generates a static HTML/CSS/JS site."""

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.HTML

    def generate(self, root: Path, project_name: str, **options) -> List[GeneratedFile]:
        files: List[GeneratedFile] = []

        files.append(self.write_file(root / "index.html", _HTML_PAGE.format(title=project_name)))
        files.append(self.write_file(root / "css" / "style.css", _CSS_BASE))
        files.append(self.write_file(root / "js" / "main.js", _JS_MAIN.format(name=project_name)))
        files.append(self.write_file(root / "README.md", f"# {project_name}\n\nA static HTML/CSS/JS site.\n"))
        return files


class ReactProvider(ProjectProvider):
    """Generates a minimal React (Vite) project scaffold (no npm install)."""

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.REACT

    def generate(self, root: Path, project_name: str, **options) -> List[GeneratedFile]:
        safe = _safe_name(project_name)
        files: List[GeneratedFile] = []

        files.append(self.write_file(root / "package.json", _REACT_PACKAGE.format(name=safe)))
        files.append(self.write_file(root / "vite.config.js", _VITE_CONFIG))
        files.append(self.write_file(root / "index.html", _REACT_INDEX.format(name=project_name)))
        files.append(self.write_file(root / "src" / "main.jsx", _REACT_MAIN))
        files.append(self.write_file(root / "src" / "App.jsx", _REACT_APP.format(name=project_name)))
        files.append(self.write_file(root / "src" / "App.css", _CSS_BASE))
        files.append(self.write_file(root / "README.md", f"# {project_name}\n\nA React application.\n\n## Run\n\n```bash\nnpm install && npm run dev\n```\n"))
        return files


class NodeJSProvider(ProjectProvider):
    """Generates a minimal Node.js / Express server scaffold."""

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.NODEJS

    def generate(self, root: Path, project_name: str, **options) -> List[GeneratedFile]:
        safe = _safe_name(project_name)
        files: List[GeneratedFile] = []

        files.append(self.write_file(root / "package.json", _NODE_PACKAGE.format(name=safe)))
        files.append(self.write_file(root / "index.js", _NODE_SERVER.format(name=project_name)))
        files.append(self.write_file(root / "README.md", f"# {project_name}\n\nA Node.js Express server.\n\n## Run\n\n```bash\nnode index.js\n```\n"))
        return files


# ─────────────────────────────────────────────────────────────────────────────
# File Modifier
# ─────────────────────────────────────────────────────────────────────────────

class FileModifier:
    """
    Applies targeted modifications to existing source files.

    Supported operations:
    - append_lines(path, lines)   → append text at end of file
    - prepend_lines(path, lines)  → insert text at top of file
    - replace_block(path, old, new) → replace first occurrence of old block
    - insert_after(path, marker, lines) → insert after the first line matching marker
    """

    @staticmethod
    def append_lines(path: Path, lines: str) -> GeneratedFile:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        new_content = existing + "\n" + lines
        return ProjectProvider.write_file(path, new_content)

    @staticmethod
    def prepend_lines(path: Path, lines: str) -> GeneratedFile:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        new_content = lines + "\n" + existing
        return ProjectProvider.write_file(path, new_content)

    @staticmethod
    def replace_block(path: Path, old_block: str, new_block: str) -> GeneratedFile:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        new_content = existing.replace(old_block, new_block, 1)
        return ProjectProvider.write_file(path, new_content)

    @staticmethod
    def insert_after(path: Path, marker: str, lines: str) -> GeneratedFile:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        result_lines = []
        inserted = False
        for line in existing.splitlines(keepends=True):
            result_lines.append(line)
            if not inserted and marker in line:
                result_lines.append(lines if lines.endswith("\n") else lines + "\n")
                inserted = True
        new_content = "".join(result_lines)
        return ProjectProvider.write_file(path, new_content)


# ─────────────────────────────────────────────────────────────────────────────
# Syntax / Runtime Validator
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0


class CodeValidator:
    """
    Validates generated code by:
    - Syntax-checking Python files with `python -m py_compile`
    - Checking package.json validity for JS projects (JSON parse)
    - Running a user-supplied test command if provided
    """

    def validate_python_syntax(self, path: Path) -> ValidationResult:
        """Run py_compile on a single Python file."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                capture_output=True, text=True, timeout=15
            )
            return ValidationResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(success=False, stderr="Syntax check timed out.")
        except Exception as e:
            return ValidationResult(success=False, stderr=str(e))

    def validate_json(self, path: Path) -> ValidationResult:
        """Parse JSON file to check validity."""
        import json
        try:
            content = path.read_text(encoding="utf-8")
            json.loads(content)
            return ValidationResult(success=True)
        except Exception as e:
            return ValidationResult(success=False, stderr=str(e))

    def run_command(self, command: List[str], cwd: Path, timeout: int = 30) -> ValidationResult:
        """Run an arbitrary shell command and return results."""
        try:
            result = subprocess.run(
                command, capture_output=True, text=True,
                timeout=timeout, cwd=str(cwd)
            )
            return ValidationResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(success=False, stderr=f"Command timed out after {timeout}s.")
        except Exception as e:
            return ValidationResult(success=False, stderr=str(e))

    def validate_generated_files(self, files: List[GeneratedFile]) -> List[ValidationResult]:
        """Auto-validate each file based on its extension."""
        results = []
        for gf in files:
            path = gf.path
            if path.suffix == ".py":
                r = self.validate_python_syntax(path)
                if not r.success:
                    logger.warning("[CodingAgent] Syntax error in %s: %s", path, r.stderr)
                results.append(r)
            elif path.name in ("package.json",):
                r = self.validate_json(path)
                if not r.success:
                    logger.warning("[CodingAgent] JSON error in %s: %s", path, r.stderr)
                results.append(r)
        return results


# ─────────────────────────────────────────────────────────────────────────────
# Project Type Detector
# ─────────────────────────────────────────────────────────────────────────────

class ProjectTypeDetector:
    """
    Detects the target ProjectType from a natural-language request.

    Uses keyword matching; future: LLM classifier call.
    """

    _KEYWORDS: Dict[ProjectType, List[str]] = {
        ProjectType.FASTAPI: ["fastapi", "fast api", "async api", "pydantic api"],
        ProjectType.FLASK:   ["flask", "flask app", "flask server", "python web"],
        ProjectType.REACT:   ["react", "reactjs", "react app", "jsx", "vite"],
        ProjectType.NODEJS:  ["nodejs", "node.js", "node js", "express", "node server"],
        ProjectType.HTML:    ["html", "css", "javascript", "static site", "static page", "webpage", "web page"],
        ProjectType.PYTHON:  ["python", "script", "cli", "package", "module"],
    }

    def detect(self, text: str) -> ProjectType:
        lower = text.lower()
        # Check in priority order (more specific first)
        for ptype in [
            ProjectType.FASTAPI, ProjectType.FLASK,
            ProjectType.REACT, ProjectType.NODEJS,
            ProjectType.HTML, ProjectType.PYTHON,
        ]:
            if any(kw in lower for kw in self._KEYWORDS[ptype]):
                return ptype
        return ProjectType.PYTHON   # Default to bare Python


class ProjectNameExtractor:
    """Extracts a project name from a natural-language request."""

    _PATTERNS = [
        r"(?:called|named|name[d]?\s+(?:it|the\s+project)?\s+)['\"]?([A-Za-z0-9_\- ]+)['\"]?",
        r"(?:create|build|generate|make)\s+(?:a\s+)?(?:[A-Za-z]+\s+)?(?:app|project|site|server|api|script)\s+['\"]?([A-Za-z0-9_\- ]+)['\"]?",
        r"(?:project|app|application)\s+['\"]([A-Za-z0-9_\- ]+)['\"]",
    ]

    def extract(self, text: str) -> str:
        for pattern in self._PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if 2 <= len(name) <= 50:
                    return name
        return "my_project"


# ─────────────────────────────────────────────────────────────────────────────
# Coding Agent
# ─────────────────────────────────────────────────────────────────────────────

class CodingAgent:
    """
    Specialised sub-agent for software development tasks.

    Usage
    -----
    agent = CodingAgent(workspace_root=Path("projects"))
    result = agent.execute("Create a FastAPI project called todo_api")

    Integration with ExecutiveAgent
    --------------------------------
    ExecutiveAgent.StepExecutor can call agent.execute(step.input_data)
    instead of engine.handle_input() when step intent == CREATION.
    """

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        progress_callback: Optional[Callable[[CodingProgress], None]] = None,
        max_retries: int = 2,
        extra_providers: Optional[List[ProjectProvider]] = None,
    ) -> None:
        self.workspace_root = workspace_root or Path.cwd() / "generated_projects"
        self.progress_callback = progress_callback
        self.max_retries = max_retries

        self.type_detector  = ProjectTypeDetector()
        self.name_extractor = ProjectNameExtractor()
        self.validator      = CodeValidator()
        self.modifier       = FileModifier()

        # Register built-in providers
        self._providers: Dict[ProjectType, ProjectProvider] = {}
        for provider in [
            PythonProvider(), FlaskProvider(), FastAPIProvider(),
            HTMLProvider(), ReactProvider(), NodeJSProvider(),
        ]:
            self._providers[provider.project_type] = provider

        # Register any extra providers supplied by caller
        for provider in (extra_providers or []):
            self._providers[provider.project_type] = provider

        logger.info("[CodingAgent] Initialized. Workspace: %s", self.workspace_root)

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(
        self,
        request: str,
        output_dir: Optional[Path] = None,
    ) -> CodingResult:
        """
        Parse request, generate project files, validate, and return a CodingResult.

        Args:
            request:    Natural-language coding instruction.
            output_dir: Override where the project is written.
        """
        task_id = str(uuid.uuid4())[:8]
        started = time.time()
        attempt = 0

        while attempt <= self.max_retries:
            attempt += 1
            self._emit(CodingProgress(
                task_id=task_id,
                status=CodingStatus.RUNNING if attempt == 1 else CodingStatus.RETRYING,
                message=f"Attempt {attempt}/{self.max_retries + 1}: analysing request…",
            ))

            try:
                result = self._run_once(task_id, request, output_dir, started)
                if result.status == CodingStatus.SUCCESS:
                    logger.info("[CodingAgent] %s", result.summary())
                    self._emit(CodingProgress(
                        task_id=task_id,
                        status=CodingStatus.SUCCESS,
                        message=f"Project generated successfully in {result.root_dir}",
                        files_created=[str(f.path) for f in result.generated_files if not f.overwritten],
                        files_modified=[str(f.path) for f in result.generated_files if f.overwritten],
                    ))
                    return result
                else:
                    if attempt > self.max_retries:
                        result.retry_count = attempt - 1
                        return result
                    logger.warning("[CodingAgent] Attempt %d failed, retrying…", attempt)
                    time.sleep(0.5 * attempt)

            except Exception as e:
                logger.error("[CodingAgent] Unexpected error on attempt %d: %s", attempt, e, exc_info=True)
                if attempt > self.max_retries:
                    duration = time.time() - started
                    return CodingResult(
                        task_id=task_id,
                        status=CodingStatus.FAILED,
                        project_type=ProjectType.UNKNOWN,
                        root_dir=self.workspace_root,
                        errors=[str(e)],
                        total_duration=duration,
                        retry_count=attempt - 1,
                    )
                time.sleep(0.5 * attempt)

        # Should not reach here
        return CodingResult(
            task_id=task_id, status=CodingStatus.FAILED,
            project_type=ProjectType.UNKNOWN, root_dir=self.workspace_root,
        )

    def modify_file(
        self,
        file_path: Path,
        operation: str,
        content: str,
        marker: Optional[str] = None,
    ) -> GeneratedFile:
        """
        Apply a targeted modification to an existing file.

        Args:
            file_path:  Path to the file to modify.
            operation:  One of: 'append', 'prepend', 'replace', 'insert_after'.
            content:    The text to add / use as replacement.
            marker:     Required for 'replace' (old block) and 'insert_after' (search marker).
        """
        op = operation.lower()
        if op == "append":
            return self.modifier.append_lines(file_path, content)
        elif op == "prepend":
            return self.modifier.prepend_lines(file_path, content)
        elif op == "replace":
            if marker is None:
                raise ValueError("'replace' operation requires a marker (old block).")
            return self.modifier.replace_block(file_path, marker, content)
        elif op == "insert_after":
            if marker is None:
                raise ValueError("'insert_after' operation requires a marker line.")
            return self.modifier.insert_after(file_path, marker, content)
        else:
            raise ValueError(f"Unknown operation '{operation}'. Choose: append, prepend, replace, insert_after.")

    def list_providers(self) -> List[str]:
        return [pt.value for pt in self._providers]

    def register_provider(self, provider: ProjectProvider) -> None:
        self._providers[provider.project_type] = provider
        logger.info("[CodingAgent] Registered provider: %s", provider.project_type.value)

    # ── Internal ───────────────────────────────────────────────────────────

    def _run_once(
        self,
        task_id: str,
        request: str,
        output_dir: Optional[Path],
        started: float,
    ) -> CodingResult:
        # 1. Detect project type & name
        project_type = self.type_detector.detect(request)
        project_name = self.name_extractor.extract(request)
        provider = self._providers.get(project_type)

        if provider is None:
            return CodingResult(
                task_id=task_id,
                status=CodingStatus.FAILED,
                project_type=project_type,
                root_dir=self.workspace_root,
                errors=[f"No provider registered for project type '{project_type}'."],
                total_duration=time.time() - started,
            )

        # 2. Resolve output directory
        root = output_dir or (self.workspace_root / _safe_name(project_name))
        root.mkdir(parents=True, exist_ok=True)

        self._emit(CodingProgress(
            task_id=task_id,
            status=CodingStatus.RUNNING,
            message=f"Generating {project_type.value} project '{project_name}' in {root}…",
        ))

        # 3. Generate files
        generated = provider.generate(root, project_name)

        # 4. Validate generated files
        validation_results = self.validator.validate_generated_files(generated)
        errors = [r.stderr for r in validation_results if not r.success and r.stderr]

        status = CodingStatus.SUCCESS if not errors else CodingStatus.FAILED

        return CodingResult(
            task_id=task_id,
            status=status,
            project_type=project_type,
            root_dir=root,
            generated_files=generated,
            errors=errors,
            total_duration=time.time() - started,
        )

    def _emit(self, progress: CodingProgress) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(progress)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    """Convert a project name to a filesystem-safe Python identifier."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name.strip()).lower()
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "project"


# ─────────────────────────────────────────────────────────────────────────────
# File templates
# ─────────────────────────────────────────────────────────────────────────────

_PYTHON_MAIN = '''\
"""
{name} — entry point
"""


def main() -> None:
    print("Hello from {name}!")


if __name__ == "__main__":
    main()
'''

_FLASK_APP = '''\
"""
Flask application — {name}
"""
from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
'''

_FASTAPI_APP = '''\
"""
FastAPI application — {name}
"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="{name}", version="0.1.0")


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/")
async def root():
    return {{"message": "Hello from {name}!"}}
'''

_HTML_TEMPLATE = '''\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <h1>{title}</h1>
    <p>Welcome to {title}.</p>
</body>
</html>
'''

_HTML_PAGE = '''\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <header>
        <h1>{title}</h1>
    </header>
    <main>
        <p>Welcome to {title}.</p>
    </main>
    <script src="js/main.js"></script>
</body>
</html>
'''

_CSS_BASE = '''\
/* Base styles */
*, *::before, *::after {{ box-sizing: border-box; }}

body {{
    margin: 0;
    font-family: system-ui, -apple-system, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    line-height: 1.6;
}}

h1 {{ color: #7c3aed; }}
a {{ color: #818cf8; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
'''

_JS_MAIN = '''\
// {name} — main.js
console.log("{name} loaded.");

document.addEventListener("DOMContentLoaded", () => {{
    console.log("DOM ready.");
}});
'''

_REACT_PACKAGE = '''\
{{
  "name": "{name}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  }},
  "dependencies": {{
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }},
  "devDependencies": {{
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.0.0"
  }}
}}
'''

_VITE_CONFIG = '''\
import {{ defineConfig }} from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({{
  plugins: [react()],
}});
'''

_REACT_INDEX = '''\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{name}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
'''

_REACT_MAIN = '''\
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./App.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
'''

_REACT_APP = '''\
import React from "react";

export default function App() {{
  return (
    <div>
      <h1>{name}</h1>
      <p>Edit <code>src/App.jsx</code> to get started.</p>
    </div>
  );
}}
'''

_NODE_PACKAGE = '''\
{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "A Node.js Express server",
  "main": "index.js",
  "scripts": {{
    "start": "node index.js",
    "dev": "nodemon index.js"
  }},
  "dependencies": {{
    "express": "^4.18.0"
  }}
}}
'''

_NODE_SERVER = '''\
const express = require("express");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

app.get("/", (req, res) => {{
  res.json({{ message: "Hello from {name}!" }});
}});

app.get("/health", (req, res) => {{
  res.json({{ status: "ok" }});
}});

app.listen(PORT, () => {{
  console.log(`{name} running on http://localhost:${{PORT}}`);
}});
'''
