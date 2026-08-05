"""
tools/memory_tool.py
--------------------
Consolidated long-term memory tool for Nova.
Conforms to the BaseTool interface.
Uses SQLite to store facts and embeddings, providing semantic search.
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from config import DATA_DIR
from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class MemoryTool(BaseTool):
    """Consolidated long-term memory manager storing user facts in a SQLite database with vector support."""

    def __init__(self, filepath: Path | None = None) -> None:
        """
        Initialize the MemoryTool, setting up the SQLite database and migrating legacy data.

        Args:
            filepath: Optional custom Path to SQLite database. Defaults to data/long_term_memory.db.
        """
        if filepath:
            if filepath.suffix == ".json":
                self._filepath = filepath.with_suffix(".db")
                self._json_filepath = filepath
            else:
                self._filepath = filepath
                self._json_filepath = filepath.with_suffix(".json")
        else:
            self._filepath = DATA_DIR / "long_term_memory.db"
            self._json_filepath = DATA_DIR / "long_term_memory.json"

        self._conn = None
        self._cursor = None
        self._init_db()
        self._migrate_json_to_sqlite()

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Manages long-term user profile memories and facts. "
            "Supports storing facts, updating facts, retrieving specific facts, "
            "and listing all facts. Use this to remember user details."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["store_fact", "get_fact", "list_facts"],
                    "description": "The action to perform on long-term memory.",
                },
                "key": {
                    "type": "string",
                    "description": "The fact key name (required for store_fact and get_fact, e.g., 'name', 'studies', 'favorite_language').",
                },
                "value": {
                    "type": "string",
                    "description": "The value string of the fact to store (required for store_fact action).",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Long-term memory profile updates are LOW risk (auto-approved)
        return RiskLevel.LOW

    def _init_db(self) -> None:
        """Initialize the SQLite database connection and create schema if not exists."""
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        try:
            # check_same_thread=False allows multi-thread/timer access safely
            self._conn = sqlite3.connect(str(self._filepath), check_same_thread=False)
            self._cursor = self._conn.cursor()
            self._cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    embedding TEXT
                )
            """)
            self._conn.commit()
            logger.info("Successfully initialized SQLite vector memory store.")
        except Exception as e:
            logger.error("Failed to initialize SQLite database: %s", e)

    def _migrate_json_to_sqlite(self) -> None:
        """Migrate existing facts from JSON to SQLite database if legacy JSON exists."""
        if not self._conn or not self._cursor:
            logger.warning("Skipping JSON migration: Database connection not initialized.")
            return

        if self._json_filepath.exists():
            logger.info("Discovered legacy JSON memory file. Migrating facts to SQLite...")
            try:
                with open(self._json_filepath, "r", encoding="utf-8") as f:
                    legacy_data = json.load(f)
                
                for key, val in legacy_data.items():
                    # Generate embedding and store in DB
                    normalized_key = key.strip().lower()
                    embedding_vector = self._get_embedding(normalized_key)
                    embedding_str = json.dumps(embedding_vector) if embedding_vector else None
                    
                    self._cursor.execute(
                        "INSERT OR REPLACE INTO memory (key, value, embedding) VALUES (?, ?, ?)",
                        (normalized_key, val.strip(), embedding_str)
                    )
                self._conn.commit()
                
                # Delete legacy JSON file
                os.remove(self._json_filepath)
                logger.info("Successfully migrated legacy memory and cleaned up legacy JSON file.")
            except Exception as e:
                logger.error("Failed to migrate legacy JSON memory: %s", e)

    def _get_embedding(self, text: str) -> list[float] | None:
        """Get 3072-dimension semantic embedding vector using Gemini API."""
        from config import GEMINI_API_KEY
        if not GEMINI_API_KEY:
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            res = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text,
                task_type="retrieval_document"
            )
            return res.get("embedding")
        except Exception as e:
            logger.warning("Failed to generate embedding from Gemini: %s", e)
            return None

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Calculate the cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm_a = sum(a * a for a in v1) ** 0.5
        norm_b = sum(b * b for b in v2) ** 0.5
        if not norm_a or not norm_b:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action provided."

        if not self._conn:
            return "Failure: Database connection is not initialized."

        if action == "store_fact":
            key = kwargs.get("key")
            value = kwargs.get("value")
            if not key or value is None:
                return "Failure: Missing 'key' or 'value' parameters for action 'store_fact'."

            normalized_key = key.strip().lower()
            val_str = value.strip()

            # Retrieve semantic embedding
            embedding_vector = self._get_embedding(normalized_key)
            embedding_str = json.dumps(embedding_vector) if embedding_vector else None

            try:
                self._cursor.execute(
                    "INSERT OR REPLACE INTO memory (key, value, embedding) VALUES (?, ?, ?)",
                    (normalized_key, val_str, embedding_str)
                )
                self._conn.commit()
                return f"Success: Stored fact '{normalized_key}' = '{val_str}' in long-term memory."
            except Exception as e:
                logger.error("Failed to store fact in database: %s", e)
                return f"Failure: Database write error: {e}"

        elif action == "get_fact":
            key = kwargs.get("key")
            if not key:
                return "Failure: Missing 'key' parameter for action 'get_fact'."

            normalized_key = key.strip().lower()

            try:
                # 1. Exact lookup
                self._cursor.execute("SELECT value FROM memory WHERE key = ?", (normalized_key,))
                row = self._cursor.fetchone()
                if row:
                    return row[0]

                # 2. Semantic lookup fallback
                query_vector = self._get_embedding(normalized_key)
                if query_vector:
                    # Retrieve all stored keys and embeddings
                    self._cursor.execute("SELECT key, value, embedding FROM memory WHERE embedding IS NOT NULL")
                    rows = self._cursor.fetchall()
                    
                    best_match_val = None
                    best_score = -1.0
                    
                    for stored_key, stored_val, stored_emb_str in rows:
                        try:
                            stored_vector = json.loads(stored_emb_str)
                            if len(stored_vector) == len(query_vector):
                                score = self._cosine_similarity(query_vector, stored_vector)
                                if score > best_score:
                                    best_score = score
                                    best_match_val = stored_val
                        except Exception:
                            continue
                    
                    # Set semantic score match threshold to 0.65
                    if best_score >= 0.65:
                        logger.info("Semantic query '%s' matched key with score %f.", normalized_key, best_score)
                        return best_match_val

                return f"Info: No fact found for key '{normalized_key}'."

            except Exception as e:
                logger.error("Database query error: %s", e)
                return f"Failure: Database read error: {e}"

        elif action == "list_facts":
            try:
                self._cursor.execute("SELECT key, value FROM memory")
                rows = self._cursor.fetchall()
                if not rows:
                    return "Info: Long-term memory is currently empty."
                
                lines = [f"- {key}: {val}" for key, val in rows]
                return "Stored long-term memory facts:\n" + "\n".join(lines)
            except Exception as e:
                logger.error("Database list error: %s", e)
                return f"Failure: Database read error: {e}"

        else:
            return f"Failure: Unsupported memory action '{action}'."

    def close(self) -> None:
        """Close connection cleanly if active."""
        if hasattr(self, "_conn") and self._conn:
            try:
                self._conn.close()
            except Exception as e:
                logger.error("Failed to close SQLite connection: %s", e)
            finally:
                self._conn = None
                self._cursor = None

    def __del__(self) -> None:
        """Close connection cleanly if active."""
        self.close()
