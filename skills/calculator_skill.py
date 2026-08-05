"""
skills/calculator_skill.py
--------------------------
Calculator skill for Nova to perform safe arithmetic operations.
"""

import re

from skills.base_skill import BaseSkill
from utils.logger import get_logger

logger = get_logger(__name__)


class CalculatorSkill(BaseSkill):
    """A skill that evaluates basic arithmetic calculations (+, -, *, /)."""

    @property
    def name(self) -> str:
        """The name of the skill."""
        return "Calculator"

    @property
    def description(self) -> str:
        """A brief description of what the skill does."""
        return "Supports simple arithmetic calculations (+, -, *, /)."

    def matches(self, user_input: str) -> bool:
        """
        Determine if this skill matches the user input.

        Matches if input begins with 'calc', 'calculate', or 'compute',
        or is a pure mathematical expression.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            True if matched, False otherwise.
        """
        cleaned = user_input.strip().lower()

        # 1. Match calculate/calc/compute command prefix
        if re.match(r"^(calc|calculate|compute)\b", cleaned):
            return True

        # 2. Match raw math expressions (e.g. '2 + 2')
        # Requires at least one digit, at least one operator, and only valid characters
        has_digits = bool(re.search(r"\d", cleaned))
        has_operator = bool(re.search(r"[\+\-\*/]", cleaned))
        only_valid_chars = bool(re.match(r"^[\d\s\+\-\*/\(\)\.]+$", cleaned))

        return has_digits and has_operator and only_valid_chars

    def execute(self, user_input: str) -> str:
        """
        Safely execute the calculation query.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            A string containing the calculated result or an error message.
        """
        logger.debug("Executing CalculatorSkill.")

        # Strip prefixes safely using word boundaries
        expr = re.sub(r"^(calculate|compute|calc)\b\s*", "", user_input.strip(), flags=re.IGNORECASE)
        expr = expr.strip()

        # Validate that characters are strictly mathematical
        if not re.match(r"^[\d\s\+\-\*/\(\)\.]+$", expr):
            logger.warning("Rejected CalculatorSkill expression: '%s' due to invalid characters.", expr)
            return "Error: Expression contains invalid characters. Only numbers and +, -, *, / are supported."

        try:
            # Safe evaluation with isolated environment (no built-in functions allowed)
            result = eval(expr, {"__builtins__": None}, {})
            logger.info("Successfully evaluated: %s = %s", expr, result)
            return f"{expr} = {result}"
        except ZeroDivisionError:
            logger.warning("Zero division error in expression: %s", expr)
            return "Error: Division by zero is not allowed."
        except Exception as e:
            logger.warning("Failed to evaluate expression: %s, error: %s", expr, e)
            return f"Error: Invalid arithmetic expression. Details: {e}"
