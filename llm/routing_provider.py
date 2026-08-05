"""
llm/routing_provider.py
-----------------------
RoutingLLMProvider routes LLM requests dynamically.
If online and API key exists, routes to Gemini.
If offline, falls back to local Ollama.
Supports overrides via FORCE_LLM_PROVIDER and FORCE_LLM_MODEL.
"""

import os
import urllib.request
from collections.abc import Generator
from typing import Any
from utils.logger import get_logger

from llm.base_provider import BaseLLMProvider, LLMResponse
from llm.gemini_provider import GeminiProvider
from llm.ollama_provider import OllamaProvider
from llm.local_llm_manager import LocalLLMManager

logger = get_logger(__name__)


class RoutingLLMProvider(BaseLLMProvider):
    """Dynamic routing LLM provider proxy switching between cloud and local models."""

    def __init__(self, gemini_key: str | None = None, default_local_model: str = "llama3") -> None:
        """
        Initialize the Routing LLM Provider.

        Args:
            gemini_key: Google Gemini API key if present.
            default_local_model: Fallback local model name.
        """
        self.gemini_key = gemini_key
        self.default_local_model = default_local_model
        
        self.gemini_provider = GeminiProvider(api_key=gemini_key) if gemini_key else None
        self.ollama_provider = OllamaProvider(model_name=default_local_model)
        self.local_manager = LocalLLMManager()

    def _is_online(self) -> bool:
        """Quick HTTP check to determine network reachability."""
        try:
            # Short 1.5s timeout check against google.com to test if internet is alive
            urllib.request.urlopen("https://www.google.com", timeout=1.5)
            return True
        except Exception:
            return False

    def generate(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        tools: list[Any] | None = None,
    ) -> LLMResponse | Generator[str, None, None]:
        """
        Execute generation by routing calls to the appropriate provider backend.

        Args:
            messages: Conversation thread message history.
            stream: True to stream responses.
            tools: Bindable tool lists.

        Returns:
            LLMResponse or a chunk generator.
        """
        from config import FORCE_LLM_PROVIDER, FORCE_LLM_MODEL

        # 1. Evaluate Force Manual Overrides
        forced_provider = (FORCE_LLM_PROVIDER or "").strip().lower()
        forced_model = (FORCE_LLM_MODEL or "").strip()

        if forced_provider == "ollama":
            logger.info("Routing: Forced local Ollama route detected.")
            if forced_model:
                self.ollama_provider.model_name = forced_model
            return self.ollama_provider.generate(messages, stream, tools)
            
        elif forced_provider == "gemini":
            logger.info("Routing: Forced Gemini route detected.")
            if not self.gemini_provider:
                raise ValueError("Gemini is forced but GEMINI_API_KEY is not configured.")
            return self.gemini_provider.generate(messages, stream, tools)

        # 2. Automatic Routing Logic
        online = self._is_online()
        if self.gemini_provider and online:
            try:
                logger.info("Routing: Online Gemini provider is available. Routing query.")
                return self.gemini_provider.generate(messages, stream, tools)
            except Exception as e:
                logger.warning("Routing: Gemini generation request failed: %s. Falling back to local Ollama.", e)

        # 3. Fallback Route to local Ollama if healthy
        if self.local_manager.is_healthy():
            logger.info("Routing: Running in offline fallback mode. Routing query to local Ollama.")
            
            # Auto-align target local model name to installed tags if specified model is missing
            local_models = self.local_manager.list_local_models()
            if local_models:
                target = forced_model or self.ollama_provider.model_name
                # Check for substring match (e.g. 'llama3' matches 'llama3:latest')
                matched = False
                for model in local_models:
                    if target.lower() in model.lower():
                        self.ollama_provider.model_name = model
                        matched = True
                        break
                if not matched:
                    # Fall back to first available model tags
                    logger.warning("Routing: Target model '%s' not found locally. Autoreconfig to '%s'.", target, local_models[0])
                    self.ollama_provider.model_name = local_models[0]
                    
            return self.ollama_provider.generate(messages, stream, tools)

        # No pathways available
        raise RuntimeError("LLM routing failure: internet is offline and local Ollama is unreachable.")
