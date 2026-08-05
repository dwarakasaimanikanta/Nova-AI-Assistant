"""
tools/memory_tool.py
--------------------
Consolidated long-term memory tool for Nova.
Conforms to the BaseTool interface.
"""

import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class MemoryTool(BaseTool):
    """Consolidated long-term memory manager storing user facts in a JSON file."""

    def __init__(self, filepath: Path | None = None) -> None:
        """
        Initialize the MemoryTool, loading data from JSON.

        Args:
            filepath: Optional custom Path to JSON storage. Defaults to data/long_term_memory.json.
        """
        self._filepath = filepath or (DATA_DIR / "long_term_memory.json")
        self._data: dict[str, str] = {}
        self._load_memory()

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

    def _load_memory(self) -> None:
        """Load stored facts from the JSON file on disk."""
        if not self._filepath.exists():
            self._data = {}
            return

        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info("Successfully loaded %d facts from long-term memory.", len(self._data))
        except Exception as e:
            logger.error("Failed to load long-term memory JSON: %s. Starting fresh.", e)
            self._data = {}

    def _save_memory(self) -> None:
        """Save active facts back to the JSON file on disk."""
        try:
            # Ensure the parent directory exists
            self._filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.debug("Successfully persisted long-term memory to disk.")
        except Exception as e:
            logger.error("Failed to persist long-term memory JSON: %s", e)

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action provided."

        if action == "store_fact":
            key = kwargs.get("key")
            value = kwargs.get("value")
            if not key or value is None:
                return "Failure: Missing 'key' or 'value' parameters for action 'store_fact'."

            # Lowercase the key for normalized lookups
            normalized_key = key.strip().lower()
            self._data[normalized_key] = value.strip()
            self._save_memory()
            return f"Success: Stored fact '{normalized_key}' = '{value}' in long-term memory."

        elif action == "get_fact":
            key = kwargs.get("key")
            if not key:
                return "Failure: Missing 'key' parameter for action 'get_fact'."

            normalized_key = key.strip().lower()
            if normalized_key in self._data:
                return self._data[normalized_key]
            else:
                return f"Info: No fact found for key '{normalized_key}'."

        elif action == "list_facts":
            if not self._data:
                return "Info: Long-term memory is currently empty."
            
            lines = [f"- {k}: {v}" for k, v in self._data.items()]
            return "Stored long-term memory facts:\n" + "\n".join(lines)

        else:
            return f"Failure: Unsupported memory action '{action}'."
