"""
tests/test_skills/test_built_in_skills.py
-----------------------------------------
Unit tests for Nova's Phase 3 built-in skills.
"""

from datetime import datetime
import os
import platform

from skills.time_skill import TimeSkill
from skills.calculator_skill import CalculatorSkill
from skills.system_info_skill import SystemInfoSkill
from skills.help_skill import HelpSkill
from skills.echo_skill import EchoSkill


def test_time_skill() -> None:
    """Test TimeSkill matching logic and execution format."""
    skill = TimeSkill()

    # Match tests
    assert skill.matches("What is the time?") is True
    assert skill.matches("give me the current date") is True
    assert skill.matches("clock check") is True
    assert skill.matches("update dependencies") is False  # Substring 'date' shouldn't match

    # Execution tests
    response = skill.execute("time")
    current_year = str(datetime.now().year)
    assert "The current date and time is" in response
    assert current_year in response


def test_calculator_skill() -> None:
    """Test CalculatorSkill matching, evaluation, and safety guards."""
    skill = CalculatorSkill()

    # Match tests
    assert skill.matches("calculate 2 + 2") is True
    assert skill.matches("calc 10 * (3 - 1)") is True
    assert skill.matches("2 + 2") is True
    assert skill.matches("100 / 4.5") is True
    assert skill.matches("hello") is False
    assert skill.matches("2 + hello") is False  # Mixed invalid string

    # Execution success tests
    assert skill.execute("2 + 2") == "2 + 2 = 4"
    assert skill.execute("calc 10 * 5") == "10 * 5 = 50"
    assert skill.execute("calculate (10 - 2) / 4") == "(10 - 2) / 4 = 2.0"

    # Execution error tests (division by zero)
    assert "division by zero" in skill.execute("10 / 0").lower()

    # Execution security character guards
    assert "invalid characters" in skill.execute("2 + __import__('os')").lower()


def test_system_info_skill() -> None:
    """Test SystemInfoSkill matches and platform metadata retrieval."""
    skill = SystemInfoSkill()

    # Match tests
    assert skill.matches("show system info") is True
    assert skill.matches("cwd") is True
    assert skill.matches("what os is this?") is True
    assert skill.matches("check py version") is False

    # Execution tests
    response = skill.execute("system")
    assert "System Information:" in response
    assert platform.system() in response
    assert platform.python_version() in response
    assert os.getcwd() in response


def test_help_skill() -> None:
    """Test HelpSkill matching and dynamic listings formatting."""
    skill = HelpSkill()

    # Match tests
    assert skill.matches("help") is True
    assert skill.matches("HELP") is True
    assert skill.matches("helper") is False

    # Empty list verification
    assert "No skills" in skill.execute("help")

    # Dynamic registration verification
    skills_list = [skill, EchoSkill()]
    skill.set_skills(skills_list)

    response = skill.execute("help")
    assert "Here are the skills I can perform:" in response
    assert "Help" in response
    assert "Echo" in response
