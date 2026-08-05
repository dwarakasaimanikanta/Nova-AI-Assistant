"""
llm/gemini_provider.py
----------------------
Google Gemini LLM provider implementation for Nova.
"""

from collections.abc import Generator
import google.generativeai as genai

from llm.base_provider import BaseLLMProvider
from utils.logger import get_logger

logger = get_logger(__name__)


class GeminiProvider(BaseLLMProvider):
    """LLM provider implementation for Google Gemini API."""

    def __init__(self, api_key: str, model_name: str = "gemini-3.6-flash") -> None:
        """
        Initialize the Gemini LLM Provider.

        Args:
            api_key: The Google API Key.
            model_name: The target model version. Defaults to 'gemini-3.6-flash'.
        """
        if not api_key:
            logger.error("Gemini API key is empty.")
            raise ValueError("Gemini API Key is required to instantiate GeminiProvider.")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info("GeminiProvider configured successfully with model: %s", model_name)

    def _convert_messages(self, messages: list[dict[str, str]]) -> list[dict]:
        """
        Convert generic messages to Google Gemini expected schema structure.

        Args:
            messages: List of generic role/content dicts.

        Returns:
            A list of formatted contents dicts matching Gemini SDK schema.
        """
        formatted_contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Map assistant role to model role for Gemini API compatibility
            api_role = "model" if role == "assistant" else "user"

            formatted_contents.append({
                "role": api_role,
                "parts": [content],
            })
        return formatted_contents

    def generate(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """
        Execute text generation against the Gemini model.

        Args:
            messages: Complete thread history.
            stream: True to return chunk generator.

        Returns:
            String response or chunk generator.
        """
        contents = self._convert_messages(messages)
        logger.debug("Sending generation request to Gemini model.")

        if stream:
            response = self.model.generate_content(contents, stream=True)
            return (chunk.text for chunk in response)
        else:
            response = self.model.generate_content(contents)
            return response.text
