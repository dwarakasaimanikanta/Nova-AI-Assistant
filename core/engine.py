"""
core/engine.py
--------------
Main engine logic and coordination for the Nova AI Assistant supporting tool calling.
"""

from collections.abc import Generator
from typing import Any

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
        # Default permission callback: approve all voice-safe tool actions.
        # The PermissionGate already auto-approves LOW-risk actions without calling this
        # callback. This callback is ONLY called for HIGH-risk tool actions.
        # We broaden approval here to allow all reasonable desktop AI operations.
        def default_permission_callback(tool_name: str, args: dict[str, Any]) -> bool:
            action = args.get("action", "")
            # File operations: create, write, read, list, delete, rename, move, copy
            if tool_name == "file_manager":
                return True  # All file_manager actions allowed
            # System control: launch and close desktop apps
            if tool_name == "system_control":
                return True  # launch_app, close_app, volume, etc.
            # Terminal: run shell commands
            if tool_name == "terminal":
                return True
            # Browser: open URLs, close browser (already LOW risk per PermissionGate,
            # but listed here for completeness in case risk level changes)
            if tool_name in ("browser", "browser_agent"):
                return True
            # Desktop automation: open applications, take screenshots
            if tool_name == "desktop_automation":
                return True
            # Web search, calendar, android: always approved
            if tool_name in ("web_search", "calendar", "android"):
                return True
            # Code helper (parse, write): approved
            if tool_name == "code_helper":
                return True
            # Unknown tool: deny by default and log
            logger.warning(
                "[PermissionGate] Unknown HIGH-risk tool '%s' with action '%s' — denied by default.",
                tool_name, action
            )
            return False
        self.permission_gate = PermissionGate(callback=default_permission_callback)
        self._selected_language = "en"


        # Initialize plugins and dynamically load all discovered modules
        self.plugins = []
        from plugins.loader import PluginLoader
        loader = PluginLoader()
        for plugin in loader.discover_and_load_plugins():
            self.load_plugin(plugin)

        # Initialize LLM Brain / Agentic Planner if configured in environment
        self.conversation = None
        try:
            # Check if either Gemini key is set or local Ollama is healthy
            from llm.local_llm_manager import LocalLLMManager
            local_manager = LocalLLMManager()
            
            if GEMINI_API_KEY or local_manager.is_healthy():
                provider = LLMProviderFactory.get_provider("routing", GEMINI_API_KEY)
                self.conversation = AgentPlanner(
                    provider=provider,
                    memory=self.memory,
                    registry=self.registry,
                    executor=self.executor,
                    permission_gate=self.permission_gate,
                )
                logger.info("AgentPlanner initialized successfully using Routing LLM Provider.")
            else:
                logger.warning("No online or local LLM pathways detected at startup. Running in offline/echo fallback mode.")
        except Exception as brain_err:
            logger.warning("Could not initialize Agentic Planner brain: %s", brain_err)

        # Set voice_manager reference if loaded
        self.voice_manager = None

        logger.info("NovaEngine initialized successfully.")

    @property
    def selected_language(self) -> str:
        from core.language_session import LanguageSession
        return LanguageSession().selected_language

    @selected_language.setter
    def selected_language(self, val: str) -> None:
        from core.language_session import LanguageSession
        LanguageSession().selected_language = val
        logger.info("[LANGUAGE-STATE]")
        logger.info("Selected response language: %s", LanguageSession().selected_language)

    @property
    def response_language(self) -> str:
        from core.language_session import LanguageSession
        return LanguageSession().selected_language

    @response_language.setter
    def response_language(self, val: str) -> None:
        self.selected_language = val

    @property
    def telugu_mode(self) -> bool:
        from core.language_session import LanguageSession
        return LanguageSession().selected_language == "te"

    @telugu_mode.setter
    def telugu_mode(self, val: bool) -> None:
        if val:
            self.selected_language = "te"
        else:
            if self.selected_language == "te":
                self.selected_language = "en"


    def load_plugin(self, plugin: Any) -> None:
        """
        Load a plugin module, registering all of its tools dynamically.

        Args:
            plugin: An instance of BasePlugin.
        """
        self.plugins.append(plugin)
        for tool in plugin.get_tools():
            self.registry.register_tool(tool)
        
        # Initialize the plugin if it defines initialize_plugin hook
        if hasattr(plugin, "initialize_plugin"):
            try:
                plugin.initialize_plugin(self)
            except Exception as e:
                logger.error("Failed to run initialize_plugin hook for plugin %s: %s", plugin.name, e)

        logger.info("Loaded plugin '%s' providing %d tools.", plugin.name, len(plugin.get_tools()))

    def _load_contacts(self) -> dict[str, str]:
        """Load contact list from data/contacts.json safely."""
        import json
        from pathlib import Path
        contacts_path = Path("data/contacts.json")
        if contacts_path.exists():
            try:
                with open(contacts_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load contacts.json: %s", e)
        return {}

    def correct_contact_names(self, original_input: str) -> str:
        """Fuzzy match and correct spoken contact names in user command."""
        import difflib
        contacts = self._load_contacts()
        if not contacts:
            return original_input

        lower_input = original_input.lower()
        action_keywords = {
            "call", "కాల్", "చేయి", "చేయ్", 
            "message", "sms", "మెసేజ్", "సందేశం", "పంపు", "పంపించు",
            "whatsapp", "వాట్సాప్"
        }
        has_action = any(kw in lower_input for kw in action_keywords)
        if not has_action:
            return original_input

        # Transliteration mapping for Telugu spoken/transcribed contact names
        telugu_to_english = {
            "అమ్మ": "amma",
            "నాన్న": "Dad",
            "జ్ఞాన": "Gnana",
            "దీపక్": "Deepak",
            "ప్రదీప్": "Pradeep",
            "అహమద్": "Ahamed",
            "అహమ్మద్": "Ahamed",
            "రవి": "Ravi",
        }

        def normalize_phonetic(name: str) -> str:
            name_lower = name.lower()
            name_lower = name_lower.replace("y", "i")
            name_lower = name_lower.replace("e", "a")
            collapsed = []
            for ch in name_lower:
                if not collapsed or collapsed[-1] != ch:
                    collapsed.append(ch)
            return "".join(collapsed)

        import string
        punctuation_set = set(string.punctuation) | {"“", "”", "‘", "’", '"', "'"}

        words = original_input.split()
        corrected_words = []

        for word in words:
            base_word = word
            suffix = ""
            prefix = ""

            # Strip trailing punctuation
            while base_word and base_word[-1] in punctuation_set:
                suffix = base_word[-1] + suffix
                base_word = base_word[:-1]

            # Strip leading punctuation
            while base_word and base_word[0] in punctuation_set:
                prefix = prefix + base_word[0]
                base_word = base_word[1:]

            # Strip Telugu suffixes
            telugu_suffixes = ["కి", "కు", "తో", "ని", "ను", "యొక్క"]
            telugu_suffix = ""
            for ts in telugu_suffixes:
                if base_word.endswith(ts):
                    telugu_suffix = ts
                    base_word = base_word[:-len(ts)]
                    break

            # Handle Telugu translation if exists
            base_word_cleaned = base_word.strip()
            if base_word_cleaned in telugu_to_english:
                base_word = telugu_to_english[base_word_cleaned]

            if base_word:
                best_match = None
                best_ratio = 0.0

                for contact_name in contacts.keys():
                    ratio_orig = difflib.SequenceMatcher(None, base_word.lower(), contact_name.lower()).ratio()
                    ratio_norm = difflib.SequenceMatcher(None, normalize_phonetic(base_word), normalize_phonetic(contact_name)).ratio()
                    ratio = max(ratio_orig, ratio_norm)

                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = contact_name

                if best_ratio >= 0.80 and best_match:
                    base_word = best_match

            corrected_word = prefix + base_word + telugu_suffix + suffix
            corrected_words.append(corrected_word)

        return " ".join(corrected_words)

    def handle_input(self, user_input: str, stream: bool = False, selected_language: str = None, intent_category: str = None) -> str | Generator[str, None, None]:
        """
        Process the user input, query matching skills, update memory, and return a response.

        Args:
            user_input: The raw input string from the user.
            stream: True to return a generator of response chunks (only valid for LLM routing).
            selected_language: Optional selected language override.

        Returns:
            The text response or a generator yielding chunks.
            """
        if selected_language:
            self.selected_language = selected_language
        original_input = user_input.strip()
        
        # ── PART 1: Smart Command Normalizer ────────────────────────────────
        normalized = original_input
        import re
        normalized = re.sub(r"\b(vscore|vs\s+code|visual\s+studio)\b", "VS Code", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\b(youtube|you\s+tube|u\s+tube)\b", "YouTube", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\b(chrome\s+browser|google\s+chrome)\b", "Chrome", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\b(git\s+hub)\b", "GitHub", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\b(chat\s+gpt)\b", "ChatGPT", normalized, flags=re.IGNORECASE)
        
        if normalized != original_input:
            logger.info("[NORMALIZER] Normalized user input: %r -> %r", original_input, normalized)
            original_input = normalized

        logger.info("Processing user input: '%s' (stream=%s)", original_input, stream)

        # Apply contact name correction layer
        cleaned_input = self.correct_contact_names(original_input)
        if cleaned_input != original_input:
            logger.info("Original transcript: '%s'", original_input)
            logger.info("Corrected contact name transcript: '%s'", cleaned_input)

        # Check for explicit language switches
        from utils.language_switch import detect_and_handle_language_switch
        if detect_and_handle_language_switch(cleaned_input, self):
            confirmations = {
                "en": "Sure Boss. I'll speak in English. How can I help you?",
                "te": "సరే బాస్. ఇక నుంచి తెలుగులో మాట్లాడతాను. మీకు ఏం సహాయం కావాలి?",
                "hi": "ठीक है बॉस। अब से मैं हिंदी में बात करूंगा। मैं आपकी कैसे मदद कर सकता हूँ?",
                "ta": "சரி பாஸ். இனிமேல் நான் தமிழில் பேசுவேன். நான் உங்களுக்கு எப்படி உதவலாம்?",
                "kn": "ಸರಿ ಬಾಸ್. ಇನ್ನು ಮುಂದೆ ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"
            }
            confirm_msg = confirmations.get(self.selected_language, "Sure Boss. I'll speak in English. How can I help you?")
            self.memory.add_message(role="user", content=cleaned_input)
            self.memory.add_message(role="assistant", content=confirm_msg)
            
            logger.info("[LANGUAGE]")
            logger.info("Language switch requested: true")
            
            if stream:
                def single_chunk_gen() -> Generator[str, None, None]:
                    yield confirm_msg
                return single_chunk_gen()
            return confirm_msg

        logger.info("[LANGUAGE]")
        logger.info("Language switch requested: false")

        # 1. Log the corrected user's message in memory if not already duplicate
        raw_hist = self.memory.get_history()
        if not raw_hist or raw_hist[-1].role != "user" or raw_hist[-1].content != cleaned_input:
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
            return self.conversation.ask(cleaned_input, stream=stream, selected_language=self.selected_language, intent_category=intent_category)

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

    def shutdown(self) -> None:
        """Shutdown all plugins and background processes."""
        logger.info("Shutting down NovaEngine plugins...")
        for plugin in self.plugins:
            if hasattr(plugin, "shutdown"):
                try:
                    plugin.shutdown()
                except Exception as e:
                    logger.error("Failed to shutdown plugin %s: %s", plugin.name, e)
        from core.boot_manager import BootManager
        if BootManager._instance:
            try:
                BootManager._instance.shutdown_system()
            except Exception as e:
                logger.error("Failed to invoke BootManager.shutdown_system: %s", e)
