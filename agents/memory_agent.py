"""
agents/memory_agent.py
----------------------
MemoryAgent is Nova's persistent intelligence layer.

It provides structured and semantic human-like memory across conversations,
coding sessions, browser sessions, and desktop usage, managing Short-Term,
Long-Term, and Working memory states.

Architecture
------------
MemoryAgent uses a SQLite back-end store and wraps:
- ShortTermMemory (conversations, current task, project)
- LongTermMemory (user preferences, remembered facts, personal notes)
- WorkingMemory (execution context, temporary variables)

All sub-agents (Coding, Browser, Android, Workspace, Planner, and Executive)
are monkey-patched on initialization to accept and leverage a MemoryAgent instance.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from config import DATA_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """Represents a single memory entry stored in the intelligence layer."""
    key: str
    value: str
    category: str  # "short_term", "long_term", "working"
    tags: Set[str] = field(default_factory=set)
    priority: float = 1.0  # 1.0 (low) to 5.0 (high)
    pinned: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class MemorySearch:
    """Represents a search query for locating memories."""
    query: str
    category: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    limit: int = 10


@dataclass
class MemoryResult:
    """Represents a single match found during memory search."""
    entry: MemoryEntry
    score: float  # relevance score


# ─────────────────────────────────────────────────────────────────────────────
# Memory Store (SQLite Back-end)
# ─────────────────────────────────────────────────────────────────────────────

class MemoryStore:
    """Thread-safe SQLite database backend for memory persistence."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DATA_DIR / "unified_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    entry_id TEXT PRIMARY KEY,
                    key TEXT,
                    value TEXT,
                    category TEXT,
                    tags TEXT,
                    priority REAL,
                    pinned INTEGER,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.commit()
            conn.close()

    def save(self, entry: MemoryEntry) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            tags_str = ",".join(entry.tags)
            cursor.execute("""
                INSERT OR REPLACE INTO memories 
                (entry_id, key, value, category, tags, priority, pinned, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.entry_id, entry.key, entry.value, entry.category,
                tags_str, entry.priority, 1 if entry.pinned else 0,
                entry.created_at, entry.updated_at
            ))
            conn.commit()
            conn.close()

    def load_by_key(self, category: str, key: str) -> Optional[MemoryEntry]:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT entry_id, value, tags, priority, pinned, created_at, updated_at
                FROM memories WHERE category = ? AND key = ?
            """, (category, key))
            row = cursor.fetchone()
            conn.close()
            if row:
                tags = set(row[2].split(",")) if row[2] else set()
                return MemoryEntry(
                    entry_id=row[0], key=key, value=row[1], category=category,
                    tags=tags, priority=row[3], pinned=bool(row[4]),
                    created_at=row[5], updated_at=row[6]
                )
            return None

    def delete(self, category: str, key: str) -> bool:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE category = ? AND key = ?", (category, key))
            affected = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return affected

    def search(self, search_spec: MemorySearch) -> List[MemoryResult]:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            query = "SELECT entry_id, key, value, category, tags, priority, pinned, created_at, updated_at FROM memories"
            conditions = []
            params = []

            if search_spec.category:
                conditions.append("category = ?")
                params.append(search_spec.category)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            results = []
            q_lower = search_spec.query.lower()
            for r in rows:
                key, val, tags_str = r[1], r[2], r[4]
                tags = set(tags_str.split(",")) if tags_str else set()

                # Basic text match scoring
                score = 0.0
                if q_lower:
                    if q_lower in key.lower():
                        score += 0.5
                    if q_lower in val.lower():
                        score += 0.3
                for tag in search_spec.tags:
                    if tag in tags:
                        score += 0.2

                if score > 0 or (not search_spec.query and not search_spec.tags):
                    entry = MemoryEntry(
                        entry_id=r[0], key=key, value=val, category=r[3],
                        tags=tags, priority=r[5], pinned=bool(r[6]),
                        created_at=r[7], updated_at=r[8]
                    )
                    # Add base score multiplier for priority / pinned status
                    score_final = score * (1.0 + (entry.priority * 0.1))
                    if entry.pinned:
                        score_final += 1.0
                    results.append(MemoryResult(entry=entry, score=score_final))


            results.sort(key=lambda x: x.score, reverse=True)
            return results[:search_spec.limit]

    def cleanup_old_memories(self, max_size: int = 500) -> int:
        """Deletes unpinned, low-priority memories when store limit is reached."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM memories")
            count = cursor.fetchone()[0]
            deleted = 0
            if count > max_size:
                to_delete = count - max_size
                cursor.execute("""
                    DELETE FROM memories WHERE entry_id IN (
                        SELECT entry_id FROM memories 
                        WHERE pinned = 0 
                        ORDER BY priority ASC, created_at ASC 
                        LIMIT ?
                    )
                """, (to_delete,))
                deleted = cursor.rowcount
                conn.commit()
            conn.close()
            return deleted


# ─────────────────────────────────────────────────────────────────────────────
# Short, Long, Working Memory Wrappers
# ─────────────────────────────────────────────────────────────────────────────

class ShortTermMemory:
    """Handles short-term session conversation history and current states."""
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def remember(self, key: str, value: str, tags: Set[str] = None, priority: float = 1.0) -> None:
        entry = MemoryEntry(key=key, value=value, category="short_term", tags=tags or set(), priority=priority)
        self.store.save(entry)

    def recall(self, key: str) -> Optional[str]:
        entry = self.store.load_by_key("short_term", key)
        return entry.value if entry else None

    def forget(self, key: str) -> bool:
        return self.store.delete("short_term", key)


class LongTermMemory:
    """Handles persistent facts, user preferences, and notes."""
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def remember(self, key: str, value: str, tags: Set[str] = None, priority: float = 2.0, pinned: bool = False) -> None:
        entry = MemoryEntry(key=key, value=value, category="long_term", tags=tags or set(), priority=priority, pinned=pinned)
        self.store.save(entry)

    def recall(self, key: str) -> Optional[str]:
        entry = self.store.load_by_key("long_term", key)
        return entry.value if entry else None

    def forget(self, key: str) -> bool:
        return self.store.delete("long_term", key)


class WorkingMemory:
    """Handles temporary context parameters and planner execution state."""
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def remember(self, key: str, value: str, tags: Set[str] = None, priority: float = 1.0) -> None:
        entry = MemoryEntry(key=key, value=value, category="working", tags=tags or set(), priority=priority)
        self.store.save(entry)

    def recall(self, key: str) -> Optional[str]:
        entry = self.store.load_by_key("working", key)
        return entry.value if entry else None

    def forget(self, key: str) -> bool:
        return self.store.delete("working", key)


# ─────────────────────────────────────────────────────────────────────────────
# Memory Agent
# ─────────────────────────────────────────────────────────────────────────────

class MemoryAgent:
    """
    Nova's unified persistent intelligence layer.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.store = MemoryStore(db_path)
        self.short_term = ShortTermMemory(self.store)
        self.long_term  = LongTermMemory(self.store)
        self.working    = WorkingMemory(self.store)
        logger.info("[MemoryAgent] Initialized database store.")

    # ── Unified Public Interface ───────────────────────────────────────────

    def remember(
        self,
        category: str,
        key: str,
        value: str,
        tags: Optional[List[str]] = None,
        priority: float = 1.0,
        pinned: bool = False
    ) -> None:
        t_set = set(tags) if tags else set()
        entry = MemoryEntry(
            key=key, value=value, category=category,
            tags=t_set, priority=priority, pinned=pinned
        )
        self.store.save(entry)

    def recall(self, category: str, key: str) -> Optional[str]:
        entry = self.store.load_by_key(category, key)
        return entry.value if entry else None

    def forget(self, category: str, key: str) -> bool:
        return self.store.delete(category, key)

    def search(self, query: str, category: Optional[str] = None, tags: Optional[List[str]] = None) -> List[dict]:
        spec = MemorySearch(query=query, category=category, tags=set(tags) if tags else set())
        results = self.store.search(spec)
        return [
            {
                "key": r.entry.key,
                "value": r.entry.value,
                "category": r.entry.category,
                "tags": list(r.entry.tags),
                "score": r.score,
                "pinned": r.entry.pinned
            }
            for r in results
        ]

    def summarize(self, category: Optional[str] = None) -> str:
        """Generates a text summary listing all facts matching category."""
        spec = MemorySearch(query="", category=category)
        results = self.store.search(spec)
        if not results:
            return "No memories recorded in this category."
        lines = [f"- [{r.entry.category}] {r.entry.key}: {r.entry.value}" for r in results]
        return "\n".join(lines)

    def cleanup(self, max_size: int = 500) -> int:
        return self.store.cleanup_old_memories(max_size)

    def handle_input(self, user_input: str, stream: bool = False):
        """Compatibility shim for ExecutiveAgent integration."""
        # Check command formats: "remember <category> <key> = <val>"
        lower = user_input.lower().strip()
        if lower.startswith("remember"):
            parts = user_input.split(None, 3)
            # remember category key = val
            if len(parts) >= 4:
                cat = parts[1]
                rem = parts[2:]
                rem_str = " ".join(rem)
                if "=" in rem_str:
                    k, v = rem_str.split("=", 1)
                    self.remember(cat, k.strip(), v.strip())
                    return f"Success: Remembered fact '{k.strip()}' = '{v.strip()}' in '{cat}'."

        elif lower.startswith("recall"):
            parts = user_input.split(None, 2)
            if len(parts) >= 3:
                cat, k = parts[1], parts[2]
                val = self.recall(cat, k.strip())
                return val or f"No fact found for key '{k}' in category '{cat}'."

        results = self.search(user_input)
        if results:
            return f"Found matches:\n" + "\n".join(f"- {r['key']}: {r['value']}" for r in results)
        return "No memories matched this query."


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Runtime Injection into ExecutiveAgent & StepExecutor (Monkey Patch)
# ─────────────────────────────────────────────────────────────────────────────

