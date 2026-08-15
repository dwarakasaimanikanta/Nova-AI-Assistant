"""
utils/logger.py
----------------
Centralized logging setup for the Nova AI Assistant.

Why this file exists:
    Using print() for debugging works for tiny scripts, but Nova
    will eventually run voice recognition, system automation, and
    AI calls -- all of which can fail in ways we need to trace.
    A proper logger:
        - Timestamps every message
        - Labels the severity (DEBUG, INFO, WARNING, ERROR)
        - Writes to both the console AND a log file on disk
        - Can be tuned via config.py (LOG_LEVEL) without code changes

Usage elsewhere in the project:
    from utils.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Nova started successfully")
    logger.error("Failed to reach the LLM API")
"""

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_FILE, LOG_LEVEL

# Track whether handlers have already been attached to the root
# "nova" logger, so repeated calls to get_logger() don't create
# duplicate log lines.
import threading

_LOGGER_LOCK = threading.Lock()
_LOGGER_CONFIGURED = False


class SafeRotatingFileHandler(RotatingFileHandler):
    """A RotatingFileHandler that catches PermissionError/WinError 32 on Windows

    when the log file is locked by another process or thread during rollover.
    """
    _last_warning_time = 0.0

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except (PermissionError, OSError) as e:
            # Under Windows, renaming/deleting files can fail if they are locked
            # by other processes or threads. We catch the exception to prevent
            # crashing the application, and ensure logging can continue to the base file.
            import sys
            import time
            now = time.time()
            # Only print warning once every 60 seconds to prevent terminal flooding
            if now - SafeRotatingFileHandler._last_warning_time > 60.0:
                print(f"Logging rollover warning: log file is locked and cannot be rolled over: {e}", file=sys.stdout)
                SafeRotatingFileHandler._last_warning_time = now
            # Reopen the stream if it was closed by super().doRollover()
            if self.stream is None:
                self.stream = self._open()


class ConsoleLogFilter(logging.Filter):
    """Show only clean user-facing log lines on the terminal.

    Internal diagnostic lines ([STT], [TIMING-METRICS], [SpeechController], etc.)
    are still written to the log file but must NOT appear on the terminal.
    """
    # Prefixes that ARE allowed on the terminal
    _TERMINAL_ALLOWED = (
        "[SYSTEM]", "[VOICE]", "[NOVA]", "[TOOL]", "[ERROR]",
        "[PLANNER]", "[EXECUTION]",
        "[LANGUAGE]", "[LANGUAGE-STATE]", "[VOICE-LANGUAGE]",
        "[STATE]", "[Watchdog]", "[NORMALIZER]",
        "[WAKE]", "[BARGE-IN]", "[LANGUAGE_SELECTION]",
        # FIX-8: New operational tags from Phase 3 fixes
        "[STOP-INTERCEPT]",    # Fix 3: silent STOP handling
        "[REQUEST-GUARD]",     # Fix 7: stale response discarded
        "[PermissionGate]",    # Fix 4: tool permission decisions
        "[BROWSER]",           # Fix 5: browser close
        "[ExecutiveAgent] Classif",   # Intent classification result
        "[ExecutiveAgent] Routing",   # Fast-path routing decisions
        "[IntentRouter]",      # LLM intent classification
    )
    # Prefixes that must ONLY go to the log file, never to the terminal
    _TERMINAL_BLOCKED = (
        "[STT]", "[TTS]", "[TIMING-METRICS]", "[VOICE-LATENCY]", "[VOICE-DEBUG]",
        "[SpeechController]", "[AlwaysListeningEngine]", "[RESPONSE]",
        "[TTS-MOCK]", "[Watchdog] Speaking response",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True  # Always show warnings/errors
        msg = record.getMessage()
        # Block explicitly noisy internal lines
        if any(msg.startswith(p) for p in self._TERMINAL_BLOCKED):
            return False
        # Allow only known terminal-safe prefixes
        return any(msg.startswith(p) for p in self._TERMINAL_ALLOWED)



class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        
        # Clean up tags and add requested prefix
        if any(msg.startswith(p) for p in ("[SYSTEM]", "[Watchdog]", "[NORMALIZER]", "[STATE]")):
            cleaned = msg
            for tag in ("[SYSTEM]", "[Watchdog]", "[NORMALIZER]", "[STATE]"):
                cleaned = cleaned.replace(tag, "")
            return f"[SYSTEM] {cleaned.strip()}"

        if any(msg.startswith(p) for p in (
            "[VOICE]", "[LANGUAGE]", "[LANGUAGE-STATE]", "[VOICE-LANGUAGE]",
            "[WAKE]", "[BARGE-IN]", "[LANGUAGE_SELECTION]",
        )):
            cleaned = msg
            for tag in ("[VOICE]", "[LANGUAGE-STATE]", "[VOICE-LANGUAGE]", "[LANGUAGE]",
                        "[WAKE]", "[BARGE-IN]", "[LANGUAGE_SELECTION]"):
                cleaned = cleaned.replace(tag, "")
            return f"[VOICE] {cleaned.strip()}"

        if msg.startswith("[NOVA]"):
            cleaned = msg.replace("[NOVA]", "").strip()
            return f"[NOVA]\n{cleaned}"

        if any(msg.startswith(p) for p in ("[TOOL]", "[PLANNER]", "[EXECUTION]", "[BROWSER]")):
            cleaned = msg
            for tag in ("[TOOL]", "[PLANNER]", "[EXECUTION]", "[BROWSER]"):
                cleaned = cleaned.replace(tag, "")
            return f"[TOOL] {cleaned.strip()}"

        # FIX-8: New operational tags
        if msg.startswith("[STOP-INTERCEPT]"):
            return f"[SYSTEM] STOP intercepted — silencing."
        if msg.startswith("[REQUEST-GUARD]"):
            return f"[SYSTEM] {msg.replace('[REQUEST-GUARD]', '').strip()}"
        if msg.startswith("[PermissionGate]"):
            return f"[SYSTEM] PermissionGate: {msg.replace('[PermissionGate]', '').strip()}"
        if msg.startswith(("[ExecutiveAgent] Classif", "[ExecutiveAgent] Routing", "[IntentRouter]")):
            return f"[SYSTEM] {msg}"

        if record.levelno >= logging.ERROR or msg.startswith("[ERROR]"):
            cleaned = msg.replace("[ERROR]", "").strip()
            return f"[ERROR] {cleaned}"

        if record.levelno >= logging.WARNING:
            return f"[SYSTEM] [WARNING] {msg}"

        return f"[SYSTEM] {msg}"

def _configure_root_logger() -> None:
    """Attach console + file handlers to the shared 'nova' logger once."""
    global _LOGGER_CONFIGURED

    with _LOGGER_LOCK:
        root_logger = logging.getLogger("nova")
        
        if root_logger.handlers or _LOGGER_CONFIGURED:
            _LOGGER_CONFIGURED = True
            return

        root_logger.setLevel(LOG_LEVEL)

        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler: shows custom clean format logs in the terminal while Nova runs.
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ConsoleFormatter())
        console_handler.addFilter(ConsoleLogFilter())
        root_logger.addHandler(console_handler)

        # Rotating file handler: keeps log files from growing forever.
        file_handler = SafeRotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        _LOGGER_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger scoped to the given module name, nested under
    the shared 'nova' logger namespace (e.g. 'nova.core.engine').

    Args:
        name: Typically passed as __name__ from the calling module.

    Returns:
        A configured logging.Logger instance.
    """
    _configure_root_logger()
    return logging.getLogger(f"nova.{name}")
