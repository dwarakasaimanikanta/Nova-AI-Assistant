"""
tests/test_config_service.py
----------------------------
Unit tests verifying the ConfigService parameter loads, validation rules, immutability, and thread-safety.
"""

import os
import tempfile
import threading
import time
from unittest.mock import patch
import pytest

from core.config_service import ConfigService, ConfigurationError


def test_config_service_lifecycle_and_basics():
    """Verify base service name, health status, and state getters."""
    srv = ConfigService()
    assert srv.name == "Configuration"
    assert srv.initialize() is True
    assert srv.health() is True


def test_get_and_exists_defaults():
    """Verify get and exists behaviors on configuration variables."""
    srv = ConfigService()
    srv.reload()
    
    assert srv.exists("APP_NAME") is True
    assert srv.get("APP_NAME") == "Nova AI Assistant"
    assert srv.get("NON_EXISTENT_KEY", "fallback") == "fallback"


def test_set_and_immutability():
    """Verify parameters are immutable after loading unless reload() is called."""
    srv = ConfigService()
    srv.reload()

    # Once loaded/frozen, calling set() raises ConfigurationError
    with pytest.raises(ConfigurationError):
        srv.set("APP_NAME", "Nova V2")

    # After calling reload(), it is temporarily unfrozen during load but frozen again.
    # To modify, we can test set() when the service is unfrozen (i.e. before freeze, but reload freezes it).
    # Let's verify we can construct and set before reload() freezes it.
    srv2 = ConfigService()
    srv2.set("NEW_VAR", "value1")
    assert srv2.get("NEW_VAR") == "value1"


def test_dotenv_source_loading():
    """Verify config service reads variables from custom .env files successfully."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
        f.write("TEST_ENV_KEY=EnvValue\n")
        f.write("AUTO_START=true\n")
        f.write("GEMINI_API_KEY=my_dummy_key\n")
        temp_path = f.name

    try:
        with patch.dict(os.environ, {}, clear=True):
            srv = ConfigService(dotenv_path=temp_path)
            srv.reload()

            assert srv.get("TEST_ENV_KEY") == "EnvValue"
            assert srv.get("AUTO_START") is True
            assert srv.get("GEMINI_API_KEY") == "my_dummy_key"
    finally:
        os.unlink(temp_path)


def test_env_var_override():
    """Verify environment variables take highest precedence during config loads."""
    with patch.dict(os.environ, {"APP_NAME": "OverrideName"}):
        srv = ConfigService()
        srv.reload()
        assert srv.get("APP_NAME") == "OverrideName"


def test_validation_rule_checks():
    """Verify invalid format mappings trigger validation failure exceptions."""
    srv = ConfigService()
    srv.reload()
    
    # Manually insert invalid format for bool validation check
    srv._frozen = False
    srv.set("AUTO_START", "invalid_bool_string")
    srv._frozen = True
    
    with pytest.raises(ConfigurationError):
        srv.validate()


def test_config_thread_safety():
    """Verify concurrent thread reads do not cause thread race conditions."""
    srv = ConfigService()
    srv.reload()

    threads = []
    def reader_loop():
        for _ in range(100):
            _ = srv.get("APP_NAME")
            _ = srv.exists("APP_NAME")

    for _ in range(10):
        t = threading.Thread(target=reader_loop)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
