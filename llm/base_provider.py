"""
llm/base_provider.py
--------------------
Abstract interface for LLM providers in Nova.
Allows swappable AI backends (Gemini, Claude, OpenAI).
"""

from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any


class LLMResponse:
    """Standardized response container returned by LLM providers."""

    def __init__(self, text: str | None = None, function_calls: list[dict[str, Any]] | None = None, raw_content: Any = None) -> None:
        """
        Initialize the LLMResponse container.

        Args:
            text: The text string response, if generated.
            function_calls: Optional list of requested function calls,
                            formatted as {"name": str, "args": dict}.
            raw_content: Optional raw provider-specific response object/structure.
        """
        self.text = text
        self.function_calls = function_calls or []
        self.raw_content = raw_content


class BaseLLMProvider(ABC):
    """Abstract base class that all LLM provider backends must inherit from."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        tools: list[Any] | None = None,
    ) -> LLMResponse | Generator[str, None, None]:
        """
        Generate a text response or a stream of chunks from the model.

        Args:
            messages: A list of dicts with keys 'role' and 'content'.
                      e.g., [{'role': 'user', 'content': 'Hello'}]
            stream: If True, return a Generator yielding strings. Otherwise, return LLMResponse.
            tools: An optional list of tool specifications compatible with the provider.

        Returns:
            An LLMResponse instance, or a Generator yielding response chunks.
        """
        pass