def _inject_memory_routing() -> None:
    """
    Monkey patches StepExecutor and ExecutiveAgent classes so that
    if a MemoryAgent instance is injected, it routes memory actions to it.
    """
    from core.executive_agent import StepExecutor, ExecutiveAgent, IntentType, ExecutionStatus

    # 1. Modify StepExecutor.__init__ to accept and store memory_agent
    orig_step_init = StepExecutor.__init__

    def patched_step_init(self, *args, **kwargs):
        self.memory_agent = kwargs.pop("memory_agent", None)
        orig_step_init(self, *args, **kwargs)

    StepExecutor.__init__ = patched_step_init

    # 2. Modify StepExecutor.execute to log memory operations
    orig_step_execute = StepExecutor.execute

    def patched_step_execute(self, step, cancel_event=None):
        if getattr(self, "memory_agent", None) is not None:
            # Automate recording conversation history / current task
            try:
                self.memory_agent.remember(
                    category="short_term",
                    key="last_step_input",
                    value=step.input_data,
                    tags=["context", "execution"]
                )
            except Exception as mem_err:
                logger.debug("Failed logging execution input to memory: %s", mem_err)

            lower = step.input_data.lower()
            is_mem_action = lower.startswith("remember") or lower.startswith("recall") or "memory" in lower

            if is_mem_action:
                try:
                    result = self.memory_agent.handle_input(step.input_data)
                    if not result.startswith("No memories matched"):
                        step.output_data = result
                        step.status = ExecutionStatus.SUCCESS
                        step.finished_at = time.time()
                        self._report(step)
                        return result
                except Exception as e:
                    logger.exception("[ExecutiveAgent] Exception in MemoryAgent. Falling back to NovaEngine: %s", e)

        output = orig_step_execute(self, step, cancel_event)

        # Log results to memory
        if getattr(self, "memory_agent", None) is not None and output:
            try:
                self.memory_agent.remember(
                    category="working",
                    key="last_step_output",
                    value=output,
                    tags=["context", "output"]
                )
            except Exception as mem_err:
                logger.debug("Failed logging execution outcome to memory: %s", mem_err)

        return output

    StepExecutor.execute = patched_step_execute

    # 3. Modify ExecutiveAgent.__init__ to accept memory_agent
    orig_exec_init = ExecutiveAgent.__init__

    def patched_exec_init(self, *args, **kwargs):
        memory_agent = kwargs.pop("memory_agent", None)
        orig_exec_init(self, *args, **kwargs)
        self.step_executor.memory_agent = memory_agent

    ExecutiveAgent.__init__ = patched_exec_init


