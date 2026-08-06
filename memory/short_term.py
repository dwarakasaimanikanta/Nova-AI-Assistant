"""
memory/short_term.py
--------------------
Handles short-term session conversation history for Nova.
"""

from dataclasses import dataclass
from typing import Any
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """Represents a single message in the conversation history."""

    role: str
    content: str | None = None
    function_calls: list[dict] | None = None
    name: str | None = None
    raw_content: Any = None


class ShortTermMemory:
    """Manages conversational history for the current session in memory."""

    def __init__(self) -> None:
        """Initialize empty short-term memory."""
        self._history: list[Message] = []
        logger.debug("Short-term memory initialized.")

    def add_message(
        self,
        role: str,
        content: str | None = None,
        function_calls: list[dict] | None = None,
        name: str | None = None,
        raw_content: Any = None,
    ) -> None:
        """
        Add a message to the history.

        Args:
            role: The author of the message (e.g. 'user', 'assistant').
            content: The text content of the message.
            function_calls: The requested tool calls.
            name: The tool name if it is a tool response.
            raw_content: Raw provider response content to preserve metadata.
        """
        message = Message(role=role, content=content, function_calls=function_calls, name=name, raw_content=raw_content)
        self._history.append(message)
        logger.debug("Added message to short-term memory: %s (has_content: %s, has_calls: %s)", role, content is not None, function_calls is not None)

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
