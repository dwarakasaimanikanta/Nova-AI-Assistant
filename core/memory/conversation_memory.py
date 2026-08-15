from typing import Dict, List

class ConversationMemory:
    """Manages active dialogue turns and context history."""

    def __init__(self) -> None:
        self.history: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def get_history(self) -> List[Dict[str, str]]:
        return self.history

    def clear(self) -> None:
        self.history.clear()
