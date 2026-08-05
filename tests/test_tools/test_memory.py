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


def test_memory_crud_operations(tmp_path: Path, monkeypatch) -> None:
    """Ensure MemoryTool supports storing, updating, retrieving and listing facts on a tmp file."""
    # Prevent real API calls for embeddings during crud tests
    monkeypatch.setattr(MemoryTool, "_get_embedding", lambda self, text: None)

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

    # 5. Verify file persistence on disk (verify SQLite DB file)
    actual_db_file = tmp_path / "long_term_memory_test.db"
    assert actual_db_file.exists()
    
    import sqlite3
    conn = sqlite3.connect(str(actual_db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM memory")
    rows = dict(cursor.fetchall())
    conn.close()
    assert rows == {"name": "Arjun", "studies": "Computer Science"}

    # 6. Update existing fact
    res = tool.execute(action="store_fact", key="name", value="Arjun Dev")
    assert "Success" in res
    assert tool.execute(action="get_fact", key="name") == "Arjun Dev"

    # 7. Check non-existent key
    res = tool.execute(action="get_fact", key="favorite_color")
    assert "no fact found" in res.lower()

    tool.close()


def test_memory_json_migration(tmp_path: Path, monkeypatch) -> None:
    """Ensure MemoryTool successfully migrates legacy JSON files to SQLite on startup."""
    # Prevent real API calls for embeddings during migration tests
    monkeypatch.setattr(MemoryTool, "_get_embedding", lambda self, text: None)

    legacy_json = tmp_path / "legacy_memory.json"
    db_file = tmp_path / "legacy_memory.db"
    
    # 1. Write some legacy JSON data
    legacy_data = {
        "hometown": "Chicago",
        "programming_language": "Python"
    }
    with open(legacy_json, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)
        
    assert legacy_json.exists()
    assert not db_file.exists()
    
    # 2. Initialize MemoryTool pointing to the legacy JSON file
    tool = MemoryTool(filepath=legacy_json)
    
    # 3. Verify migration succeeded and legacy JSON is deleted
    assert not legacy_json.exists()
    assert db_file.exists()
    
    # 4. Verify retrieved values from the tool
    assert tool.execute(action="get_fact", key="hometown") == "Chicago"
    assert tool.execute(action="get_fact", key="programming_language") == "Python"
    
    tool.close()


def test_memory_semantic_lookup(tmp_path: Path, monkeypatch) -> None:
    """Ensure MemoryTool performs semantic lookup when exact match is not found."""
    db_file = tmp_path / "semantic_memory_test.db"
    
    # Mock _get_embedding method
    def mock_get_embedding(self, text: str) -> list[float] | None:
        vectors = {
            "programming language": [1.0, 0.0, 0.0],
            "hometown": [0.0, 1.0, 0.0],
            "favorite language": [0.99, 0.01, 0.0],
            "location": [0.05, 0.95, 0.0],
            "unrelated": [0.0, 0.0, 1.0]
        }
        return vectors.get(text.strip().lower(), [0.0, 0.0, 0.0])
        
    monkeypatch.setattr(MemoryTool, "_get_embedding", mock_get_embedding)
    
    tool = MemoryTool(filepath=db_file)
    
    # Store some facts
    tool.execute(action="store_fact", key="programming language", value="Python")
    tool.execute(action="store_fact", key="hometown", value="Seattle")
    
    # Test semantic lookup
    val = tool.execute(action="get_fact", key="favorite language")
    assert val == "Python"
    
    val = tool.execute(action="get_fact", key="location")
    assert val == "Seattle"
    
    val = tool.execute(action="get_fact", key="unrelated")
    assert "no fact found" in val.lower()
    
    tool.close()
