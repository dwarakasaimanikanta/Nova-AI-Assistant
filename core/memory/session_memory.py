import time
from typing import Any, Dict

class SessionMemory:
    """Manages short-lived in-memory variables representing current session states."""

    def __init__(self) -> None:
        self.variables: Dict[str, Any] = {
            "start_time": time.time(),
            "last_interaction": time.time()
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value
        self.variables["last_interaction"] = time.time()
