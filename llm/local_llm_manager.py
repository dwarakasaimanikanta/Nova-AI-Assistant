"""
llm/local_llm_manager.py
------------------------
LocalLLMManager manages offline local AI configurations, conducts server status health checks,
and discovers installed model tags using local Ollama endpoints.
"""

from typing import List
import requests

from config import OLLAMA_HOST
from utils.logger import get_logger

logger = get_logger(__name__)


class LocalLLMManager:
    """Manages Ollama system settings, conducts health status checks, and discovers local model tags."""

    _health_cached = None
    _health_cache_time = 0.0
    
    _models_cached = None
    _models_cache_time = 0.0

    def __init__(self, host: str | None = None) -> None:
        self.host = host or OLLAMA_HOST

    def is_healthy(self) -> bool:
        """
        Pings the base endpoint of the local Ollama server.

        Returns:
            True if the server is active, False otherwise.
        """
        import time
        now = time.time()
        if LocalLLMManager._health_cached is not None and (now - LocalLLMManager._health_cache_time) < 20.0:
            return LocalLLMManager._health_cached
            
        try:
            # Query base path, which responds with "Ollama is running"
            response = requests.get(self.host, timeout=1.0)
            status = (response.status_code == 200)
            LocalLLMManager._health_cached = status
        except Exception as e:
            logger.debug("Ollama health check ping failed: %s", e)
            LocalLLMManager._health_cached = False
            
        LocalLLMManager._health_cache_time = now
        return LocalLLMManager._health_cached

    def list_local_models(self) -> List[str]:
        """
        Fetches the list of names of all model tags currently installed on the local server.

        Returns:
            A list of model name strings (e.g. ['llama3:latest', 'mistral:latest']).
        """
        import time
        now = time.time()
        if LocalLLMManager._models_cached is not None and (now - LocalLLMManager._models_cache_time) < 20.0:
            return LocalLLMManager._models_cached

        url = f"{self.host}/api/tags"
        try:
            response = requests.get(url, timeout=1.0)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                names = [m.get("name") for m in models if m.get("name")]
                logger.info("Discovered %d local Ollama models: %s", len(names), names)
                LocalLLMManager._models_cached = names
                LocalLLMManager._models_cache_time = now
                return names
        except Exception as e:
            logger.error("Failed to fetch local model tags from Ollama: %s", e)
        
        return []
