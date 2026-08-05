"""
llm/base_provider.py
--------------------
Abstract interface for LLM providers in Nova.
Allows swappable AI backends (Gemini, Claude, OpenAI).
"""

from abc import ABC, abstractmethod
from collections.abc import Generator


class BaseLLMProvider(ABC):
    """Abstract base class that all LLM provider backends must inherit from."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """
        Generate a text response or a stream of chunks from the model.

        Args:
            messages: A list of dicts with keys 'role' and 'content'.
                      e.g., [{'role': 'user', 'content': 'Hello'}]
            stream: If True, return a Generator yielding strings. Otherwise, return a str.

        Returns:
            The complete generated response string, or a Generator yielding response chunks.
        """
        pass
