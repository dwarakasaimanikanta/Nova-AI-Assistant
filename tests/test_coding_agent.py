"""
tests/test_coding_agent.py
--------------------------
Comprehensive unit tests for the CodingAgent pipeline.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.coding_agent import (
    CodingAgent,
    CodingProgress,
    CodingResult,
    CodingStatus,
    CodeValidator,
    FastAPIProvider,
    FileModifier,
    FlaskProvider,
    GeneratedFile,
    HTMLProvider,
    NodeJSProvider,
    ProjectNameExtractor,
    ProjectType,
    ProjectTypeDetector,
    PythonProvider,
    ReactProvider,
    ValidationResult,
    _safe_name,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_workspace(tmp_path):
    return tmp_path / "workspace"


# ─────────────────────────────────────────────────────────────────────────────
# _safe_name
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeName:
    def test_simple_ascii(self):
        assert _safe_name("my project") == "my_project"

    def test_special_chars(self):
        assert _safe_name("Todo-App!") == "todo_app"

    def test_empty_string(self):
        assert _safe_name("") == "project"

    def test_already_safe(self):
        assert _safe_name("hello_world") == "hello_world"

    def test_multiple_underscores_collapsed(self):
        assert _safe_name("a  b  c") == "a_b_c"


# ─────────────────────────────────────────────────────────────────────────────
# ProjectTypeDetector
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectTypeDetector:
    def setup_method(self):
        self.detector = ProjectTypeDetector()

    def test_fastapi_detected(self):
        assert self.detector.detect("Create a FastAPI project") == ProjectType.FASTAPI

    def test_flask_detected(self):
        assert self.detector.detect("Build a Flask web application") == ProjectType.FLASK

    def test_react_detected(self):
        assert self.detector.detect("Generate a React app with JSX") == ProjectType.REACT

    def test_nodejs_detected(self):
        assert self.detector.detect("Create a Node.js Express server") == ProjectType.NODEJS

    def test_html_detected(self):
        assert self.detector.detect("Build a static HTML/CSS/JS website") == ProjectType.HTML

    def test_python_detected(self):
        assert self.detector.detect("Write a Python script for data processing") == ProjectType.PYTHON

    def test_default_fallback_is_python(self):
        assert self.detector.detect("build something cool") == ProjectType.PYTHON

    def test_fastapi_takes_priority_over_python(self):
        assert self.detector.detect("Create a FastAPI Python microservice") == ProjectType.FASTAPI


# ─────────────────────────────────────────────────────────────────────────────
# ProjectNameExtractor
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectNameExtractor:
    def setup_method(self):
        self.extractor = ProjectNameExtractor()

    def test_extracts_named_project(self):
        name = self.extractor.extract("Create a Flask app called todo_app")
        assert "todo" in name.lower() or "app" in name.lower()

    def test_default_when_no_name(self):
        name = self.extractor.extract("Just build something")
        assert name == "my_project"

    def test_extracts_quoted_name(self):
        name = self.extractor.extract("Create a project 'my_api'")
        assert "my_api" in name


# ─────────────────────────────────────────────────────────────────────────────
# Providers
# ─────────────────────────────────────────────────────────────────────────────

class TestPythonProvider:
    def test_generates_expected_files(self, tmp_path):
        provider = PythonProvider()
        files = provider.generate(tmp_path, "demo")
        paths = [f.path.name for f in files]
        assert "demo.py" in paths
        assert "requirements.txt" in paths
        assert "README.md" in paths

    def test_main_py_is_valid_python(self, tmp_path):
        provider = PythonProvider()
        files = provider.generate(tmp_path, "demo")
        main_file = next(f for f in files if f.path.name == "demo.py")
        assert "def main" in main_file.content
        assert main_file.path.exists()


class TestFlaskProvider:
    def test_generates_expected_files(self, tmp_path):
        provider = FlaskProvider()
        files = provider.generate(tmp_path, "myapp")
        paths = [f.path.name for f in files]
        assert "app.py" in paths
        assert "requirements.txt" in paths
        assert "index.html" in paths
        assert "style.css" in paths

    def test_app_py_imports_flask(self, tmp_path):
        provider = FlaskProvider()
        files = provider.generate(tmp_path, "myapp")
        app_file = next(f for f in files if f.path.name == "app.py")
        assert "from flask import" in app_file.content


class TestFastAPIProvider:
    def test_generates_expected_files(self, tmp_path):
        provider = FastAPIProvider()
        files = provider.generate(tmp_path, "api")
        paths = [f.path.name for f in files]
        assert "main.py" in paths
        assert "requirements.txt" in paths

    def test_main_py_imports_fastapi(self, tmp_path):
        provider = FastAPIProvider()
        files = provider.generate(tmp_path, "api")
        main_file = next(f for f in files if f.path.name == "main.py")
        assert "from fastapi import" in main_file.content


class TestHTMLProvider:
    def test_generates_expected_files(self, tmp_path):
        provider = HTMLProvider()
        files = provider.generate(tmp_path, "mysite")
        paths = [f.path.name for f in files]
        assert "index.html" in paths
        assert "style.css" in paths
        assert "main.js" in paths

    def test_index_html_has_doctype(self, tmp_path):
        provider = HTMLProvider()
        files = provider.generate(tmp_path, "mysite")
        html = next(f for f in files if f.path.name == "index.html")
        assert "<!DOCTYPE html>" in html.content


class TestReactProvider:
    def test_generates_expected_files(self, tmp_path):
        provider = ReactProvider()
        files = provider.generate(tmp_path, "myreact")
        paths = [f.path.name for f in files]
        assert "package.json" in paths
        assert "App.jsx" in paths
        assert "main.jsx" in paths
        assert "index.html" in paths

    def test_package_json_is_valid(self, tmp_path):
        provider = ReactProvider()
        files = provider.generate(tmp_path, "myreact")
        pkg = next(f for f in files if f.path.name == "package.json")
        data = json.loads(pkg.content)
        assert "react" in data["dependencies"]


class TestNodeJSProvider:
    def test_generates_expected_files(self, tmp_path):
        provider = NodeJSProvider()
        files = provider.generate(tmp_path, "myserver")
        paths = [f.path.name for f in files]
        assert "package.json" in paths
        assert "index.js" in paths

    def test_package_json_has_express(self, tmp_path):
        provider = NodeJSProvider()
        files = provider.generate(tmp_path, "myserver")
        pkg = next(f for f in files if f.path.name == "package.json")
        data = json.loads(pkg.content)
        assert "express" in data["dependencies"]


# ─────────────────────────────────────────────────────────────────────────────
# FileModifier
# ─────────────────────────────────────────────────────────────────────────────

class TestFileModifier:
    def test_append_lines(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\n")
        result = FileModifier.append_lines(f, "line2")
        assert "line1" in result.content
        assert "line2" in result.content
        assert f.read_text(encoding="utf-8").strip().endswith("line2")

    def test_prepend_lines(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line2\n")
        result = FileModifier.prepend_lines(f, "line1")
        content = f.read_text(encoding="utf-8")
        assert content.index("line1") < content.index("line2")

    def test_replace_block(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def old_function(): pass\n")
        result = FileModifier.replace_block(f, "old_function", "new_function")
        assert "new_function" in f.read_text(encoding="utf-8")
        assert "old_function" not in f.read_text(encoding="utf-8")

    def test_insert_after(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("# header\nimport os\n# end\n")
        FileModifier.insert_after(f, "# header", "import sys")
        content = f.read_text(encoding="utf-8")
        assert "import sys" in content
        assert content.index("import sys") > content.index("# header")

    def test_append_creates_file_if_missing(self, tmp_path):
        f = tmp_path / "new_file.txt"
        assert not f.exists()
        FileModifier.append_lines(f, "new content")
        assert f.exists()
        assert "new content" in f.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# CodeValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestCodeValidator:
    def test_valid_python_file(self, tmp_path):
        f = tmp_path / "ok.py"
        f.write_text("x = 1 + 1\n")
        validator = CodeValidator()
        result = validator.validate_python_syntax(f)
        assert result.success is True

    def test_invalid_python_file(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        validator = CodeValidator()
        result = validator.validate_python_syntax(f)
        assert result.success is False

    def test_valid_json_file(self, tmp_path):
        f = tmp_path / "package.json"
        f.write_text('{"name": "test"}')
        validator = CodeValidator()
        result = validator.validate_json(f)
        assert result.success is True

    def test_invalid_json_file(self, tmp_path):
        f = tmp_path / "package.json"
        f.write_text('{broken json}')
        validator = CodeValidator()
        result = validator.validate_json(f)
        assert result.success is False

    def test_validate_generated_files_python(self, tmp_path):
        f = tmp_path / "good.py"
        f.write_text("print('hi')\n")
        gf = GeneratedFile(path=f, content="print('hi')\n")
        validator = CodeValidator()
        results = validator.validate_generated_files([gf])
        assert len(results) == 1
        assert results[0].success is True


# ─────────────────────────────────────────────────────────────────────────────
# CodingAgent Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCodingAgent:
    def test_python_project_generation(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Create a Python script called hello_world")
        assert result.status == CodingStatus.SUCCESS
        assert result.project_type == ProjectType.PYTHON
        assert len(result.generated_files) > 0
        assert result.root_dir.exists()

    def test_flask_project_generation(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Build a Flask web app called my_flask_app")
        assert result.status == CodingStatus.SUCCESS
        assert result.project_type == ProjectType.FLASK

    def test_fastapi_project_generation(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Create a FastAPI project called my_api")
        assert result.status == CodingStatus.SUCCESS
        assert result.project_type == ProjectType.FASTAPI

    def test_html_project_generation(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Generate a static HTML website called my_site")
        assert result.status == CodingStatus.SUCCESS
        assert result.project_type == ProjectType.HTML

    def test_react_project_generation(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Create a React app called my_react_app")
        assert result.status == CodingStatus.SUCCESS
        assert result.project_type == ProjectType.REACT

    def test_nodejs_project_generation(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Build a Node.js Express server called my_server")
        assert result.status == CodingStatus.SUCCESS
        assert result.project_type == ProjectType.NODEJS

    def test_progress_callback_invoked(self, tmp_workspace):
        progress_events = []
        agent = CodingAgent(
            workspace_root=tmp_workspace,
            progress_callback=lambda p: progress_events.append(p),
        )
        agent.execute("Create a Python project")
        assert len(progress_events) > 0
        assert any(p.status == CodingStatus.SUCCESS for p in progress_events)

    def test_to_dict_structure(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Create a Python project")
        d = result.to_dict()
        assert "task_id" in d
        assert "status" in d
        assert "project_type" in d
        assert "files_created" in d

    def test_custom_output_dir(self, tmp_path):
        custom_dir = tmp_path / "custom_output"
        agent = CodingAgent(workspace_root=tmp_path)
        result = agent.execute("Create a Python project", output_dir=custom_dir)
        assert result.status == CodingStatus.SUCCESS
        assert result.root_dir == custom_dir

    def test_modify_file_append(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        # First generate a project
        result = agent.execute("Create a Python project called mod_test")
        py_file = next(f.path for f in result.generated_files if f.path.suffix == ".py")
        # Then append a new function
        gf = agent.modify_file(py_file, "append", "\ndef helper():\n    return 42\n")
        assert "helper" in py_file.read_text(encoding="utf-8")

    def test_list_providers(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        providers = agent.list_providers()
        assert "python" in providers
        assert "flask" in providers
        assert "fastapi" in providers
        assert "html" in providers
        assert "react" in providers
        assert "nodejs" in providers

    def test_register_custom_provider(self, tmp_workspace):
        from agents.coding_agent import ProjectProvider

        class MockProvider(ProjectProvider):
            @property
            def project_type(self):
                return ProjectType.UNKNOWN

            def generate(self, root, project_name, **options):
                return [self.write_file(root / "mock.txt", "mock content")]

        agent = CodingAgent(workspace_root=tmp_workspace)
        agent.register_provider(MockProvider())
        assert ProjectType.UNKNOWN in agent._providers

    def test_summary_string(self, tmp_workspace):
        agent = CodingAgent(workspace_root=tmp_workspace)
        result = agent.execute("Create a Python project called summary_test")
        summary = result.summary()
        assert "CodingAgent" in summary
        assert "python" in summary
