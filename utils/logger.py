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
_LOGGER_CONFIGURED = False


def _configure_root_logger() -> None:
    """Attach console + file handlers to the shared 'nova' logger once."""
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    root_logger = logging.getLogger("nova")
    root_logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler: shows logs in the terminal while Nova runs.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Rotating file handler: keeps log files from growing forever.
    # Once a log file hits 5 MB, it rolls over and keeps 3 backups.
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
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
