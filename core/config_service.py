"""
core/config_service.py
----------------------
Production-ready configuration service supporting .env loads, validation rules,
immutability after initialization, and thread-safe operations.
"""

import os
import threading
from typing import Any, Dict, List, Optional
from dotenv import dotenv_values
from utils.logger import get_logger
from core.service_manager import BaseService

logger = get_logger(__name__)


class ConfigurationError(Exception):
    """Exception raised for invalid configurations or missing required parameters."""
    pass


class ConfigService(BaseService):
    """Configuration service managing system keys, validation rules, and immutability."""

    def __init__(self, dotenv_path: Optional[str] = None) -> None:
        self._dotenv_path = dotenv_path
        self._lock = threading.Lock()
        self._config: Dict[str, Any] = {}
        self._frozen = False
        
        # Required configuration variables validation rules
        self._required_keys = ["GEMINI_API_KEY"]
        
        # Types validation maps
        self._validation_rules = {
            "AUTO_START": lambda v: str(v).lower() in ("true", "false", "1", "0"),
            "START_MINIMIZED": lambda v: str(v).lower() in ("true", "false", "1", "0"),
            "SYSTEM_TRAY": lambda v: str(v).lower() in ("true", "false", "1", "0"),
            "VOICE_INPUT_ENABLED": lambda v: str(v).lower() in ("true", "false", "1", "0"),
            "WAKE_WORD_ENABLED": lambda v: str(v).lower() in ("true", "false", "1", "0"),
            "STARTUP_GREETING_ENABLED": lambda v: str(v).lower() in ("true", "false", "1", "0"),
        }

    @property
    def name(self) -> str:
        return "Configuration"

    def initialize(self) -> bool:
        """Initialize and reload configuration parameters, freezing them immediately."""
        try:
            self.reload()
            return self.validate()
        except Exception as e:
            logger.error("[ConfigService] Initialization failed: %s", e)
            return False

    def start(self) -> bool:
        """Service start lifecycle hook."""
        return True

    def stop(self) -> bool:
        """Service stop lifecycle hook."""
        return True

    def restart(self) -> bool:
        """Service restart lifecycle hook."""
        return self.initialize()

    def health(self) -> bool:
        """Return configuration health status."""
        try:
            return self.validate()
        except Exception:
            return False

    def reload(self) -> None:
        """Load configuration parameters from config.py defaults, .env, and environment variables."""
        with self._lock:
            self._frozen = False
            self._config.clear()
            
            # 1. Load config.py legacy defaults if available
            try:
                import config as legacy_config
                for key in dir(legacy_config):
                    if key.isupper() and not key.startswith("_"):
                        self._config[key] = getattr(legacy_config, key)
            except ImportError:
                pass

            # 2. Load from .env file
            target_env = self._dotenv_path
            if not target_env:
                try:
                    import config
                    target_env = getattr(config, "dotenv_path", None)
                except ImportError:
                    pass
            
            if target_env and os.path.exists(target_env):
                env_vals = dotenv_values(target_env)
                for key, val in env_vals.items():
                    if val is not None:
                        # Clean placeholder text
                        cleaned = val.strip()
                        if cleaned.lower() not in ("your_gemini_api_key_here", ""):
                            self._config[key] = cleaned

            # 3. Load from active environment variables (highest priority)
            for key in os.environ:
                if key.isupper():
                    self._config[key] = os.environ[key]

            # 4. Expose dynamic framework hook for user custom settings
            self._load_user_settings()

            self._frozen = True
            logger.info("[ConfigService] Loaded %d configuration parameters successfully.", len(self._config))

    def _load_user_settings(self) -> None:
        """Framework stub hook for loading user-defined setting profiles (future expansion)."""
        logger.debug("[ConfigService] Loading user settings profile (stub).")

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration parameter."""
        with self._lock:
            val = self._config.get(key, default)
            
            # Type casting wrapper for common flags
            if key in self._validation_rules and isinstance(val, str):
                if val.lower() in ("true", "1"):
                    return True
                if val.lower() in ("false", "0"):
                    return False
            return val

    def set(self, key: str, value: Any) -> None:
        """Modify or set a configuration parameter. Raises ConfigurationError if frozen."""
        with self._lock:
            if self._frozen:
                raise ConfigurationError(f"Configuration is frozen and cannot be modified. Call reload() first.")
            self._config[key] = value

    def exists(self, key: str) -> bool:
        """Check if a configuration parameter exists."""
        with self._lock:
            return key in self._config

    def validate(self) -> bool:
        """Validate all rules and check for required keys. Raises ConfigurationError if invalid."""
        with self._lock:
            # 1. Verify required keys
            for req_key in self._required_keys:
                val = self._config.get(req_key)
                if not val or str(val).lower().strip() in ("your_gemini_api_key_here", ""):
                    logger.warning("[ConfigService] Required configuration parameter missing: %s", req_key)
                    return False

            # 2. Verify validation rules
            for key, rule in self._validation_rules.items():
                if key in self._config:
                    val = self._config[key]
                    if not rule(val):
                        logger.error("[ConfigService] Validation failed for %s with value %r", key, val)
                        raise ConfigurationError(f"Validation failed for parameter '{key}' with value '{val}'")
            
            return True
