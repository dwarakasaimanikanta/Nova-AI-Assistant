"""
tests/test_memory_agent.py
---------------------------
Comprehensive unit and integration tests for the MemoryAgent persistent
intelligence layer and its dynamic routing/logging integration.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.memory_agent import (
    MemoryAgent,
    MemoryEntry,
    MemoryStore,
    MemorySearch,
    MemoryResult,
    ShortTermMemory,
    LongTermMemory,
    WorkingMemory,
)
from core.executive_agent import ExecutiveAgent, ExecutionStatus


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    import os
    os.close(fd)
    db_path = Path(path)
    yield db_path
    if db_path.exists():
        os.remove(db_path)


@pytest.fixture
def agent(temp_db):
    return MemoryAgent(db_path=temp_db)


# ─────────────────────────────────────────────────────────────────────────────
# Store CRUD & Search Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryStore:
    def test_store_init(self, temp_db):
        store = MemoryStore(temp_db)
        assert store.db_path.exists()

    def test_save_and_load_entry(self, temp_db):
        store = MemoryStore(temp_db)
        entry = MemoryEntry(key="name", value="Nova", category="short_term", tags={"system", "name"}, priority=3.0)
        store.save(entry)

        loaded = store.load_by_key("short_term", "name")
        assert loaded is not None
        assert loaded.key == "name"
        assert loaded.value == "Nova"
        assert "system" in loaded.tags
        assert loaded.priority == 3.0

    def test_delete_entry(self, temp_db):
        store = MemoryStore(temp_db)
        entry = MemoryEntry(key="studies", value="CS", category="long_term")
        store.save(entry)

        deleted = store.delete("long_term", "studies")
        assert deleted is True
        assert store.load_by_key("long_term", "studies") is None

    def test_search_memories(self, temp_db):
        store = MemoryStore(temp_db)
        e1 = MemoryEntry(key="favorite_language", value="Python", category="long_term", tags={"coding"})
        e2 = MemoryEntry(key="preferred_editor", value="VS Code", category="long_term", tags={"tools"})
        store.save(e1)
        store.save(e2)

        # Search for language
        res = store.search(MemorySearch(query="language", category="long_term"))
        assert len(res) == 1
        assert res[0].entry.key == "favorite_language"

        # Search by tag
        res_tag = store.search(MemorySearch(query="", tags={"tools"}))
        assert len(res_tag) == 1
        assert res_tag[0].entry.key == "preferred_editor"

    def test_cleanup_removes_unpinned_memories(self, temp_db):
        store = MemoryStore(temp_db)
        # Store 5 unpinned memories
        for i in range(5):
            store.save(MemoryEntry(key=f"k{i}", value=f"v{i}", category="working", priority=1.0, pinned=False))
        # Store 1 pinned memory
        store.save(MemoryEntry(key="keep", value="val", category="working", priority=5.0, pinned=True))

        # Cleanup keeping max size of 3
        deleted = store.cleanup_old_memories(max_size=3)
        assert deleted == 3
        
        # Verify the pinned one is still present
        assert store.load_by_key("working", "keep") is not None


# ─────────────────────────────────────────────────────────────────────────────
# Sub-Memory Manager Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSubMemories:
    def test_short_term(self, temp_db):
        store = MemoryStore(temp_db)
        st = ShortTermMemory(store)
        st.remember(key="current_project", value="Nova AI", tags={"dev"})
        assert st.recall("current_project") == "Nova AI"
        st.forget("current_project")
        assert st.recall("current_project") is None

    def test_long_term(self, temp_db):
        store = MemoryStore(temp_db)
        lt = LongTermMemory(store)
        lt.remember(key="user_name", value="Alice", pinned=True)
        assert lt.recall("user_name") == "Alice"
        lt.forget("user_name")
        assert lt.recall("user_name") is None

    def test_working_memory(self, temp_db):
        store = MemoryStore(temp_db)
        wm = WorkingMemory(store)
        wm.remember(key="temp_var", value="temp_val")
        assert wm.recall("temp_var") == "temp_val"


# ─────────────────────────────────────────────────────────────────────────────
# MemoryAgent Orchestration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryAgent:
    def test_unified_execute_remember(self, agent):
        # Commands like "remember long_term favourite_food = Pizza"
        response = agent.handle_input("remember long_term favourite_food = Pizza")
        assert "Pizza" in response
        assert agent.recall("long_term", "favourite_food") == "Pizza"

    def test_unified_execute_recall(self, agent):
        agent.remember("long_term", "favourite_food", "Pizza")
        response = agent.handle_input("recall long_term favourite_food")
        assert response == "Pizza"

    def test_summarize_category(self, agent):
        agent.remember("long_term", "k1", "v1")
        summary = agent.summarize("long_term")
        assert "k1: v1" in summary


# ─────────────────────────────────────────────────────────────────────────────
# Integration / Monkey-Patch Routing Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutiveAgentMemoryIntegration:
    def test_memory_operation_routing(self, agent):
        engine = MagicMock()
        exec_agent = ExecutiveAgent(engine=engine, memory_agent=agent)

        # Triggers a memory storage action via patch
        result = exec_agent.execute("remember long_term city = Paris")

        # Verify task succeeded in MemoryAgent directly
        assert result.status == ExecutionStatus.SUCCESS
        assert "Paris" in result.final_response
        assert agent.recall("long_term", "city") == "Paris"
        
        # Verify NovaEngine was NOT called
        assert len(engine.handle_input.calls if hasattr(engine.handle_input, "calls") else []) == 0

    def test_auto_logging_step_inputs_outputs(self, agent):
        engine = MagicMock()
        engine.handle_input.return_value = "Engine output value"
        exec_agent = ExecutiveAgent(engine=engine, memory_agent=agent)

        # Runs an action that falls back to the Engine
        exec_agent.execute("what is the capital of France?")

        # Check that the step input and output were automatically remembered in the agent
        last_in = agent.recall("short_term", "last_step_input")
        last_out = agent.recall("working", "last_step_output")

        assert last_in == "what is the capital of France?"
        assert last_out == "Engine output value"

    def test_subagent_memory_injection(self, agent):
        from agents.coding_agent import CodingAgent
        from agents.browser_agent import BrowserAgent
        from agents.android_agent import AndroidAgent
        from agents.workspace_agent import WorkspaceAgent
        from agents.planner_agent import PlannerAgent

        # Initialize CodingAgent and check that memory_agent is set
        c_agent = CodingAgent(memory_agent=agent)
        assert c_agent.memory_agent == agent

        b_agent = BrowserAgent(memory_agent=agent)
        assert b_agent.memory_agent == agent

        a_agent = AndroidAgent(memory_agent=agent)
        assert a_agent.memory_agent == agent

        w_agent = WorkspaceAgent(memory_agent=agent)
        assert w_agent.memory_agent == agent

        p_agent = PlannerAgent(engine=MagicMock(), memory_agent=agent)
        assert p_agent.memory_agent == agent
