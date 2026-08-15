import os
from typing import Any, Dict, List, Optional
from core.memory.persistent_memory import PersistentMemory
from core.memory.session_memory import SessionMemory
from core.memory.conversation_memory import ConversationMemory
from core.memory.entity_memory import EntityMemory

class NovaMemory:
    """Authoritative memory registry orchestrating short-term, persistent, conversation, and entity references."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NovaMemory, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self.initialized:
            return
        self.persistent = PersistentMemory()
        self.session = SessionMemory()
        self.conversation = ConversationMemory()
        self.entities = EntityMemory()
        self.initialized = True

    @property
    def selected_language(self) -> str:
        return self.persistent.get("selected_language", "en")

    @selected_language.setter
    def selected_language(self, lang: str) -> None:
        self.persistent.set("selected_language", lang)

    @property
    def current_working_directory(self) -> str:
        return self.persistent.get("current_working_directory", os.getcwd())

    @current_working_directory.setter
    def current_working_directory(self, path: str) -> None:
        self.persistent.set("current_working_directory", path)

    # Bridge to Entity Memory properties
    @property
    def last_created_path(self) -> Optional[str]:
        return self.entities.last_created_path

    @last_created_path.setter
    def last_created_path(self, val: Optional[str]) -> None:
        self.entities.last_created_path = val
        if val:
            if os.path.isdir(val):
                self.entities.last_created_folder = val
            else:
                self.entities.last_created_file = val

    @property
    def last_opened_path(self) -> Optional[str]:
        return self.entities.last_opened_path

    @last_opened_path.setter
    def last_opened_path(self, val: Optional[str]) -> None:
        self.entities.last_opened_path = val
        if val and os.path.isdir(val):
            self.entities.last_created_folder = val

    @property
    def last_opened_application(self) -> Optional[str]:
        return self.entities.last_opened_application

    @last_opened_application.setter
    def last_opened_application(self, val: Optional[str]) -> None:
        self.entities.last_opened_application = val

    @property
    def last_opened_website(self) -> Optional[str]:
        return self.entities.last_opened_website

    @last_opened_website.setter
    def last_opened_website(self, val: Optional[str]) -> None:
        self.entities.last_opened_website = val

    @property
    def last_active_browser_page(self) -> Optional[str]:
        return self.entities.last_active_browser_page

    @last_active_browser_page.setter
    def last_active_browser_page(self, val: Optional[str]) -> None:
        self.entities.last_active_browser_page = val

    @property
    def last_active_application(self) -> Optional[str]:
        return self.entities.last_active_application

    @last_active_application.setter
    def last_active_application(self, val: Optional[str]) -> None:
        self.entities.last_active_application = val

    def resolve_pronoun(self, pronoun: str, context_intent: str = "OPEN") -> Optional[str]:
        return self.entities.resolve(pronoun, context_intent=context_intent)

    def add_message(self, role: str, content: str) -> None:
        self.conversation.add_message(role, content)

    def get_history(self) -> List[Dict[str, str]]:
        return self.conversation.get_history()

    def clear_conversation(self) -> None:
        self.conversation.clear()
