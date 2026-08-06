"""
core/planner.py
---------------
Agentic execution planner loop coordinating LLM requests, tool calls, and performance logging.
"""

from collections.abc import Generator
import time

from memory.short_term import ShortTermMemory
from llm.base_provider import BaseLLMProvider
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from tools.permission_gate import PermissionGate
from utils.logger import get_logger

logger = get_logger(__name__)


class AgentPlanner:
    """Manages iterative conversation loops, planning, and executing tool calls."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        memory: ShortTermMemory,
        registry: ToolRegistry,
        executor: ToolExecutor,
        permission_gate: PermissionGate,
        max_iterations: int = 5,
    ) -> None:
        """
        Initialize the AgentPlanner loop manager.

        Args:
            provider: Swappable LLM provider client.
            memory: ShortTermMemory storage.
            registry: The tool catalog.
            executor: The validated runner.
            permission_gate: The security gate interceptor.
            max_iterations: Execution limit ceiling to prevent runaways.
        """
        self.provider = provider
        self.memory = memory
        self.registry = registry
        self.executor = executor
        self.permission_gate = permission_gate
        self.max_iterations = max_iterations

    def ask(self, user_input: str, stream: bool = False) -> str | Generator[str, None, None]:
        """
        Query the LLM provider with tool execution loop and return the final response.

        Args:
            user_input: The active prompt query.
            stream: True to return a generator of the final text response.

        Returns:
            The string response or a generator of string chunks.
        """
        start_planning = time.perf_counter()

        # Metrics trackers
        tool_selection_time = 0.0
        tool_execution_time = 0.0
        llm_generation_time = 0.0

        # 1. Log the user's input in memory if not already the latest message
        raw_history = self.memory.get_history()
        if (
            not raw_history
            or raw_history[-1].role != "user"
            or raw_history[-1].content != user_input
        ):
            self.memory.add_message(role="user", content=user_input)
            raw_history = self.memory.get_history()

        # 2. Compile conversational history from memory
        from google.genai import types
        history_payload = []
        i = 0
        while i < len(raw_history):
            msg = raw_history[i]
            if msg.role == "user":
                history_payload.append({
                    "role": "user",
                    "parts": [msg.content]
                })
                i += 1
            elif msg.role == "assistant":
                if msg.raw_content is not None:
                    history_payload.append(msg.raw_content)
                else:
                    if msg.function_calls:
                        parts = []
                        for fc in msg.function_calls:
                            parts.append(
                                types.Part.from_function_call(
                                    name=fc["name"],
                                    args=fc["args"]
                                )
                            )
                        history_payload.append({
                            "role": "model",
                            "parts": parts
                        })
                    else:
                        history_payload.append({
                            "role": "model",
                            "parts": [msg.content or ""]
                        })
                i += 1
            elif msg.role == "tool":
                tool_parts = []
                while i < len(raw_history) and raw_history[i].role == "tool":
                    t_msg = raw_history[i]
                    part = types.Part.from_function_response(
                        name=t_msg.name or "",
                        response={"result": t_msg.content}
                    )
                    tool_parts.append(part)
                    i += 1
                history_payload.append({
                    "role": "user",
                    "parts": tool_parts
                })

        # Limit history payload context window to last 10 turns safely, avoiding orphan function_responses
        history_payload = history_payload[-10:]
        while history_payload:
            first_msg = history_payload[0]
            has_response = False
            if isinstance(first_msg, dict):
                parts = first_msg.get("parts", [])
                for p in parts:
                    if hasattr(p, "function_response") or (isinstance(p, dict) and "function_response" in p):
                        has_response = True
                        break
            elif hasattr(first_msg, "parts"):
                for p in first_msg.parts:
                    if hasattr(p, "function_response"):
                        has_response = True
                        break
            
            if has_response:
                history_payload = history_payload[1:]
            else:
                break

        # 3. Get active tool declarations
        declarations = self.registry.get_gemini_declarations()
        logger.debug("Active tool declarations count: %d", len(declarations))

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            logger.info("Starting planning loop iteration %d/%d", iteration, self.max_iterations)

            # Call provider synchronously to check if a tool call is needed
            start_selection = time.perf_counter()
            try:
                response = self.provider.generate(
                    messages=history_payload,
                    stream=False,
                    tools=declarations if declarations else None,
                )
            except Exception as e:
                logger.exception("Provider error in planning loop: %s", e)
                return "I encountered an error contacting my AI brain. Please try again."

            selection_latency = time.perf_counter() - start_selection
            # Attribute first call to tool selection, subsequent turns represent LLM response generation
            if iteration == 1:
                tool_selection_time += selection_latency
            else:
                llm_generation_time += selection_latency

            if response.function_calls:
                # Log model's execution intent in payload and short-term memory
                self.memory.add_message(role="assistant", function_calls=response.function_calls, raw_content=response.raw_content)
                if response.raw_content:
                    history_payload.append(response.raw_content)
                else:
                    history_payload.append({
                        "role": "assistant",
                        "content": None,
                        "function_calls": response.function_calls,
                    })

                start_tool_exec = time.perf_counter()
                results = []
                should_direct_return = False
                direct_response = ""

                tool_parts = []
                # Process all requested function calls sequentially
                for fc in response.function_calls:
                    tool_name = fc["name"]
                    args = fc["args"]

                    tool = self.registry.get_tool(tool_name)
                    if not tool:
                        result = f"Error: Tool '{tool_name}' is not registered."
                        logger.error(result)
                    else:
                        # Safety verification gate check
                        if not self.permission_gate.check_permission(tool, args):
                            result = f"Permission Denied: User refused execution of tool '{tool_name}'."
                            logger.warning("Tool execution blocked by permission gate: %s", tool_name)
                        else:
                            # Run tool
                            result = self.executor.execute_tool(tool, args)

                    # Append execution output back into memory sequentially
                    self.memory.add_message(role="tool", content=result, name=tool_name)
                    results.append(result)

                    # Add response part to the grouped payload list
                    tool_parts.append({
                        "function_response": {
                            "name": tool_name,
                            "response": {"result": result}
                        }
                    })

                    # Optimize: If a local deterministic tool already returns a full human-readable response, skip subsequent LLM turn
                    direct_return_tools = {"calculate_expression", "get_system_time", "get_system_info", "file_manager", "browser", "terminal", "memory", "web_search", "system_control", "scheduler", "code_helper", "voice_tts", "system_monitor"}
                    if tool_name in direct_return_tools:
                        should_direct_return = True
                        direct_response = result

                # Append the grouped tool responses as a single message to history_payload
                if tool_parts:
                    history_payload.append({
                        "role": "user",
                        "parts": tool_parts
                    })

                tool_execution_time += time.perf_counter() - start_tool_exec

                # If direct return was triggered, bypass the final LLM reasoning generation request
                if should_direct_return:
                    self.memory.add_message(role="assistant", content=direct_response)
                    total_time = time.perf_counter() - start_planning
                    logger.info(
                        "[Metrics] Execution breakdown:\n"
                        "  • Planning / Tool Selection: %.4f seconds\n"
                        "  • Tool Execution           : %.4f seconds\n"
                        "  • LLM Response Generation  : %.4f seconds\n"
                        "  • Total Response Latency   : %.4f seconds",
                        tool_selection_time,
                        tool_execution_time,
                        llm_generation_time,
                        total_time,
                    )
                    if stream:
                        def direct_gen() -> Generator[str, None, None]:
                            yield direct_response
                        return direct_gen()
                    return direct_response

                # Slice payload window to last 10 elements
                history_payload = history_payload[-10:]
                continue

            else:
                # No more function calls requested! The model produced a final conversational answer.
                final_text = response.text or "I completed the tasks but have no message to report."
                self.memory.add_message(role="assistant", content=final_text, raw_content=response.raw_content)

                total_time = time.perf_counter() - start_planning
                logger.info(
                    "[Metrics] Execution breakdown:\n"
                    "  • Planning / Tool Selection: %.4f seconds\n"
                    "  • Tool Execution           : %.4f seconds\n"
                    "  • LLM Response Generation  : %.4f seconds\n"
                    "  • Total Response Latency   : %.4f seconds",
                    tool_selection_time,
                    tool_execution_time,
                    llm_generation_time,
                    total_time,
                )

                if stream:
                    def text_generator() -> Generator[str, None, None]:
                        yield final_text
                    return text_generator()

                return final_text

        logger.warning("Agent planning loop reached max iterations (%d). Exiting loop.", self.max_iterations)
        err_msg = "I spent too long executing tasks and had to stop to prevent an infinite loop."
        self.memory.add_message(role="assistant", content=err_msg)

        total_time = time.perf_counter() - start_planning
        logger.info(
            "[Metrics] Execution breakdown (Loop aborted):\n"
            "  • Planning / Tool Selection: %.4f seconds\n"
            "  • Tool Execution           : %.4f seconds\n"
            "  • LLM Response Generation  : %.4f seconds\n"
            "  • Total Response Latency   : %.4f seconds",
            tool_selection_time,
            tool_execution_time,
            llm_generation_time,
            total_time,
        )

        if stream:
            def err_generator() -> Generator[str, None, None]:
                yield err_msg
            return err_generator()

        return err_msg
