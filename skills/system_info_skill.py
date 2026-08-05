"""
skills/system_info_skill.py
---------------------------
System Information skill for Nova.
"""

import os
import platform
import re

from skills.base_skill import BaseSkill
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemInfoSkill(BaseSkill):
    """A skill that details OS, Python version, and the current working directory."""

    @property
    def name(self) -> str:
        """The name of the skill."""
        return "SystemInfo"

    @property
    def description(self) -> str:
        """A brief description of what the skill does."""
        return "Shows OS, Python version and current working directory."

    def matches(self, user_input: str) -> bool:
        """
        Determine if this skill matches the user input.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            True if matched, False otherwise.
        """
        cleaned = user_input.strip().lower()
        keywords = r"\b(system|sysinfo|os|cwd|python version|working directory)\b"
        return bool(re.search(keywords, cleaned))

    def execute(self, user_input: str) -> str:
        """
        Execute the system info skill.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            A formatted string listing system metadata.
        """
        logger.debug("Executing SystemInfoSkill.")

        os_name = platform.system()
        os_release = platform.release()
        python_ver = platform.python_version()
        cwd = os.getcwd()

        response = (
            "System Information:\n"
            f"  • Operating System : {os_name} {os_release}\n"
            f"  • Python Version   : {python_ver}\n"
            f"  • Working Directory: {cwd}"
        )
        return response
