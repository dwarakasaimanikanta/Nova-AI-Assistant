"""
llm/provider_factory.py
-----------------------
Factory class for generating LLM provider instances.
"""

from llm.base_provider import BaseLLMProvider
from llm.gemini_provider import GeminiProvider


class LLMProviderFactory:
    """Factory to retrieve concrete BaseLLMProvider instances."""

    @staticmethod
    def get_provider(provider_name: str, api_key: str) -> BaseLLMProvider:
        """
        Instantiate the requested LLM provider backend.

        Args:
            provider_name: The name of the provider (e.g. 'gemini').
            api_key: The credentials/API key for that provider.

        Returns:
            A subclass instance of BaseLLMProvider.
        """
        name = provider_name.strip().lower()

        if name == "gemini":
            return GeminiProvider(api_key=api_key)
        else:
            raise ValueError(
                f"Unsupported LLM provider: '{provider_name}'. "
                "Only 'gemini' is supported at this stage."
            )
