"""
tests/test_core/test_llm.py
----------------------------
Unit tests for Nova's LLM Abstraction Layer.
"""

from unittest.mock import MagicMock, patch
import pytest

from google.genai import types
from llm.gemini_provider import GeminiProvider
from llm.provider_factory import LLMProviderFactory
from llm.conversation import LLMConversation
from memory.short_term import ShortTermMemory
from llm.base_provider import LLMResponse


def test_provider_factory() -> None:
    """Ensure provider factory returns correct instance or raises ValueError."""
    with patch("google.genai.Client") as mock_client:
        provider = LLMProviderFactory.get_provider("gemini", "mock-api-key")
        assert isinstance(provider, GeminiProvider)
        mock_client.assert_called_once_with(api_key="mock-api-key")

    with pytest.raises(ValueError):
        LLMProviderFactory.get_provider("invalid-provider", "key")


def test_gemini_message_conversion() -> None:
    """Ensure GeminiProvider translates roles to Google Gemini's schema (user/model)."""
    with patch("google.genai.Client"):
        provider = GeminiProvider(api_key="mock")

        generic_messages = [
            {"role": "user", "parts": ["Hello"]},
            {"role": "assistant", "parts": ["Hi there!"]},
        ]
        translated = provider._convert_messages(generic_messages)

        assert len(translated) == 2
        assert translated[0].role == "user"
        assert translated[0].parts[0].text == "Hello"
        assert translated[1].role == "model"
        assert translated[1].parts[0].text == "Hi there!"


def test_conversation_manager() -> None:
    """Ensure LLMConversation logs and fetches histories and forwards responses."""
    memory = ShortTermMemory()
    memory.add_message(role="user", content="Hi")

    mock_provider = MagicMock()
    mock_provider.generate.return_value = LLMResponse(text="Hello! How can I help?")

    convo = LLMConversation(provider=mock_provider, memory=memory)
    response = convo.ask("Hello Nova")

    assert response == "Hello! How can I help?"
    
    # Verify that the provider was called with the correct history payload (structured parts)
    called_payload = mock_provider.generate.call_args[0][0]
    assert len(called_payload) == 2
    assert called_payload[0]["role"] == "user"
    assert called_payload[0]["parts"] == ["Hi"]
    assert called_payload[1]["role"] == "user"
    assert called_payload[1]["parts"] == ["Hello Nova"]


def test_conversation_error_isolation() -> None:
    """Ensure LLMConversation prevents app crashes on API connection failure."""
    memory = ShortTermMemory()
    mock_provider = MagicMock()
    # Simulate API connection timed out / key blocked
    mock_provider.generate.side_effect = Exception("API connection timed out")

    convo = LLMConversation(provider=mock_provider, memory=memory)

    # Calling ask() must not raise Exception, but return friendly message
    response = convo.ask("Hello")
    assert "issue contacting my AI brain" in response


def test_conversation_history_slicing() -> None:
    """Ensure conversation history is sliced to last 10 messages."""
    memory = ShortTermMemory()
    # Log 12 messages (6 user, 6 assistant)
    for i in range(6):
        memory.add_message(role="user", content=f"User {i}")
        memory.add_message(role="assistant", content=f"Bot {i}")

    mock_provider = MagicMock()
    mock_provider.generate.return_value = LLMResponse(text="Response")

    convo = LLMConversation(provider=mock_provider, memory=memory)
    convo.ask("Active Input")

    called_payload = mock_provider.generate.call_args[0][0]
    # Expect last 10 messages: Bot 1, User 2, Bot 2, User 3, Bot 3, User 4, Bot 4, User 5, Bot 5, and the Active Input
    assert len(called_payload) == 10
    
    # Alternating roles
    assert called_payload[0]["role"] == "model"
    assert called_payload[0]["parts"] == ["Bot 1"]
    assert called_payload[1]["role"] == "user"
    assert called_payload[1]["parts"] == ["User 2"]
    assert called_payload[-1]["role"] == "user"
    assert called_payload[-1]["parts"] == ["Active Input"]


def test_conversation_manager_streaming() -> None:
    """Ensure LLMConversation streaming returns a generator and tracks latency."""
    memory = ShortTermMemory()

    mock_provider = MagicMock()
    # Mock generator output from provider
    mock_provider.generate.return_value = iter(["Hello", " world", "!"])

    convo = LLMConversation(provider=mock_provider, memory=memory)
    generator = convo.ask("Hello Nova", stream=True)

    # Validate output sequence
    chunks = list(generator)
    assert chunks == ["Hello", " world", "!"]

    # Verify that the full response was recorded in memory
    history = memory.get_history()
    # First turn is user "Hello Nova", second is assistant "Hello world!"
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"
    assert history[1].content == "Hello world!"
