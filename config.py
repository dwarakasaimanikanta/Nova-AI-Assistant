"""
config.py
---------
Centralized configuration for the Nova AI Assistant.
"""

import os
from pathlib import Path
import shutil
from dotenv import load_dotenv

import sys

# 1. Base paths
if getattr(sys, "frozen", False):
    # Running inside a PyInstaller bundle
    BASE_DIR: Path = Path(sys._MEIPASS).resolve()
    EXE_DIR: Path = Path(sys.executable).parent.resolve()
    DATA_DIR: Path = EXE_DIR / "data"
    LOGS_DIR: Path = EXE_DIR / "logs"
else:
    # Running in standard python development
    BASE_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"

# Ensure critical runtime folders always exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# MCP configuration file
MCP_CONFIG_FILE: Path = DATA_DIR / "mcp_config.json"
if not MCP_CONFIG_FILE.exists():
    import json
    try:
        with open(MCP_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {}}, f, indent=2)
    except Exception:
        pass

# 2. Check and copy template .env file if it doesn't exist
if getattr(sys, "frozen", False):
    dotenv_path = EXE_DIR / ".env"
    if not dotenv_path.exists():
        example_path = BASE_DIR / ".env.example"
        if example_path.exists():
            try:
                shutil.copy(example_path, dotenv_path)
            except Exception:
                pass
else:
    dotenv_path = BASE_DIR / ".env"
    if not dotenv_path.exists():
        example_path = BASE_DIR / ".env.example"
        if example_path.exists():
            shutil.copy(example_path, dotenv_path)

# 3. Explicitly load variables only from the project .env file
load_dotenv(dotenv_path=dotenv_path)

# Application metadata
APP_NAME: str = "Nova AI Assistant"
APP_VERSION: str = "1.0.0"

# Logging configuration
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Path = LOGS_DIR / "nova.log"


def _get_env_key(key_name: str) -> str | None:
    """
    Read an environment variable key and filter out placeholder values.

    Args:
        key_name: The environment variable key.

    Returns:
        The valid key value, or None if empty/placeholder.
    """
    value = os.getenv(key_name)
    if not value:
        return None

    cleaned = value.strip()
    # Filter out template placeholders from .env.example
    placeholders = (
        "your_gemini_api_key_here",
        "your_anthropic_api_key_here",
        "your_openai_api_key_here",
        "your_search_api_key_here",
    )
    if cleaned.lower() in placeholders or cleaned == "":
        return None

    return cleaned


# 4. API keys / secrets
GEMINI_API_KEY: str | None = _get_env_key("GEMINI_API_KEY")
ANTHROPIC_API_KEY: str | None = _get_env_key("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str | None = _get_env_key("OPENAI_API_KEY")
SEARCH_API_KEY: str | None = _get_env_key("SEARCH_API_KEY")

# Environment / mode
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
DEBUG: bool = ENVIRONMENT == "development"

# Voice configuration
VOICE_INPUT_ENABLED: bool = os.getenv("VOICE_INPUT_ENABLED", "false").strip().lower() == "true"
WAKE_WORD_ENABLED: bool = os.getenv("WAKE_WORD_ENABLED", "false").strip().lower() == "true"
VOICE_MODEL_SIZE: str = os.getenv("VOICE_MODEL_SIZE", "tiny").strip()
