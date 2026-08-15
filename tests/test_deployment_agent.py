"""
tests/test_deployment_agent.py
------------------------------
Comprehensive unit tests for the DeploymentAgent subsystem.
"""

import tempfile
from pathlib import Path

import pytest

from agents.deployment_agent import DeploymentAgent


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestDeploymentAgent:
    def test_detects_react_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create package.json with react dependency
            pkg_json = root / "package.json"
            pkg_json.write_text('{"dependencies": {"react": "^18.0.0"}}', encoding="utf-8")
            
            agent = DeploymentAgent(workspace_root=root)
            res = agent.execute("deploy this project")
            
            assert res.project_type == "React"
            assert res.provider == "Vercel"
            assert "vercel deploy" in res.deployment_command

    def test_detects_fastapi_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create requirements.txt with fastapi dependency
            reqs = root / "requirements.txt"
            reqs.write_text("fastapi==0.95.0\nuvicorn==0.21.1\n", encoding="utf-8")
            
            agent = DeploymentAgent(workspace_root=root)
            res = agent.execute("deploy to Railway")
            
            assert res.project_type == "FastAPI"
            assert res.provider == "Railway"
            assert "railway up" in res.deployment_command

    def test_custom_provider_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create index.html for static html project
            html = root / "index.html"
            html.write_text("<h1>Nova</h1>", encoding="utf-8")
            
            agent = DeploymentAgent(workspace_root=root)
            # Override Netlify default with Vercel request keyword
            res = agent.execute("deploy to vercel")
            
            assert res.project_type == "Static HTML"
            assert res.provider == "Vercel"
            assert "vercel deploy" in res.deployment_command
