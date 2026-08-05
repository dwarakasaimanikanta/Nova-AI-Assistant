"""
skills/time_skill.py
--------------------
Time and date skill for Nova.
"""

from datetime import datetime
import re

from skills.base_skill import BaseSkill
from utils.logger import get_logger

logger = get_logger(__name__)


class TimeSkill(BaseSkill):
    """A skill that provides the current system date and time."""

    @property
    def name(self) -> str:
        """The name of the skill."""
        return "Time"

    @property
    def description(self) -> str:
        """A brief description of what the skill does."""
        return "Shows the current date and time."

    def matches(self, user_input: str) -> bool:
        """
        Determine if this skill matches the user input.

        Matches if 'time', 'date', or 'clock' are present as whole words.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            True if matched, False otherwise.
        """
        cleaned = user_input.strip().lower()
        return bool(re.search(r"\b(time|date|clock)\b", cleaned))

    def execute(self, user_input: str) -> str:
        """
        Execute the time skill.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            A string containing the formatted current date and time.
        """
        logger.debug("Executing TimeSkill.")
        now = datetime.now()
        formatted_now = now.strftime("%Y-%m-%d %H:%M:%S")
        return f"The current date and time is {formatted_now}."
