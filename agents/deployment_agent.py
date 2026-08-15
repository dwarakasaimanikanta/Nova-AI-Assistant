"""
agents/deployment_agent.py
--------------------------
DeploymentAgent building hosted cloud configurations for React, Next, and backend apps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DeploymentResult:
    """Outcome of a deployment configuration assembly."""
    provider: str
    project_type: str
    deployment_command: str
    expected_url: str
    environment_variables: Dict[str, str]
    status: str


# ─────────────────────────────────────────────────────────────────────────────
# Deployment Agent
# ─────────────────────────────────────────────────────────────────────────────

class DeploymentAgent:
    """Configures project-agnostic cloud build commands for hosting sites."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = workspace_root or Path.cwd()

    def execute(self, request: str) -> DeploymentResult:
        """Analyzes directory project files, selects provider and builds CLI instructions."""
        lower = request.lower()
        target_dir = self.workspace_root

        # 1. Detect project type
        project_type = self._detect_project_type(target_dir)

        # 2. Select target provider
        provider = self._select_provider(lower, project_type)

        # 3. Build command
        cmd, url = self._build_config(provider, target_dir)

        # 4. Environments
        env_vars = {
            "PORT": "8000" if project_type == "FastAPI" else "5000" if project_type == "Flask" else "3000",
            "ENVIRONMENT": "production"
        }

        return DeploymentResult(
            provider=provider,
            project_type=project_type,
            deployment_command=cmd,
            expected_url=url,
            environment_variables=env_vars,
            status="READY_TO_DEPLOY"
        )

    def _detect_project_type(self, root: Path) -> str:
        try:
            if (root / "package.json").exists():
                content = (root / "package.json").read_text(encoding="utf-8", errors="ignore").lower()
                if "next" in content:
                    return "Next.js"
                if "react" in content:
                    return "React"
                return "Node.js"
            elif (root / "requirements.txt").exists():
                content = (root / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
                if "fastapi" in content:
                    return "FastAPI"
                if "flask" in content:
                    return "Flask"
                return "Flask"
            elif (root / "index.html").exists():
                return "Static HTML"
        except Exception as e:
            logger.debug("Failed reading project files for detection: %s", e)
        return "Static HTML"

    def _select_provider(self, request_text: str, project_type: str) -> str:
        for p in ("vercel", "netlify", "render", "railway"):
            if p in request_text:
                return p.capitalize()
        # Fallbacks
        if project_type in ("React", "Next.js"):
            return "Vercel"
        elif project_type == "Static HTML":
            return "Netlify"
        else:
            return "Render"

    def _build_config(self, provider: str, root: Path) -> tuple[str, str]:
        name = root.name.lower()
        resolved = root.resolve()
        if provider == "Vercel":
            return f"vercel deploy --prod --yes --cwd {resolved}", f"https://{name}.vercel.app"
        elif provider == "Netlify":
            return f"netlify deploy --prod --dir={resolved}", f"https://{name}.netlify.app"
        elif provider == "Render":
            return f"render deploy --manual --directory {resolved}", f"https://{name}.onrender.com"
        elif provider == "Railway":
            return f"railway up --service {name} --workdir {resolved}", f"https://{name}.up.railway.app"
        return f"echo deploying to {provider}", f"http://{name}.local"
