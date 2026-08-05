"""
tools/executor.py
-----------------
Executes registered tools safely, handling validation and exceptions.
"""

from typing import Any

from tools.base_tool import BaseTool
from utils.logger import get_logger

logger = get_logger(__name__)


class ToolExecutor:
    """Invokes tools with parameter validation and exception isolation."""

    def execute_tool(self, tool: BaseTool, args: dict[str, Any]) -> str:
        """
        Execute the tool with the provided arguments and capture exceptions.

        Args:
            tool: The BaseTool instance to run.
            args: Key-value dictionary containing tool arguments.

        Returns:
            The string response of the execution or an error notification message.
        """
        tool_name = tool.name
        logger.info("Executing tool '%s' with arguments: %s", tool_name, args)

        # Simple schema type/presence validation (basic sanity checks)
        schema = tool.parameters_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # 1. Check for missing required parameters
        missing_params = [p for p in required if p not in args]
        if missing_params:
            err = f"Validation Error: Tool '{tool_name}' missing required parameters: {missing_params}"
            logger.error(err)
            return err

        # 2. Execute target tool action inside safety blockades
        try:
            result = tool.execute(**args)
            logger.debug("Tool '%s' executed successfully. Output length: %d", tool_name, len(result))
            return result
        except Exception as e:
            logger.exception("Error executing tool '%s': %s", tool_name, e)
            return f"Execution Error: Tool '{tool_name}' failed during run: {e}"
