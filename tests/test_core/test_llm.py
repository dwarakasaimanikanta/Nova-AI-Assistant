"""
tests/test_core/test_llm.py
----------------------------
Unit tests for Nova's LLM Abstraction Layer.
"""

from unittest.mock import MagicMock, patch
import pytest

from llm.gemini_provider import GeminiProvider
from llm.provider_factory import LLMProviderFactory
from llm.conversation import LLMConversation
from memory.short_term import ShortTermMemory


def test_provider_factory() -> None:
    """Ensure provider factory returns correct instance or raises ValueError."""
    # Instantiating Gemini requires a key, mock configure to bypass validation
    with patch("google.generativeai.configure") as mock_conf:
        provider = LLMProviderFactory.get_provider("gemini", "mock-api-key")
        assert isinstance(provider, GeminiProvider)
        mock_conf.assert_called_once_with(api_key="mock-api-key", transport="rest")

    with pytest.raises(ValueError):
        LLMProviderFactory.get_provider("invalid-provider", "key")


def test_gemini_message_conversion() -> None:
    """Ensure GeminiProvider translates roles to Google Gemini's schema (user/model)."""
    with patch("google.generativeai.configure"), patch("google.generativeai.GenerativeModel"):
        provider = GeminiProvider(api_key="mock")

        # Conversions check
        generic_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        translated = provider._convert_messages(generic_messages)

        assert len(translated) == 2
        assert translated[0]["role"] == "user"
        assert translated[0]["parts"] == ["Hello"]
        assert translated[1]["role"] == "model"
        assert translated[1]["parts"] == ["Hi there!"]


def test_conversation_manager() -> None:
    """Ensure LLMConversation logs and fetches histories and forwards responses."""
    memory = ShortTermMemory()
    memory.add_message(role="user", content="Hi")

    mock_provider = MagicMock()
    mock_provider.generate.return_value = "Hello! How can I help?"

    convo = LLMConversation(provider=mock_provider, memory=memory)
    response = convo.ask("Hello Nova")

    assert response == "Hello! How can I help?"
    # Verify that the provider was called with the correct history payload
    mock_provider.generate.assert_called_once_with([
        {"role": "user", "content": "Hi"},
        {"role": "user", "content": "Hello Nova"},
    ], stream=False)


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
    mock_provider.generate.return_value = "Response"

    convo = LLMConversation(provider=mock_provider, memory=memory)
    convo.ask("Active Input")

    # Expect last 10 messages: Bot 1, User 2, Bot 2, User 3, Bot 3, User 4, Bot 4, User 5, Bot 5, and the Active Input
    expected_payload = [
        {"role": "assistant", "content": "Bot 1"},
        {"role": "user", "content": "User 2"},
        {"role": "assistant", "content": "Bot 2"},
        {"role": "user", "content": "User 3"},
        {"role": "assistant", "content": "Bot 3"},
        {"role": "user", "content": "User 4"},
        {"role": "assistant", "content": "Bot 4"},
        {"role": "user", "content": "User 5"},
        {"role": "assistant", "content": "Bot 5"},
        {"role": "user", "content": "Active Input"},
    ]

    mock_provider.generate.assert_called_once_with(expected_payload, stream=False)


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
    assert len(history) == 1
    assert history[0].role == "assistant"
    assert history[0].content == "Hello world!"
