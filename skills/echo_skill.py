"""
skills/echo_skill.py
--------------------
A simple implementation of EchoSkill for Nova.
"""

from skills.base_skill import BaseSkill
from utils.logger import get_logger

logger = get_logger(__name__)


class EchoSkill(BaseSkill):
    """A skill that simply echoes the user input back to the user."""

    @property
    def name(self) -> str:
        """The name of the skill."""
        return "Echo"

    @property
    def description(self) -> str:
        """A brief description of what the skill does."""
        return "Echoes back the user's input."

    def matches(self, user_input: str) -> bool:
        """
        Determine if this skill matches the user input.

        For this phase, EchoSkill matches all standard inputs.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            Always True.
        """
        return True

    def execute(self, user_input: str) -> str:
        """
        Execute the echo skill.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            The input prefixed with 'Echo: '.
        """
        logger.debug("Executing EchoSkill on input: %s", user_input)
        return f"Echo: {user_input}"
