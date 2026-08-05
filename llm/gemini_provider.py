"""
llm/gemini_provider.py
----------------------
Google Gemini LLM provider implementation for Nova supporting function calling.
"""

from collections.abc import Generator
from typing import Any
import google.generativeai as genai
import google.generativeai.types.content_types as ct

from llm.base_provider import BaseLLMProvider, LLMResponse
from utils.logger import get_logger

logger = get_logger(__name__)


class GeminiProvider(BaseLLMProvider):
    """LLM provider implementation for Google Gemini API."""

    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash-lite") -> None:
        """
        Initialize the Gemini LLM Provider.

        Args:
            api_key: The Google API Key.
            model_name: The target model version. Defaults to 'gemini-3.5-flash-lite'.
        """
        if not api_key:
            logger.error("Gemini API key is empty.")
            raise ValueError("Gemini API Key is required to instantiate GeminiProvider.")

        self.model_name = model_name
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info("GeminiProvider configured successfully with model: %s", model_name)

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[Any]:
        """
        Convert generic messages to Google Gemini expected schema structure.

        Args:
            messages: List of generic role/content dicts.

        Returns:
            A list of formatted contents dicts matching Gemini SDK schema.
        """
        formatted_contents = []
        for msg in messages:
            # If the item is already a Content object or structured dict (has 'parts' and 'role'), pass it directly
            if hasattr(msg, "parts") and hasattr(msg, "role"):
                formatted_contents.append(msg)
                continue
            if isinstance(msg, dict) and "parts" in msg and "role" in msg:
                formatted_contents.append(msg)
                continue

            role = msg.get("role", "user")
            content = msg.get("content")
            function_calls = msg.get("function_calls")

            # Map assistant role to model role for Gemini API compatibility
            api_role = "model" if role == "assistant" else role

            parts = []
            if function_calls:
                api_role = "model"
                for fc in function_calls:
                    parts.append(
                        ct.to_part({
                            "function_call": {
                                "name": fc["name"],
                                "args": fc["args"],
                            }
                        })
                    )
            elif role == "tool":
                # Function response results must be mapped as role "user"
                api_role = "user"
                parts.append(
                    ct.to_part({
                        "function_response": {
                            "name": msg.get("name", ""),
                            "response": {"result": content},
                        }
                    })
                )
            else:
                if content is not None:
                    parts.append(content)

            if parts:
                formatted_contents.append({
                    "role": api_role,
                    "parts": parts,
                })
        return formatted_contents

    def generate(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        tools: list[Any] | None = None,
    ) -> LLMResponse | Generator[str, None, None]:
        """
        Execute text generation or tool call generation against the Gemini model.

        Args:
            messages: Complete thread history.
            stream: True to return chunk generator.
            tools: List of function declarations the model can call.

        Returns:
            LLMResponse or chunk generator.
        """
        contents = self._convert_messages(messages)
        logger.debug("Sending generation request to Gemini model.")

        # Bind tools to a temporary model instance if provided to prevent caching issues
        if tools:
            model = genai.GenerativeModel(self.model_name, tools=tools)
        else:
            model = self.model

        if stream:
            response = model.generate_content(contents, stream=True)
            return (chunk.text for chunk in response)
        else:
            response = model.generate_content(contents)

            # Check for function calls
            function_calls = []
            raw_content = None
            if response.candidates and response.candidates[0].content.parts:
                raw_content = response.candidates[0].content
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        function_calls.append({
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args),
                        })

            # Safely extract text (raises ValueError if there are only function calls)
            text = None
            if not function_calls:
                try:
                    text = response.text
                except ValueError:
                    pass

            return LLMResponse(text=text, function_calls=function_calls, raw_content=raw_content)
