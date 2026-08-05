"""
core/engine.py
--------------
Main engine logic and coordination for the Nova AI Assistant supporting tool calling.
"""

from collections.abc import Generator

from config import GEMINI_API_KEY
from memory.short_term import ShortTermMemory
from skills.base_skill import BaseSkill
from skills.echo_skill import EchoSkill
from skills.help_skill import HelpSkill
from skills.time_skill import TimeSkill
from skills.calculator_skill import CalculatorSkill
from skills.system_info_skill import SystemInfoSkill
from llm.provider_factory import LLMProviderFactory
from core.planner import AgentPlanner
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from tools.permission_gate import PermissionGate
from utils.logger import get_logger

logger = get_logger(__name__)


class NovaEngine:
    """The central brain of Nova, orchestrating memory, skills, and tools."""

    def __init__(
        self,
        memory: ShortTermMemory,
        skills: list[BaseSkill] | None = None,
    ) -> None:
        """
        Initialize the engine with a memory store, a list of skills, and tools.

        Args:
            memory: An instance of ShortTermMemory.
            skills: An optional list of skills. Defaults to registering built-in skills.
        """
        self.memory = memory
        if skills is None:
            # Auto-register all built-in skills for Phase 3 (offline capability)
            help_skill = HelpSkill()
            self.skills = [
                help_skill,
                TimeSkill(),
                CalculatorSkill(),
                SystemInfoSkill(),
                EchoSkill(),  # Fallback matches everything, so keep last
            ]
            # Bind the skill list reference so HelpSkill displays all of them
            help_skill.set_skills(self.skills)
            logger.info("Engine registered built-in skills: Help, Time, Calculator, SystemInfo, Echo.")
        else:
            self.skills = skills
            # Ensure any custom HelpSkill instances receive the custom skills list
            for skill in self.skills:
                if isinstance(skill, HelpSkill):
                    skill.set_skills(self.skills)
            logger.info("Engine initialized with %d custom skills.", len(skills))

        # Initialize Tool calling subsystems
        self.registry = ToolRegistry()
        self.executor = ToolExecutor()
        self.permission_gate = PermissionGate()

        # Register built-in tools
        from tools.builtin_tools import CalculateTool, TimeTool, SystemInfoTool
        self.registry.register_tool(CalculateTool())
        self.registry.register_tool(TimeTool())
        self.registry.register_tool(SystemInfoTool())
        logger.info("Registered built-in tools: calculate_expression, get_system_time, get_system_info.")

        # Initialize plugins and dynamically load all discovered modules
        self.plugins = []
        from plugins.loader import PluginLoader
        loader = PluginLoader()
        for plugin in loader.discover_and_load_plugins():
            self.load_plugin(plugin)

        # Initialize LLM Brain / Agentic Planner if configured in environment
        self.conversation = None
        if GEMINI_API_KEY:
            try:
                provider = LLMProviderFactory.get_provider("gemini", GEMINI_API_KEY)
                self.conversation = AgentPlanner(
                    provider=provider,
                    memory=self.memory,
                    registry=self.registry,
                    executor=self.executor,
                    permission_gate=self.permission_gate,
                )
                logger.info("AgentPlanner initialized successfully using Gemini.")
            except Exception as e:
                logger.exception("Failed to initialize AgentPlanner: %s", e)
        else:
            logger.warning("GEMINI_API_KEY not found in environment. Running in offline/echo fallback mode.")

    def load_plugin(self, plugin: Any) -> None:
        """
        Load a plugin module, registering all of its tools dynamically.

        Args:
            plugin: An instance of BasePlugin.
        """
        self.plugins.append(plugin)
        for tool in plugin.get_tools():
            self.registry.register_tool(tool)
        logger.info("Loaded plugin '%s' providing %d tools.", plugin.name, len(plugin.get_tools()))

    def handle_input(self, user_input: str, stream: bool = False) -> str | Generator[str, None, None]:
        """
        Process the user input, query matching skills, update memory, and return a response.

        Args:
            user_input: The raw input string from the user.
            stream: True to return a generator of response chunks (only valid for LLM routing).

        Returns:
            The text response or a generator yielding chunks.
        """
        cleaned_input = user_input.strip()
        logger.info("Processing user input: '%s' (stream=%s)", cleaned_input, stream)

        # 1. Log the user's message in memory
        self.memory.add_message(role="user", content=cleaned_input)

        # Route shell commands directly to TerminalTool to prevent LLM routing/hallucination errors
        parts = cleaned_input.split()
        base_cmd = parts[0].lower() if parts else ""
        shell_commands = {"mkdir", "rmdir", "cd", "dir", "git", "python", "pip", "pwd"}

        if base_cmd in shell_commands:
            tool = self.registry.get_tool("terminal")
            if tool:
                args = {"command": cleaned_input}
                # Safety verification gate check
                if not self.permission_gate.check_permission(tool, args):
                    response = f"Permission Denied: User refused execution of command '{cleaned_input}'."
                else:
                    response = self.executor.execute_tool(tool, args)

                self.memory.add_message(role="assistant", content=response)
                if stream:
                    def direct_gen() -> Generator[str, None, None]:
                        yield response
                    return direct_gen()
                return response

        # 2. Find a matching specific command skill (excluding EchoSkill fallback)
        response = None
        for skill in self.skills:
            if skill.name == "Echo":
                continue
            if skill.matches(cleaned_input):
                logger.debug("Found matching skill: %s", skill.name)
                try:
                    response = skill.execute(cleaned_input)
                except Exception as e:
                    logger.exception("Error executing skill %s: %s", skill.name, e)
                    response = f"An error occurred while executing the {skill.name} skill."
                break

        # 3. If no command skill matched, try to route to the AI Agentic Planner
        if response is None and self.conversation is not None:
            return self.conversation.ask(cleaned_input, stream=stream)

        # 4. Fallback to EchoSkill if LLM is not active and no other skill matched
        if response is None:
            echo_skill = next((s for s in self.skills if s.name == "Echo"), None)
            if echo_skill:
                response = echo_skill.execute(cleaned_input)
                response += "\n[dim](Tip: Configure GEMINI_API_KEY in your .env file to enable the AI brain.)[/dim]"
            else:
                logger.warning("No skill or LLM matched the input: '%s'", cleaned_input)
                response = "I'm sorry, I don't know how to handle that request yet."

        # 5. Log non-streaming response in memory (streaming response is logged dynamically inside the planner)
        self.memory.add_message(role="assistant", content=response)

        # If streaming was requested but we hit a local command or fallback, return it as a single chunk generator
        if stream:
            def single_chunk_gen() -> Generator[str, None, None]:
                yield response
            return single_chunk_gen()

        return response
