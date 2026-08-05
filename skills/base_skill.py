"""
skills/base_skill.py
--------------------
Abstract base class representing a capability/skill of Nova.
"""

from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """Abstract base class that all Nova skills must inherit from."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name/identifier of the skill."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A brief description of what the skill does."""
        pass

    @abstractmethod
    def matches(self, user_input: str) -> bool:
        """
        Determine if this skill is suitable for the given user input.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            True if the skill should be selected, False otherwise.
        """
        pass

    @abstractmethod
    def execute(self, user_input: str) -> str:
        """
        Execute the skill's logic.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            A string response to be sent back to the user interface.
        """
        pass
