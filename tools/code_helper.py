"""
tools/code_helper.py
--------------------
Consolidated code helper and runner tool conforming to the BaseTool interface.
Supports syntax parsing via AST and secure background script executions.
"""

import ast
import os
import subprocess
import sys
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger
from config import DATA_DIR

logger = get_logger(__name__)


class CodeHelperTool(BaseTool):
    """Consolidated code helper tool for checking syntax and executing Python code blocks."""

    @property
    def name(self) -> str:
        return "code_helper"

    @property
    def description(self) -> str:
        return (
            "Checks syntax and runs Python code snippets. Supported actions: "
            "'parse_code' (analyzes syntax and structure without executing), and "
            "'execute_code' (executes Python script in an isolated file workspace)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["parse_code", "execute_code"],
                    "description": "The coding assistant action to perform.",
                },
                "code": {
                    "type": "string",
                    "description": "The Python source code snippet to parse or run.",
                },
            },
            "required": ["action", "code"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Defaults to HIGH. Overridden dynamically in PermissionGate for parse_code.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "").strip()
        code = kwargs.get("code", "")

        if not action or not code:
            return "Failure: Both 'action' and 'code' parameters are required."

        if action == "parse_code":
            try:
                tree = ast.parse(code)
                node_summary = []
                for node in ast.iter_child_nodes(tree):
                    node_summary.append(type(node).__name__)
                
                summary_str = ", ".join(node_summary[:10])
                if len(node_summary) > 10:
                    summary_str += "..."
                return f"Success: Code syntax is valid. Top-level AST elements: [{summary_str}]."
            except SyntaxError as se:
                logger.warning("Syntax error detected during parse: %s", se)
                return f"Failure: Syntax error at line {se.lineno}: {se.msg}\nCode block:\n{se.text}"
            except Exception as e:
                logger.error("Error parsing code: %s", e)
                return f"Failure: Code parsing error: {e}"

        elif action == "execute_code":
            scratch_dir = DATA_DIR / "scratch"
            scratch_dir.mkdir(exist_ok=True)
            temp_file = scratch_dir / "temp_run.py"

            try:
                logger.info("Executing user code block inside temp file '%s'.", temp_file)
                # Write code block to the temporary run file
                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write(code)

                # Locate virtual environment python binary or use fallback sys.executable
                venv_python = os.path.join("venv", "Scripts", "python.exe")
                if not os.path.exists(venv_python):
                    venv_python = sys.executable

                res = subprocess.run(
                    [venv_python, str(temp_file)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                # Clean up temporary run script
                if temp_file.exists():
                    os.remove(temp_file)

                output = []
                if res.stdout:
                    output.append(f"--- Standard Output ---\n{res.stdout.strip()}")
                if res.stderr:
                    output.append(f"--- Standard Error ---\n{res.stderr.strip()}")

                result_text = "\n\n".join(output).strip()
                if not result_text:
                    result_text = "Code completed successfully with no console output."

                return f"Execution Code: {res.returncode}\n\n{result_text}"

            except subprocess.TimeoutExpired:
                if temp_file.exists():
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                logger.warning("User code execution timed out.")
                return "Failure: Execution timed out (limit: 10s)."
            except Exception as e:
                if temp_file.exists():
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                logger.error("Failed to execute code: %s", e)
                return f"Failure executing code: {e}"

        else:
            return f"Failure: Unknown code_helper action '{action}'."
