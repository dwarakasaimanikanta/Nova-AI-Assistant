"""
tools/registry.py
-----------------
Catalog repository for registering and retrieving Nova agent tools.
"""

from typing import Any
import google.generativeai as genai

from tools.base_tool import BaseTool
from utils.logger import get_logger

logger = get_logger(__name__)


def convert_schema_to_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively convert standard JSON schema (lowercase types) to Gemini API schema format (uppercase types).

    Args:
        schema: The input dictionary representing standard JSON schema.

    Returns:
        The converted Gemini schema format dictionary.
    """
    if not isinstance(schema, dict):
        return schema

    gemini_schema = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            gemini_schema[k] = v.upper()
        elif isinstance(v, dict):
            gemini_schema[k] = convert_schema_to_gemini(v)
        elif isinstance(v, list):
            gemini_schema[k] = [
                convert_schema_to_gemini(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            gemini_schema[k] = v
    return gemini_schema


class ToolRegistry:
    """Manages active tool mappings and compiles schemas for LLM registration."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """
        Register a new tool instance in the registry.

        Args:
            tool: An instance of BaseTool.
        """
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool registration: %s", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Successfully registered tool: %s", tool.name)

    def get_tool(self, name: str) -> BaseTool | None:
        """
        Look up a tool by its unique name.

        Args:
            name: The tool name.

        Returns:
            The BaseTool instance or None if not found.
        """
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """
        Return a list of all registered tools.

        Returns:
            A list of BaseTool instances.
        """
        return list(self._tools.values())

    def get_gemini_declarations(self) -> list[genai.types.FunctionDeclaration]:
        """
        Compile all registered tools into google.generativeai.types.FunctionDeclaration.

        Returns:
            A list of FunctionDeclarations for the Gemini GenerativeModel setup.
        """
        declarations = []
        for tool in self._tools.values():
            gemini_param = convert_schema_to_gemini(tool.parameters_schema)
            decl = genai.types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=gemini_param if gemini_param else None,
            )
            declarations.append(decl)
        return declarations
