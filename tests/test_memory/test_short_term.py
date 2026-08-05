"""
tests/test_memory/test_short_term.py
------------------------------------
Unit tests for Nova's short-term memory system.
"""

from memory.short_term import Message, ShortTermMemory


def test_initial_state() -> None:
    """Ensure memory starts empty."""
    memory = ShortTermMemory()
    assert len(memory.get_history()) == 0


def test_add_message() -> None:
    """Ensure messages are added and retrieved correctly."""
    memory = ShortTermMemory()

    memory.add_message(role="user", content="Hello Nova")
    history = memory.get_history()

    assert len(history) == 1
    assert history[0].role == "user"
    assert history[0].content == "Hello Nova"

    memory.add_message(role="assistant", content="Echo: Hello Nova")
    history = memory.get_history()

    assert len(history) == 2
    assert history[1].role == "assistant"
    assert history[1].content == "Echo: Hello Nova"


def test_clear() -> None:
    """Ensure memory is successfully cleared."""
    memory = ShortTermMemory()
    memory.add_message(role="user", content="Test")
    assert len(memory.get_history()) == 1

    memory.clear()
    assert len(memory.get_history()) == 0
