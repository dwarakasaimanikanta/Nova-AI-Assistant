"""
memory/short_term.py
--------------------
Handles short-term session conversation history for Nova.
"""

from dataclasses import dataclass
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """Represents a single message in the conversation history."""

    role: str
    content: str


class ShortTermMemory:
    """Manages conversational history for the current session in memory."""

    def __init__(self) -> None:
        """Initialize empty short-term memory."""
        self._history: list[Message] = []
        logger.debug("Short-term memory initialized.")

    def add_message(self, role: str, content: str) -> None:
        """
        Add a message to the history.

        Args:
            role: The author of the message (e.g. 'user', 'assistant').
            content: The text content of the message.
        """
        message = Message(role=role, content=content)
        self._history.append(message)
        logger.debug("Added message to short-term memory: %s -> %s", role, content)

    def get_history(self) -> list[Message]:
        """
        Retrieve all messages in the current session history.

        Returns:
            A list of Message objects.
        """
        return list(self._history)

    def clear(self) -> None:
        """Clear all messages from the session history."""
        self._history.clear()
        logger.info("Short-term memory history cleared.")
