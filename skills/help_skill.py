"""
skills/help_skill.py
--------------------
Dynamic help skill that registers with NovaEngine and lists all active capabilities.
"""

from skills.base_skill import BaseSkill
from utils.logger import get_logger

logger = get_logger(__name__)


class HelpSkill(BaseSkill):
    """A skill that dynamically lists all other registered skills."""

    def __init__(self, skills: list[BaseSkill] | None = None) -> None:
        """
        Initialize HelpSkill.

        Args:
            skills: Optional list of skills to display. Can be set later.
        """
        self._skills = skills or []

    def set_skills(self, skills: list[BaseSkill]) -> None:
        """
        Inject the current list of skills.

        Args:
            skills: The active skills registered in the engine.
        """
        self._skills = skills
        logger.debug("HelpSkill updated with %d registered skills.", len(skills))

    @property
    def name(self) -> str:
        """The name of the skill."""
        return "Help"

    @property
    def description(self) -> str:
        """A brief description of what the skill does."""
        return "Lists every available skill dynamically."

    def matches(self, user_input: str) -> bool:
        """
        Determine if this skill matches the user input.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            True if the input is exactly 'help' (case-insensitive).
        """
        return user_input.strip().lower() == "help"

    def execute(self, user_input: str) -> str:
        """
        Execute the help command by dynamically inspecting all loaded skills.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            A formatted string of all available skills.
        """
        logger.debug("Executing HelpSkill.")
        if not self._skills:
            return "No skills are currently registered in the engine."

        response = "Here are the skills I can perform:\n"
        for skill in self._skills:
            response += f"  • [bold]{skill.name}[/bold]: {skill.description}\n"

        return response.rstrip()
