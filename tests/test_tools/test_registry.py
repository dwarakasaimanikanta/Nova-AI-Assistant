"""
tests/test_tools/test_registry.py
---------------------------------
Unit tests for Nova's ToolRegistry.
"""

from tools.registry import ToolRegistry
from tools.builtin_tools import CalculateTool, TimeTool


def test_registry_register_and_lookup() -> None:
    """Ensure registry registers and retrieves tools correctly."""
    registry = ToolRegistry()
    calc = CalculateTool()

    registry.register_tool(calc)
    assert registry.get_tool("calculate_expression") is calc
    assert registry.get_tool("nonexistent") is None

    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0] is calc


def test_registry_gemini_declarations() -> None:
    """Ensure registry converts tool schemas to Gemini FunctionDeclarations."""
    registry = ToolRegistry()
    registry.register_tool(CalculateTool())
    registry.register_tool(TimeTool())

    declarations = registry.get_gemini_declarations()
    assert len(declarations) == 2

    calc_decl = next(d for d in declarations if d.name == "calculate_expression")
    assert calc_decl.description is not None
    # Verify parameter property names exist in parameters_json_schema
    assert "expression" in calc_decl.parameters_json_schema["properties"]
