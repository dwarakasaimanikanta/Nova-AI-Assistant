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

    def __init__(self, host: str | None = None) -> None:
        self.host = host or OLLAMA_HOST

    def is_healthy(self) -> bool:
        """
        Pings the base endpoint of the local Ollama server.

        Returns:
            True if the server is active, False otherwise.
        """
        try:
            # Query base path, which responds with "Ollama is running"
            response = requests.get(self.host, timeout=2.0)
            return response.status_code == 200
        except Exception as e:
            logger.debug("Ollama health check ping failed: %s", e)
            return False

    def list_local_models(self) -> List[str]:
        """
        Fetches the list of names of all model tags currently installed on the local server.

        Returns:
            A list of model name strings (e.g. ['llama3:latest', 'mistral:latest']).
        """
        url = f"{self.host}/api/tags"
        try:
            response = requests.get(url, timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                names = [m.get("name") for m in models if m.get("name")]
                logger.info("Discovered %d local Ollama models: %s", len(names), names)
                return names
        except Exception as e:
            logger.error("Failed to fetch local model tags from Ollama: %s", e)
        
        return []