# Monkey patch sub-agents __init__ to dynamically support self.memory_agent
def _inject_subagent_memory_injection() -> None:
    # Hooking into CodingAgent
    try:
        from agents.coding_agent import CodingAgent
        orig_coding_init = CodingAgent.__init__
        def patched_coding_init(self, *args, **kwargs):
            self.memory_agent = kwargs.pop("memory_agent", None)
            orig_coding_init(self, *args, **kwargs)
        CodingAgent.__init__ = patched_coding_init
    except ImportError:
        pass

    # Hooking into BrowserAgent
    try:
        from agents.browser_agent import BrowserAgent
        orig_browser_init = BrowserAgent.__init__
        def patched_browser_init(self, *args, **kwargs):
            self.memory_agent = kwargs.pop("memory_agent", None)
            orig_browser_init(self, *args, **kwargs)
        BrowserAgent.__init__ = patched_browser_init
    except ImportError:
        pass

    # Hooking into AndroidAgent
    try:
        from agents.android_agent import AndroidAgent
        orig_android_init = AndroidAgent.__init__
        def patched_android_init(self, *args, **kwargs):
            self.memory_agent = kwargs.pop("memory_agent", None)
            orig_android_init(self, *args, **kwargs)
        AndroidAgent.__init__ = patched_android_init
    except ImportError:
        pass

    # Hooking into WorkspaceAgent
    try:
        from agents.workspace_agent import WorkspaceAgent
        orig_workspace_init = WorkspaceAgent.__init__
        def patched_workspace_init(self, *args, **kwargs):
            self.memory_agent = kwargs.pop("memory_agent", None)
            orig_workspace_init(self, *args, **kwargs)
        WorkspaceAgent.__init__ = patched_workspace_init
    except ImportError:
        pass

    # Hooking into PlannerAgent
    try:
        from agents.planner_agent import PlannerAgent
        orig_planner_init = PlannerAgent.__init__
        def patched_planner_init(self, *args, **kwargs):
            self.memory_agent = kwargs.pop("memory_agent", None)
            orig_planner_init(self, *args, **kwargs)
        PlannerAgent.__init__ = patched_planner_init
    except ImportError:
        pass



try:
    _inject_memory_routing()
    _inject_subagent_memory_injection()
    logger.info("[MemoryAgent] Injected memory hooks across all sub-agents.")
except Exception as hook_err:
    logger.error("[MemoryAgent] Failed to inject memory hooks: %s", hook_err)
