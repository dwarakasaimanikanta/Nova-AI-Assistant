"""
tests/test_tools/test_memory.py
-------------------------------
Unit tests for Nova's consolidated long-term memory tool and plugin.
"""

import json
from pathlib import Path
from tools.memory_tool import MemoryTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_memory_schema() -> None:
    """Ensure MemoryTool defines correct parameters schema and is LOW risk."""
    tool = MemoryTool()
    assert tool.name == "memory"
    assert tool.risk_level == RiskLevel.LOW
    assert "action" in tool.parameters_schema["required"]
    assert "store_fact" in tool.parameters_schema["properties"]["action"]["enum"]
    assert "get_fact" in tool.parameters_schema["properties"]["action"]["enum"]


def test_memory_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and registers the MemoryPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    # MemoryPlugin, BrowserPlugin, FileManagerPlugin, TerminalPlugin should be loaded
    assert len(discovered_plugins) >= 4
    assert any(p.name == "memory" for p in discovered_plugins)


def test_engine_memory_registration() -> None:
    """Ensure engine dynamically registers memory tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    # MemoryPlugin should be loaded
    assert any(p.name == "memory" for p in engine.plugins)

    # MemoryTool should be registered in registry
    assert engine.registry.get_tool("memory") is not None


def test_memory_crud_operations(tmp_path: Path) -> None:
    """Ensure MemoryTool supports storing, updating, retrieving and listing facts on a tmp file."""
    db_file = tmp_path / "long_term_memory_test.json"
    tool = MemoryTool(filepath=db_file)

    # 1. Start fresh and empty
    res = tool.execute(action="list_facts")
    assert "empty" in res.lower()

    # 2. Store new facts
    res = tool.execute(action="store_fact", key="name", value="Arjun")
    assert "Success" in res
    
    res = tool.execute(action="store_fact", key="Studies", value="Computer Science")
    assert "Success" in res

    # 3. Retrieve facts (verify key normalization to lowercase)
    val = tool.execute(action="get_fact", key="NAME")
    assert val == "Arjun"

    val = tool.execute(action="get_fact", key="studies")
    assert val == "Computer Science"

    # 4. List all facts
    list_res = tool.execute(action="list_facts")
    assert "name: Arjun" in list_res
    assert "studies: Computer Science" in list_res

    # 5. Verify file persistence on disk
    assert db_file.exists()
    with open(db_file, "r", encoding="utf-8") as f:
        stored_dict = json.load(f)
    assert stored_dict == {"name": "Arjun", "studies": "Computer Science"}

    # 6. Update existing fact
    res = tool.execute(action="store_fact", key="name", value="Arjun Dev")
    assert "Success" in res
    assert tool.execute(action="get_fact", key="name") == "Arjun Dev"

    # 7. Check non-existent key
    res = tool.execute(action="get_fact", key="favorite_color")
    assert "no fact found" in res.lower()
