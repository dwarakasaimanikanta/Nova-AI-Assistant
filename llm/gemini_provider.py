"""
llm/gemini_provider.py
----------------------
Google Gemini LLM provider implementation for Nova supporting function calling,
fully migrated to the official google-genai SDK.
"""

from collections.abc import Generator
from typing import Any
from google import genai
from google.genai import types

from llm.base_provider import BaseLLMProvider, LLMResponse
from utils.logger import get_logger

logger = get_logger(__name__)


class GeminiProvider(BaseLLMProvider):
    """LLM provider implementation for Google Gemini API using google-genai SDK."""

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
        self.client = genai.Client(api_key=api_key)
        logger.info("GeminiProvider configured successfully with model: %s (genai Client)", model_name)

    def _convert_messages(self, messages: list[Any]) -> list[types.Content]:
        """
        Convert generic messages to Google Gemini expected types.Content structure.

        Args:
            messages: List of generic role/content dicts or types.Content.

        Returns:
            A list of formatted types.Content objects.
        """
        formatted_contents = []
        for msg in messages:
            # If the item is already a types.Content object, pass it directly
            if isinstance(msg, types.Content):
                formatted_contents.append(msg)
                continue

            # If it is a dictionary representing Content with role and parts
            if isinstance(msg, dict) and "parts" in msg and "role" in msg:
                role = msg["role"]
                api_role = "model" if role == "assistant" else role
                parts = []
                for p in msg["parts"]:
                    if isinstance(p, types.Part):
                        parts.append(p)
                    elif isinstance(p, dict):
                        if "text" in p:
                            parts.append(types.Part.from_text(text=p["text"]))
                        elif "function_call" in p:
                            fc = p["function_call"]
                            parts.append(types.Part.from_function_call(
                                name=fc["name"],
                                args=fc["args"]
                            ))
                        elif "function_response" in p:
                            fr = p["function_response"]
                            parts.append(types.Part.from_function_response(
                                name=fr["name"],
                                response=fr["response"]
                            ))
                        else:
                            parts.append(types.Part(**p))
                    else:
                        parts.append(types.Part.from_text(text=str(p)))

                formatted_contents.append(types.Content(
                    role=api_role,
                    parts=parts
                ))
                continue

            # Standard fallback message dict mapping
            role = msg.get("role", "user")
            content = msg.get("content")
            function_calls = msg.get("function_calls")

            api_role = "model" if role == "assistant" else role
            if role == "tool":
                api_role = "user"

            parts = []
            if function_calls:
                api_role = "model"
                for fc in function_calls:
                    parts.append(types.Part.from_function_call(
                        name=fc["name"],
                        args=fc["args"]
                    ))
            elif role == "tool":
                parts.append(types.Part.from_function_response(
                    name=msg.get("name", ""),
                    response={"result": content}
                ))
            else:
                if content is not None:
                    parts.append(types.Part.from_text(text=str(content)))

            if parts:
                formatted_contents.append(types.Content(
                    role=api_role,
                    parts=parts
                ))

        return formatted_contents

    def generate(
        self,
        messages: list[Any],
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

        # Construct GenerateContentConfig config arguments
        config_args = {"temperature": 0.7}
        if tools:
            wrapped_tools = []
            if isinstance(tools, list):
                func_decls = []
                for t in tools:
                    if isinstance(t, types.Tool):
                        wrapped_tools.append(t)
                    elif isinstance(t, types.FunctionDeclaration):
                        func_decls.append(t)
                    elif hasattr(t, "name") and (hasattr(t, "parameters_json_schema") or hasattr(t, "parameters")):
                        func_decls.append(t)
                    else:
                        wrapped_tools.append(t)
                if func_decls:
                    wrapped_tools.append(types.Tool(function_declarations=func_decls))
            else:
                if isinstance(tools, types.Tool):
                    wrapped_tools.append(tools)
                elif isinstance(tools, types.FunctionDeclaration):
                    wrapped_tools.append(types.Tool(function_declarations=[tools]))
                else:
                    wrapped_tools.append(tools)

            config_args["tools"] = wrapped_tools
            # Disable automatic function calling so we can execute manually via planner
            config_args["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)

        config = types.GenerateContentConfig(**config_args)

        if stream:
            # Note: Streaming with tools is typically not supported or needed, but we provide it for text response.
            response_stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config
            )
            return (chunk.text for chunk in response_stream if chunk.text)
        else:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )

            # Check for function calls
            function_calls = []
            raw_content = None
            if response.candidates and response.candidates[0].content:
                raw_content = response.candidates[0].content
                if response.function_calls:
                    for call in response.function_calls:
                        parsed_args = {k: v for k, v in call.args.items()} if call.args else {}
                        function_calls.append({
                            "name": call.name,
                            "args": parsed_args,
                        })

            # Extract text safely
            text = response.text

            return LLMResponse(text=text, function_calls=function_calls, raw_content=raw_content)
