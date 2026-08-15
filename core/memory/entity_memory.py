import os
from typing import Optional
from core.conversation_context import get_conversation_context

class EntityMemory:
    """Tracks last accessed files, folders, applications, and browser pages to resolve pronouns."""

    def __init__(self) -> None:
        pass

    @property
    def last_created_path(self) -> Optional[str]:
        return get_conversation_context().last_created_path or None

    @last_created_path.setter
    def last_created_path(self, val: Optional[str]) -> None:
        get_conversation_context().last_created_path = val or ""

    @property
    def last_opened_path(self) -> Optional[str]:
        return get_conversation_context().last_opened_path or None

    @last_opened_path.setter
    def last_opened_path(self, val: Optional[str]) -> None:
        get_conversation_context().last_opened_path = val or ""

    @property
    def last_opened_application(self) -> Optional[str]:
        return get_conversation_context().last_app or None

    @last_opened_application.setter
    def last_opened_application(self, val: Optional[str]) -> None:
        get_conversation_context().last_app = val or ""

    @property
    def last_opened_website(self) -> Optional[str]:
        return get_conversation_context().last_site or None

    @last_opened_website.setter
    def last_opened_website(self, val: Optional[str]) -> None:
        get_conversation_context().last_site = val or ""

    @property
    def last_created_folder(self) -> Optional[str]:
        return get_conversation_context().last_folder or None

    @last_created_folder.setter
    def last_created_folder(self, val: Optional[str]) -> None:
        get_conversation_context().last_folder = val or ""

    @property
    def last_created_file(self) -> Optional[str]:
        return get_conversation_context().last_file or None

    @last_created_file.setter
    def last_created_file(self, val: Optional[str]) -> None:
        get_conversation_context().last_file = val or ""

    @property
    def last_renamed_item(self) -> Optional[str]:
        return getattr(get_conversation_context(), "last_renamed_item", None) or None

    @last_renamed_item.setter
    def last_renamed_item(self, val: Optional[str]) -> None:
        setattr(get_conversation_context(), "last_renamed_item", val or "")

    @property
    def last_active_browser_page(self) -> Optional[str]:
        return get_conversation_context().last_browser_page or None

    @last_active_browser_page.setter
    def last_active_browser_page(self, val: Optional[str]) -> None:
        get_conversation_context().last_browser_page = val or ""

    @property
    def last_active_application(self) -> Optional[str]:
        return get_conversation_context().last_application or None

    @last_active_application.setter
    def last_active_application(self, val: Optional[str]) -> None:
        get_conversation_context().last_application = val or ""

    def resolve(self, pronoun: str, context_intent: str = "OPEN") -> Optional[str]:
        p = pronoun.lower().strip()
        
        # 1. Resolve "there" -> last folder target
        if p == "there":
            return self.last_created_folder or self.last_opened_path or self.last_created_path
            
        # 2. Resolve "the folder" / "that folder"
        if "folder" in p or "directory" in p:
            if self.last_created_folder:
                return self.last_created_folder
            if self.last_opened_path and os.path.isdir(self.last_opened_path):
                return self.last_opened_path
            return self.last_created_path
            
        # 3. Resolve "the app" / "the application" / "the window"
        if "app" in p or "application" in p or "window" in p:
            if context_intent == "CLOSE":
                return self.last_active_application or self.last_opened_application or "chrome"
            return self.last_opened_application or self.last_active_application
            
        # 4. Resolve general pronouns "it", "that", "this"
        if p in ("it", "that", "this"):
            if context_intent == "CLOSE":
                return self.last_active_application or self.last_active_browser_page or self.last_opened_application or self.last_opened_website
            return self.last_created_path or self.last_opened_path or self.last_opened_application or self.last_opened_website

        return None
