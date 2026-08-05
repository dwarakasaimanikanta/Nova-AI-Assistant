"""
tests/test_skills/test_skills.py
--------------------------------
Unit tests for Nova's skills (EchoSkill).
"""

from skills.echo_skill import EchoSkill


def test_echo_skill_properties() -> None:
    """Ensure EchoSkill has the correct name and description properties."""
    skill = EchoSkill()
    assert skill.name == "Echo"
    assert skill.description == "Echoes back the user's input."


def test_echo_skill_matches() -> None:
    """Ensure EchoSkill matches any user input string."""
    skill = EchoSkill()
    assert skill.matches("Hello") is True
    assert skill.matches("") is True
    assert skill.matches("   ") is True
    assert skill.matches("exit") is True


def test_echo_skill_execute() -> None:
    """Ensure EchoSkill returns the correct echoed string."""
    skill = EchoSkill()
    assert skill.execute("Hello Nova") == "Echo: Hello Nova"
    assert skill.execute("") == "Echo: "
