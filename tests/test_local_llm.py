"""
tests/test_local_llm.py
-----------------------
Unit tests for OllamaProvider, LocalLLMManager, and RoutingLLMProvider.
Fully mocked to ensure headless execution without requiring actual Ollama daemon processes.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from llm.ollama_provider import OllamaProvider
from llm.local_llm_manager import LocalLLMManager
from llm.routing_provider import RoutingLLMProvider
from llm.base_provider import LLMResponse


@pytest.fixture
def mock_response():
    """Generates a mock requests response helper."""
    mock = MagicMock()
    mock.status_code = 200
    return mock


def test_ollama_provider_generate(mock_response) -> None:
    """OllamaProvider: verify generate makes a POST request to /api/chat."""
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "Hello from offline model"}
    }
    
    with patch("requests.post", return_value=mock_response) as mock_post:
        provider = OllamaProvider(model_name="llama3", host="http://localhost:11434")
        res = provider.generate([{"role": "user", "content": "Hi"}], stream=False)
        
        assert isinstance(res, LLMResponse)
        assert res.text == "Hello from offline model"
        
        # Verify JSON payload
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:11434/api/chat"
        assert kwargs["json"]["model"] == "llama3"
        assert kwargs["json"]["messages"][0]["content"] == "Hi"


def test_ollama_provider_streaming(mock_response) -> None:
    """OllamaProvider: verify generate yields chunks for streaming queries."""
    mock_response.iter_lines.return_value = [
        b'{"message": {"content": "Chunk 1"}}',
        b'{"message": {"content": " "}}',
        b'{"message": {"content": "Chunk 2"}}'
    ]
    
    with patch("requests.post", return_value=mock_response):
        provider = OllamaProvider(model_name="llama3")
        generator = provider.generate([{"role": "user", "content": "Hi"}], stream=True)
        
        chunks = list(generator)
        assert chunks == ["Chunk 1", " ", "Chunk 2"]


def test_local_llm_manager(mock_response) -> None:
    """LocalLLMManager: verify health check status and tagging discovery lists."""
    # 1. Health check
    with patch("requests.get", return_value=mock_response) as mock_get:
        manager = LocalLLMManager(host="http://localhost:11434")
        assert manager.is_healthy() is True
        mock_get.assert_called_with("http://localhost:11434", timeout=2.0)

    # 2. Tag listing
    mock_response.json.return_value = {
        "models": [
            {"name": "llama3:latest"},
            {"name": "qwen:7b"},
            {"name": "gemma:latest"}
        ]
    }
    with patch("requests.get", return_value=mock_response) as mock_get:
        manager = LocalLLMManager(host="http://localhost:11434")
        models = manager.list_local_models()
        assert models == ["llama3:latest", "qwen:7b", "gemma:latest"]
        mock_get.assert_called_with("http://localhost:11434/api/tags", timeout=2.0)


def test_routing_provider_automatic(mock_response) -> None:
    """RoutingLLMProvider: verify automatic routing selects Gemini online and Ollama offline."""
    # Mock routing env variables to be empty
    with patch("config.FORCE_LLM_PROVIDER", None), \
         patch("config.FORCE_LLM_MODEL", None):
         
        # Instantiate router
        router = RoutingLLMProvider(gemini_key="fake_key", default_local_model="llama3")
        
        # Mock providers
        router.gemini_provider = MagicMock()
        router.gemini_provider.generate.return_value = LLMResponse("Gemini output")
        
        router.ollama_provider = MagicMock()
        router.ollama_provider.model_name = "llama3"
        router.ollama_provider.generate.return_value = LLMResponse("Ollama output")
        
        # A. Case: Online -> should route to Gemini
        with patch.object(router, "_is_online", return_value=True):
            res = router.generate([{"role": "user", "content": "Hi"}])
            assert res.text == "Gemini output"
            router.gemini_provider.generate.assert_called_once()
            router.ollama_provider.generate.assert_not_called()

        # Reset mocks
        router.gemini_provider.generate.reset_mock()
        router.ollama_provider.generate.reset_mock()

        # B. Case: Offline -> should route to Ollama
        router.local_manager = MagicMock()
        router.local_manager.is_healthy.return_value = True
        router.local_manager.list_local_models.return_value = ["llama3:latest"]
        
        with patch.object(router, "_is_online", return_value=False):
            res = router.generate([{"role": "user", "content": "Hi"}])
            assert res.text == "Ollama output"
            router.gemini_provider.generate.assert_not_called()
            router.ollama_provider.generate.assert_called_once()


def test_routing_provider_forced() -> None:
    """RoutingLLMProvider: verify provider override flags bypass automatic route evaluations."""
    router = RoutingLLMProvider(gemini_key="fake_key")
    router.gemini_provider = MagicMock()
    router.gemini_provider.generate.return_value = LLMResponse("Forced Gemini")
    
    router.ollama_provider = MagicMock()
    router.ollama_provider.generate.return_value = LLMResponse("Forced Ollama")

    # A. Force Ollama route
    with patch("config.FORCE_LLM_PROVIDER", "ollama"), \
         patch("config.FORCE_LLM_MODEL", "qwen"):
         
        res = router.generate([{"role": "user", "content": "Hi"}])
        assert res.text == "Forced Ollama"
        assert router.ollama_provider.model_name == "qwen"
        router.ollama_provider.generate.assert_called_once()

    # B. Force Gemini route
    router.ollama_provider.generate.reset_mock()
    with patch("config.FORCE_LLM_PROVIDER", "gemini"), \
         patch("config.FORCE_LLM_MODEL", None):
         
        res = router.generate([{"role": "user", "content": "Hi"}])
        assert res.text == "Forced Gemini"
        router.gemini_provider.generate.assert_called_once()
        router.ollama_provider.generate.assert_not_called()
