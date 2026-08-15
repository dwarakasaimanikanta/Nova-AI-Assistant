"""
core/conversation_context.py
Tracks session context for natural follow-up understanding.
"""
from __future__ import annotations
import re
import threading
from typing import Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class ConversationContext:
    MAX_HISTORY = 10

    def __init__(self):
        self._lock = threading.Lock()
        self.last_command = ""
        self.last_response = ""
        self.last_app = ""
        self.last_site = ""
        self.last_project_path = ""
        self.last_topic = ""
        self.last_folder = ""
        self.last_file = ""
        self.last_created_path = ""
        self.last_opened_path = ""
        self.last_application = ""
        self.last_browser_page = ""
        self.history = []

    def update(self, command, response):
        with self._lock:
            self.last_command = command
            self.last_response = response
            lower = command.lower()
            
            # Track last folder or file
            folder_match = re.search(r"\b(?:folder|directory)\s+(?:called|named\s+)?([a-zA-Z0-9_-]+)", command, flags=re.IGNORECASE)
            if folder_match:
                self.last_folder = folder_match.group(1)
            elif "mkdir" in lower:
                parts = command.split("mkdir")
                if len(parts) > 1:
                    self.last_folder = parts[1].strip()

            file_match = re.search(r"\b(?:file)\s+(?:called|named\s+)?([\w.]+)", command, flags=re.IGNORECASE)
            if file_match:
                self.last_file = file_match.group(1)
            elif "touch" in lower:
                parts = command.split("touch")
                if len(parts) > 1:
                    self.last_file = parts[1].strip()
            elif "create" in lower and "." in lower:
                m = re.search(r"\bcreate\s+([\w.]+)\b", command, flags=re.IGNORECASE)
                if m:
                    self.last_file = m.group(1)

            for verb in ("open", "launch", "run", "close", "kill"):
                m = re.search(r"(?<!\w)" + verb + r"\s+(\w+)", lower)
                if m:
                    candidate = m.group(1)
                    known_apps = {"notepad","chrome","calculator","paint","explorer","powershell","cmd","vscode","taskmgr","firefox"}
                    if candidate in known_apps:
                        self.last_app = candidate
                        break
            site_m = re.search(r"(?:open|go to|visit|navigate to)\s+([\w.]+)", lower)
            if site_m:
                self.last_site = site_m.group(1)
            if any(kw in lower for kw in ("project","website","app","application","site")):
                p = re.search(r"(?:for|called|named)\s+(?:a\s+)?([a-zA-Z ]+)", lower)
                if p:
                    self.last_topic = p.group(1).strip()
            self.history.append({"command": command, "response": response})
            if len(self.history) > self.MAX_HISTORY:
                self.history.pop(0)

    def set_project_path(self, path):
        with self._lock:
            self.last_project_path = path

    def resolve_follow_up(self, command):
        import os
        with self._lock:
            lower = command.lower().strip()

            # 1. Resolve "open it"
            if re.match(r"^(?:open|launch|run|start)\s+it(\s+again)?\b", lower):
                target = self.last_created_path or self.last_opened_path
                if target:
                    if os.path.isdir(target):
                        return f"open folder {target}"
                    else:
                        return f"open file {target}"
                elif self.last_folder:
                    return f"open folder {self.last_folder}"
                elif self.last_app:
                    return f"open {self.last_app}"

            # 2. Resolve "create <filename> there" / "create file <filename> there" / "inside/in it/there"
            # Matches: create README.txt there, create file README.txt inside it, create folder NovaProject in there
            there_match = re.search(r"\bcreate\s+(?:folder\s+|file\s+)?([\w.-]+)\s+(?:there|inside\s+it|in\s+it|inside\s+there|in\s+there)\b", lower)
            if there_match:
                target_dir = ""
                if self.last_opened_path and os.path.isdir(self.last_opened_path):
                    target_dir = self.last_opened_path
                elif self.last_created_path and os.path.isdir(self.last_created_path):
                    target_dir = self.last_created_path
                elif self.last_folder:
                    # Search if last_folder is a path
                    target_dir = self.last_folder
                
                if target_dir:
                    start, end = there_match.span(1)
                    filename = command[start:end]
                    full_path = os.path.join(target_dir, filename)
                    is_folder_creation = "folder" in lower
                    if is_folder_creation:
                        return f"create folder {full_path}"
                    else:
                        return f"create file {full_path}"

            # 3. Resolve "rename it to <name>"
            rename_match = re.search(r"\brename\s+it\s+to\s+([\w.-]+)\b", lower)
            if rename_match:
                start, end = rename_match.span(1)
                new_name = command[start:end]
                src_path = self.last_created_path or self.last_opened_path
                if src_path and os.path.exists(src_path):
                    parent_dir = os.path.dirname(src_path)
                    _, ext = os.path.splitext(src_path)
                    # If target is a file, preserve extension if new_name doesn't specify one
                    if os.path.isfile(src_path) and ext and not new_name.endswith(ext):
                        dest_name = new_name + ext
                    else:
                        dest_name = new_name
                    dest_path = os.path.join(parent_dir, dest_name)
                    return f"rename {src_path} to {dest_path}"

            # 4. Resolve "close it", "close that", "close the window", "close the app"
            if re.match(r"^(?:close|exit|quit|stop)\s+(?:it|that|the\s+window|the\s+app)\b", lower):
                target = self.last_app
                if not target and getattr(self, "last_application", None):
                    target = self.last_application
                if not target and (getattr(self, "last_created_path", None) or getattr(self, "last_opened_path", None)):
                    p = self.last_created_path or self.last_opened_path
                    if p and os.path.isdir(p):
                        target = "explorer"
                if target:
                    return f"close {target}"
                return "close unknown"

            # 5. Resolve "search for it" / "look up it" to last topic/site
            if re.match(r"^(?:search|look up|find)\s+(?:for\s+)?it\b", lower):
                if self.last_topic:
                    return f"search for {self.last_topic}"
                elif self.last_site:
                    return f"search for {self.last_site}"

            # 6. Resolve project modifications/coding tasks to last project path/topic
            project_prefixes = (
                "make it", "change it", "update it", "modify it", "edit it", "fix it",
                "improve it", "add to it", "rebuild it",
                "add ", "create ", "implement ", "modify ", "update ", "change ", "make ",
                "write ", "generate ", "remove ", "delete "
            )
            if any(lower.startswith(v) for v in project_prefixes):
                if self.last_project_path:
                    if self.last_project_path not in command:
                        return f"{command} (project: {self.last_project_path})"
                elif self.last_topic:
                    if self.last_topic not in command:
                        return f"{command} (regarding: {self.last_topic})"

        return command

    def get_summary(self):
        with self._lock:
            parts = []
            if self.last_command: parts.append(f"last_cmd={self.last_command!r}")
            if self.last_app: parts.append(f"last_app={self.last_app}")
            if self.last_site: parts.append(f"last_site={self.last_site}")
            if self.last_folder: parts.append(f"last_folder={self.last_folder}")
            if self.last_file: parts.append(f"last_file={self.last_file}")
            if self.last_project_path: parts.append(f"last_project={self.last_project_path}")
            return " | ".join(parts) if parts else "empty"

    def reset(self):
        with self._lock:
            self.last_command = ""
            self.last_response = ""
            self.last_app = ""
            self.last_site = ""
            self.last_project_path = ""
            self.last_topic = ""
            self.last_folder = ""
            self.last_file = ""
            self.last_created_path = ""
            self.last_opened_path = ""
            self.last_application = ""
            self.last_browser_page = ""
            self.history.clear()


_global_context = None
_context_lock = threading.Lock()

def get_conversation_context():
    global _global_context
    with _context_lock:
        if _global_context is None:
            _global_context = ConversationContext()
        return _global_context
