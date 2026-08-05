"""
tests/test_core/test_engine.py
------------------------------
Unit tests for Nova's core engine orchestration.
"""

from unittest.mock import patch

from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from skills.base_skill import BaseSkill


class MockSkill(BaseSkill):
    """A mock skill for testing custom routing."""

    @property
    def name(self) -> str:
        return "Mock"

    @property
    def description(self) -> str:
        return "A mock skill for testing."

    def matches(self, user_input: str) -> bool:
        return user_input.lower() == "ping"

    def execute(self, user_input: str) -> str:
        return "pong"


def test_engine_default_skill() -> None:
    """Ensure engine defaults to registering built-in skills when none are provided."""
    memory = ShortTermMemory()
    with patch("core.engine.GEMINI_API_KEY", None):
        engine = NovaEngine(memory=memory)

        assert len(engine.skills) == 5
        assert engine.skills[0].name == "Help"
        assert engine.skills[4].name == "Echo"


def test_engine_handle_input() -> None:
    """Ensure handling input updates short-term memory and routes responses."""
    memory = ShortTermMemory()
    with patch("core.engine.GEMINI_API_KEY", None):
        engine = NovaEngine(memory=memory)

        response = engine.handle_input("Hello Nova")
        assert response.startswith("Echo: Hello Nova")

        history = memory.get_history()
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[0].content == "Hello Nova"
        assert history[1].role == "assistant"
        assert history[1].content.startswith("Echo: Hello Nova")


def test_engine_custom_skill_routing() -> None:
    """Ensure engine correctly selects and executes matching custom skills."""
    memory = ShortTermMemory()
    mock_skill = MockSkill()

    # Pass the mock skill to the engine
    engine = NovaEngine(memory=memory, skills=[mock_skill])

    # Should match and return "pong"
    response = engine.handle_input("ping")
    assert response == "pong"

    # Memory check
    history = memory.get_history()
    assert len(history) == 2
    assert history[0].content == "ping"
    assert history[1].content == "pong"
