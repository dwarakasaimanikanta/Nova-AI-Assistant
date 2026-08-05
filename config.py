"""
config.py
---------
Centralized configuration for the Nova AI Assistant.

Why this file exists:
    Hardcoding values like API keys, file paths, or app settings
    directly inside logic files is a bad practice. It makes the
    code hard to maintain and risks leaking secrets into source
    control. Instead, all configuration is loaded here, in one
    place, from environment variables (via a .env file).

How it works:
    - python-dotenv reads the local ".env" file (which is NOT
      committed to git) and loads its key-value pairs into the
      environment.
    - This module then reads those environment variables and
      exposes them as clean Python constants that the rest of
      the app can import.

Usage elsewhere in the project:
    from config import APP_NAME, LOG_LEVEL, DATA_DIR
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env file into the environment.
# If .env does not exist yet, this simply does nothing (no crash).
load_dotenv()

# ---------------------------------------------------------------------------
# Application metadata
# ---------------------------------------------------------------------------
APP_NAME: str = "Nova AI Assistant"
APP_VERSION: str = "1.0.0"

# ---------------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
LOGS_DIR: Path = BASE_DIR / "logs"

# Ensure critical runtime folders always exist, even on a fresh clone.
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Path = LOGS_DIR / "nova.log"

# ---------------------------------------------------------------------------
# API keys / secrets (placeholders for future phases)
# ---------------------------------------------------------------------------
# These are read now so the pattern is established early, even though
# no AI features are implemented yet in Phase 1.
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
SEARCH_API_KEY: str | None = os.getenv("SEARCH_API_KEY")

# ---------------------------------------------------------------------------
# Environment / mode
# ---------------------------------------------------------------------------
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
DEBUG: bool = ENVIRONMENT == "development"
