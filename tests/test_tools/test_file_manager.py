"""
tests/test_tools/test_file_manager.py
-------------------------------------
Unit tests for Nova's consolidated file manager tool and plugin system.
"""

from pathlib import Path
from tools.file_manager import FileManagerTool
from tools.permission_gate import PermissionGate
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_file_manager_schema() -> None:
    """Ensure FileManagerTool registers a unified schema with required parameter constraints."""
    tool = FileManagerTool()
    assert tool.name == "file_manager"
    assert "action" in tool.parameters_schema["required"]
    assert "write" in tool.parameters_schema["properties"]["action"]["enum"]


def test_permission_gate_dynamic_risk() -> None:
    """Ensure permission gate overrides risk level dynamically based on action."""
    gate = PermissionGate()
    tool = FileManagerTool()

    # Read and List actions should bypass safety check (effectively LOW risk)
    assert gate.check_permission(tool, {"action": "read", "path": "test.txt"}) is True
    assert gate.check_permission(tool, {"action": "list", "path": "."}) is True

    # Overwriting, deleting, or structuring files should trigger authorization prompts (HIGH risk)
    assert gate.check_permission(tool, {"action": "write", "path": "test.txt", "content": "hi"}) is False
    assert gate.check_permission(tool, {"action": "delete", "path": "test.txt"}) is False
    assert gate.check_permission(tool, {"action": "create_folder", "path": "dir"}) is False


def test_file_operations(tmp_path: Path) -> None:
    """Ensure all actions execute successfully on sandboxed directory path."""
    tool = FileManagerTool()

    test_folder = tmp_path / "sandbox"
    test_file = test_folder / "file.txt"
    renamed_file = test_folder / "renamed.txt"
    copied_file = test_folder / "copied.txt"

    # 1. create_folder
    res = tool.execute(action="create_folder", path=str(test_folder))
    assert "Success" in res
    assert test_folder.is_dir()

    # 2. create_file
    res = tool.execute(action="create_file", path=str(test_file))
    assert "Success" in res
    assert test_file.is_file()

    # 3. write
    res = tool.execute(action="write", path=str(test_file), content="Hello")
    assert "Success" in res
    assert test_file.read_text(encoding="utf-8") == "Hello"

    # 4. append
    res = tool.execute(action="append", path=str(test_file), content=" world!")
    assert "Success" in res
    assert test_file.read_text(encoding="utf-8") == "Hello world!"

    # 5. read
    res = tool.execute(action="read", path=str(test_file))
    assert res == "Hello world!"

    # 6. list
    res = tool.execute(action="list", path=str(test_folder))
    assert "file.txt" in res

    # 7. copy
    res = tool.execute(action="copy", src=str(test_file), dest=str(copied_file))
    assert "Success" in res
    assert copied_file.is_file()
    assert copied_file.read_text(encoding="utf-8") == "Hello world!"

    # 8. rename
    res = tool.execute(action="rename", src=str(test_file), dest=str(renamed_file))
    assert "Success" in res
    assert not test_file.exists()
    assert renamed_file.is_file()

    # 9. delete file
    res = tool.execute(action="delete", path=str(renamed_file))
    assert "Success" in res
    assert not renamed_file.exists()

    # 10. delete folder
    res = tool.execute(action="delete", path=str(test_folder))
    assert "Success" in res
    assert not test_folder.exists()


def test_plugin_loader_discovery() -> None:
    """Ensure PluginLoader automatically scans and loads plugins from the filesystem."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    # FileManagerPlugin should be found and loaded dynamically
    assert len(discovered_plugins) >= 1
    assert any(p.name == "file_manager" for p in discovered_plugins)


def test_engine_plugin_loading() -> None:
    """Ensure engine dynamically registers tools loaded through plugins."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    # FileManagerPlugin should be loaded
    assert len(engine.plugins) >= 1
    assert any(p.name == "file_manager" for p in engine.plugins)

    # FileManagerTool should be registered in registry
    assert engine.registry.get_tool("file_manager") is not None
