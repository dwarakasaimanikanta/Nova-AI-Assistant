import json
import os
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

class PersistentMemory:
    """Handles disk-backed persistent storage of memory variables."""

    def __init__(self, filepath: str = "data/nova_memory.json") -> None:
        self.filepath = Path(filepath)
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                logger.error("Failed to load persistent memory file: %s", e)
                self.data = {}
        else:
            self.data = {}

    def save(self) -> None:
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            logger.error("Failed to save persistent memory: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()
