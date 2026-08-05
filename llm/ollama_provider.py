"""
llm/ollama_provider.py
----------------------
Ollama LLM provider implementation for Nova supporting local, offline LLMs.
Uses the standard HTTP REST API of local Ollama instances.
"""

import json
from collections.abc import Generator
from typing import Any
import requests

from llm.base_provider import BaseLLMProvider, LLMResponse
from config import OLLAMA_HOST
from utils.logger import get_logger

logger = get_logger(__name__)


class OllamaProvider(BaseLLMProvider):
    """LLM provider implementation for local offline Ollama models."""

    def __init__(self, model_name: str = "llama3", host: str | None = None) -> None:
        """
        Initialize the Ollama Provider.

        Args:
            model_name: The target local model (e.g. 'llama3', 'qwen', 'mistral', 'gemma').
            host: Ollama daemon URL. Defaults to OLLAMA_HOST (http://localhost:11434).
        """
        self.model_name = model_name
        self.host = host or OLLAMA_HOST
        logger.info("OllamaProvider initialized targeting model: %s at %s", model_name, self.host)

    def generate(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        tools: list[Any] | None = None,
    ) -> LLMResponse | Generator[str, None, None]:
        """
        Generate text response from the local model.

        Args:
            messages: Thread message history.
            stream: True to return chunk generator.
            tools: Tools to bind (not natively supported by standard Ollama HTTP API without extra setups).

        Returns:
            LLMResponse or a chunk generator.
        """
        url = f"{self.host}/api/chat"

        # Format messages for Ollama API
        formatted_messages = []
        for msg in messages:
            # Map roles safely
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Map assistant role to model role if necessary, though Ollama accepts assistant
            formatted_messages.append({
                "role": role,
                "content": str(content)
            })

        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "stream": stream,
            "options": {
                "temperature": 0.7
            }
        }

        try:
            if stream:
                response = requests.post(url, json=payload, stream=True, timeout=60.0)
                response.raise_for_status()
                return self._stream_generator(response)
            else:
                response = requests.post(url, json=payload, timeout=60.0)
                response.raise_for_status()
                res_data = response.json()
                text = res_data.get("message", {}).get("content", "")
                return LLMResponse(text=text)
        except Exception as e:
            logger.error("Failed to generate response from Ollama: %s", e)
            raise RuntimeError(f"Ollama generation failed: {e}")

    def _stream_generator(self, response: requests.Response) -> Generator[str, None, None]:
        """Parses the NDJSON streaming response from Ollama and yields string chunks."""
        try:
            for line in response.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    data = json.loads(decoded)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
        except Exception as e:
            logger.error("Error in Ollama stream generator: %s", e)
        finally:
            response.close()
