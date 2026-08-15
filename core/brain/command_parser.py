import re
from typing import Any, Dict, Optional
from core.brain.intent import IntentType
from core.brain.action_plan import ActionPlan

class CommandParser:
    """Parses user input into a structured ActionPlan using deterministic patterns first."""

    def __init__(self) -> None:
        # Standard site mappings
        self.site_keywords = {
            "youtube": "https://www.youtube.com/",
            "google": "https://www.google.com/",
            "gmail": "https://mail.google.com/",
            "google mail": "https://mail.google.com/",
            "github": "https://github.com/",
            "chatgpt": "https://chatgpt.com/",
            "twitter": "https://twitter.com/",
            "x": "https://twitter.com/",
            "reddit": "https://www.reddit.com/",
            "spotify": "https://open.spotify.com/",
            "linkedin": "https://www.linkedin.com/",
            "stackoverflow": "https://stackoverflow.com/",
            "stack overflow": "https://stackoverflow.com/",
            "whatsapp": "https://web.whatsapp.com/",
            "netflix": "https://www.netflix.com/",
            "amazon": "https://www.amazon.in/",
            "instagram": "https://www.instagram.com/",
            "facebook": "https://www.facebook.com/",
        }

        self.app_keywords = {
            "notepad", "calculator", "calc", "paint", "mspaint", "cmd", 
            "command prompt", "powershell", "terminal", "vscode", 
            "visual studio code", "chrome", "explorer", "file explorer", 
            "task manager", "taskmgr"
        }

        # Priority personality triggers
        self.personality_replies = {
            "what are you doing": "Standing by, Boss. Ready for your command.",
            "what are you": "I am Nova, your personal AI assistant, Boss.",
            "who are you": "I'm Nova, your personal AI assistant, Boss. Think of me as your Jarvis.",
            "who made you": "I was built by my creator — your very own Nova AI system.",
            "how are you": "Running at full capacity, Boss. All systems are operational.",
            "good morning": "Good morning, Boss! All systems are ready. How can I assist you today?",
            "good afternoon": "Good afternoon, Boss. How can I help?",
            "good evening": "Good evening, Boss. What can I do for you?",
            "good night": "Good night, Boss. Powering down voice monitoring. Sleep well.",
            "hey nova": "Yes Boss.",
            "hello nova": "Yes Boss.",
            "hi nova": "Hi Boss! Ready when you are.",
            "thanks": "Anytime, Boss.",
            "thank you": "You're welcome, Boss.",
            "nice work": "Thank you, Boss. That means a lot.",
            "well done": "Glad I could help, Boss.",
            "can you hear me": "Loud and clear, Boss.",
            "are you there": "Always here, Boss.",
            "are you listening": "Every word, Boss.",
            "cancel": "Cancelled, Boss.",
        }

    def parse(self, text: str) -> ActionPlan:
        raw_text = text
        lower = text.lower().strip()
        
        # Strip conversational prefixes
        lower = re.sub(r"^i\s+said\s+", "", lower)
        
        # Normalize notepad variations
        lower = re.sub(r"\b(note\s+pad|north\s+pad|northpad|note-pad|not\s+bad)\b", "notepad", lower)
        
        # Normalize command prefixes
        lower = re.sub(r"\bopen\s+up\b", "open", lower)
        lower = re.sub(r"\bclose\s+the\b", "close", lower)
        lower = re.sub(r"\blaunch\s+the\b", "launch", lower)
        
        from utils.logger import get_logger
        _stt_logger = get_logger("STT")
        _stt_logger.info("[STT] Raw: %s", raw_text)
        _stt_logger.info("[STT] Normalized: %s", lower)
        
        # 1. Stop / Interruption Precheck
        stop_keywords = {
            "stop", "stop speaking", "enough", "quiet", "shut up", "nova stop",
            "ఆపు", "ఆపండి", "చాలు", "apu", "apandi", "chalu",
            "ruko", "band karo", "niruthu", "pothum", "nillisu", "saaku"
        }
        if any(w == lower or lower.startswith(w + " ") for w in stop_keywords):
            return ActionPlan(IntentType.STOP, "SYSTEM", "stop", confidence=1.0)

        # Match shutdown
        shutdown_keywords = {"shutdown", "shutdown nova", "exit", "exit nova", "quit", "quit nova", "power off"}
        if lower in shutdown_keywords or any(lower.startswith(w + " ") for w in shutdown_keywords):
            return ActionPlan(IntentType.STOP, "SYSTEM", "shutdown", confidence=1.0)

        # Match restart
        restart_keywords = {"restart", "restart nova", "reboot", "reboot nova"}
        if lower in restart_keywords or any(lower.startswith(w + " ") for w in restart_keywords):
            return ActionPlan(IntentType.STOP, "SYSTEM", "restart", confidence=1.0)

        # 1b. Filesystem memory queries pre-check (bypasses LLM)
        fs_query_keywords = {
            "where did you create it",
            "where is the folder",
            "tell me where you created it",
            "where is it created",
            "tell me where it is"
        }
        if any(w in lower for w in fs_query_keywords):
            return ActionPlan(IntentType.APP_CONTROL, "FS_QUERY", "where", confidence=1.0)

        # 1c. Open last created folder pre-check (bypasses LLM)
        if "open the folder you just created" in lower or "open the created folder" in lower or "open that folder" in lower:
            return ActionPlan(IntentType.OPEN, "FOLDER", "last_created", confidence=1.0)

        # 2. Language Switch Checks
        # Support mixing language patterns: e.g. "Telugu lo matladu", "Hindi me bolo", etc.
        lang_matches = {
            "te": [r"telugu", r"తెలుగు", r"telgu", r"telegu"],
            "hi": [r"hindi", r"हिंदी", r"हिन्दी", r"hindee"],
            "ta": [r"tamil", r"தமிழ்", r"tameel", r"thamil"],
            "kn": [r"kannada", r"ಕನ್ನಡ", r"kanada", r"kannad"],
            "en": [r"english", r"ఇంగ్లీష్", r"இங்கிலீஷ்", r"ಇಂಗ್ಲಿಷ್", r"inglish"]
        }
        
        switch_verbs = [
            r"switch\s+to", r"speak\s+in", r"talk\s+in", r"change\s+to", r"use", r"select", r"set",
            r"lo\s+(matladu|maatlaadu|matladandi|maatlaadandi)", r"me\s+(bolo|baat\s+karo)", 
            r"la\s+pesu", r"dalli\s+maatadu", r"in\s+", r"mode"
        ]

        for lang, patterns in lang_matches.items():
            for pat in patterns:
                for verb in switch_verbs:
                    if "lo" in verb or "me" in verb or "la" in verb or "dalli" in verb:
                        full_pat = pat + r"\s+" + verb
                    else:
                        full_pat = verb + r"\s+" + pat
                    if re.search(full_pat, lower):
                        return ActionPlan(
                            IntentType.LANGUAGE_SWITCH, "LANGUAGE", lang, 
                            parameters={"language": lang}, confidence=1.0
                        )

        # 3. Personality replies fast-path
        for trigger in self.personality_replies:
            if lower == trigger or lower.startswith(trigger + " "):
                return ActionPlan(
                    IntentType.CONVERSATION, "PERSONALITY", trigger, 
                    parameters={"reply": self.personality_replies[trigger]}, confidence=1.0
                )

        # 4. Project/Website Creation Precheck
        # "Create a website", "build a website", etc.
        project_keywords = (
            "create website", "create a website", "build website", "build a website",
            "build web application", "build a web application", "create portfolio website",
            "create a portfolio website", "generate website", "generate a website"
        )
        if any(kw in lower for kw in project_keywords):
            return ActionPlan(IntentType.CREATE_PROJECT, "PROJECT", "website", confidence=1.0)

        # 5. Open / Launch / Go to Commands
        # Match "open chrome", "go to youtube", etc.
        open_match = re.match(r"^(?:open|launch|run|start|go\s+to)\s+(.+)$", lower)
        if open_match:
            target = open_match.group(1).strip()
            # Remove filler articles like "the", "a", "an", "app", "website"
            target_cleaned = re.sub(r"\b(this|the|app|application|website|page|site)\b", "", target).strip()
            
            # If target starts with http, it is a direct URL. Do not map friendly name.
            if target_cleaned.startswith("http"):
                return ActionPlan(IntentType.OPEN, "WEBSITE", target_cleaned, confidence=1.0)
            
            # Check site mapping first
            for site_kw, url in self.site_keywords.items():
                if re.search(r"\b" + re.escape(site_kw) + r"\b", target_cleaned):
                    return ActionPlan(IntentType.OPEN, "WEBSITE", url, confidence=1.0)
            
            # Check app mapping
            for app_kw in self.app_keywords:
                if re.search(r"\b" + re.escape(app_kw) + r"\b", target_cleaned):
                    return ActionPlan(IntentType.OPEN, "APPLICATION", app_kw, confidence=1.0)
            
            # If target has a dot (e.g. google.com), assume website
            if "." in target_cleaned and " " not in target_cleaned:
                url = target_cleaned if target_cleaned.startswith("http") else f"https://{target_cleaned}"
                return ActionPlan(IntentType.OPEN, "WEBSITE", url, confidence=1.0)
                
            # If target resolves to folder, it is navigation
            if target_cleaned in ("it", "that", "there", "this", "the folder", "folder"):
                return ActionPlan(IntentType.OPEN, "FOLDER", target_cleaned, confidence=1.0)
            
            # Unrecognized launch target (return low confidence to clarification)
            return ActionPlan(IntentType.OPEN, "UNKNOWN", target_cleaned, confidence=0.4)

        # 6. Close / Exit / Stop application Commands
        # Match "close chrome", "exit calculator", etc.
        close_match = re.match(r"^(?:close|exit|quit|stop|kill|terminate)\s+(.+)$", lower)
        if close_match:
            target = close_match.group(1).strip()
            target_cleaned = re.sub(r"\b(this|the|app|application|website|page|site|window)\b", "", target).strip()
            
            # Match mapped targets
            for site_kw in self.site_keywords:
                if re.search(r"\b" + re.escape(site_kw) + r"\b", target_cleaned):
                    return ActionPlan(IntentType.CLOSE, "WEBSITE", site_kw, confidence=1.0)
            for app_kw in self.app_keywords:
                if re.search(r"\b" + re.escape(app_kw) + r"\b", target_cleaned):
                    return ActionPlan(IntentType.CLOSE, "APPLICATION", app_kw, confidence=1.0)
            
            # Pronoun/context resolution triggers
            if target_cleaned in ("it", "that", "the window", "the app"):
                return ActionPlan(IntentType.CLOSE, "LAST_ACTIVE_RESOURCE", target_cleaned, confidence=1.0)
                
            return ActionPlan(IntentType.CLOSE, "UNKNOWN", target_cleaned, confidence=0.4)

        # 7. Filesystem Commands: Create file/folder, rename, delete, move, copy
        # Match "create a folder called X", "make a directory called Y"
        folder_match = re.search(r"\b(?:create|make|mkdir|build)\s+(?:a\s+)?(?:folder|directory)(?:\s+(?:called|named))?\s+([\w\.\-]+)(?:\s+(?:inside|in|on|at|into)\s+(.+))?", lower)
        if folder_match:
            name = folder_match.group(1).strip()
            parent = folder_match.group(2).strip() if folder_match.group(2) else "desktop"
            return ActionPlan(IntentType.CREATE, "FOLDER", parent, parameters={"name": name}, confidence=1.0)

        # Match "create test.txt there", "create file test.txt inside Projects"
        file_match = re.search(r"\b(?:create|make|write|write\s+to|append)\s+(?:a\s+)?(?:file\s+)?(?:called\s+|named\s+)?([\w\-\.]+)(?:\s+(?:there|in|inside|into)\s+(.+))?", lower)
        if file_match:
            filename = file_match.group(1).strip()
            coding_indicators = {"script", "code", "program", "function", "class", "algorithm", "sorting", "api", "website", "web page"}
            if any(indicator in lower for indicator in coding_indicators):
                pass
            else:
                dest = file_match.group(2).strip() if file_match.group(2) else "there"
                return ActionPlan(IntentType.CREATE, "FILE", dest, parameters={"name": filename}, confidence=1.0)

        # Match "rename X to Y"
        rename_match = re.search(r"\b(?:rename|change\s+name\s+of)\s+(.+)\s+to\s+(.+)$", lower)
        if rename_match:
            src = rename_match.group(1).strip()
            dest = rename_match.group(2).strip()
            return ActionPlan(IntentType.RENAME, "RESOURCE", src, parameters={"dest": dest}, confidence=1.0)

        # Match "delete that file", "delete folder X"
        delete_match = re.match(r"^(?:delete|remove|rm|erase)\s+(.+)$", lower)
        if delete_match:
            target = delete_match.group(1).strip()
            return ActionPlan(IntentType.DELETE, "RESOURCE", target, confidence=1.0)

        # 8. General Q&A / Knowledge queries
        # MUST remain a KNOWLEDGE request. Must NOT open browser or google.
        question_words = {
            "what", "how", "why", "who", "where", "when", "explain", "tell", 
            "describe", "list", "show", "help", "story", "code"
        }
        if any(w == lower or lower.startswith(w + " ") for w in question_words) or lower.endswith("?"):
            return ActionPlan(IntentType.KNOWLEDGE, "KNOWLEDGE", lower, confidence=1.0)

        # 9. Fallback general conversation
        return ActionPlan(IntentType.CONVERSATION, "GENERAL", lower, confidence=0.5)
