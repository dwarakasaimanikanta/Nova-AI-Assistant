"""
llm/conversation.py
--------------------
Manages active LLM conversation history, performance tracking, and exception handling.
"""

from collections.abc import Generator
import time

from memory.short_term import ShortTermMemory
from llm.base_provider import BaseLLMProvider
from utils.logger import get_logger

logger = get_logger(__name__)


class LLMConversation:
    """Manages active chat session, history window slicing, and performance tracking."""

    def __init__(self, provider: BaseLLMProvider, memory: ShortTermMemory) -> None:
        """
        Initialize the conversation wrapper.

        Args:
            provider: The LLM provider backend client instance.
            memory: The session short-term memory instance.
        """
        self.provider = provider
        self.memory = memory

    def ask(self, user_input: str, stream: bool = False) -> str | Generator[str, None, None]:
        """
        Query the LLM provider with the current context and return its response.

        Guarantees that no API/network errors will crash the application.

        Args:
            user_input: The raw string prompt from the user.
            stream: True to return a generator of response chunks.

        Returns:
            The response string or a generator yielding chunks.
        """
        # 1. Fetch history from short-term memory
        raw_history = self.memory.get_history()

        # 2. Double-check that user_input is representing the latest turn
        if (
            not raw_history
            or raw_history[-1].role != "user"
            or raw_history[-1].content != user_input
        ):
            self.memory.add_message(role="user", content=user_input)
            raw_history = self.memory.get_history()

        # 3. Format history and preserve thought_signatures using new SDK structures
        from google.genai import types
        history_payload = []
        i = 0
        while i < len(raw_history):
            msg = raw_history[i]
            if msg.role == "user":
                history_payload.append({
                    "role": "user",
                    "parts": [msg.content]
                })
                i += 1
            elif msg.role == "assistant":
                if msg.raw_content is not None:
                    history_payload.append(msg.raw_content)
                else:
                    if msg.function_calls:
                        parts = []
                        for fc in msg.function_calls:
                            parts.append(
                                types.Part.from_function_call(
                                    name=fc["name"],
                                    args=fc["args"]
                                )
                            )
                        history_payload.append({
                            "role": "model",
                            "parts": parts
                        })
                    else:
                        history_payload.append({
                            "role": "model",
                            "parts": [msg.content or ""]
                        })
                i += 1
            elif msg.role == "tool":
                tool_parts = []
                while i < len(raw_history) and raw_history[i].role == "tool":
                    t_msg = raw_history[i]
                    part = types.Part.from_function_response(
                        name=t_msg.name or "",
                        response={"result": t_msg.content}
                    )
                    tool_parts.append(part)
                    i += 1
                history_payload.append({
                    "role": "user",
                    "parts": tool_parts
                })

        # 4. Limit conversation history sent to Gemini to only the last 10 messages (including current user prompt)
        history_payload = history_payload[-10:]

        # 5. Invoke model generation wrapped in performance tracking and crash protection
        start_time = time.perf_counter()
        logger.info("Requesting completion from LLM provider (stream=%s). Start time: %f", stream, start_time)

        try:
            if stream:
                # Return a generator that tracks metrics when consumed
                def stream_generator() -> Generator[str, None, None]:
                    full_response = []
                    first_token_received = False
                    first_token_latency = 0.0

                    try:
                        raw_generator = self.provider.generate(history_payload, stream=True)
                        for chunk in raw_generator:
                            if not first_token_received:
                                first_token_latency = time.perf_counter() - start_time
                                logger.info("First token latency: %.4f seconds", first_token_latency)
                                first_token_received = True
                            full_response.append(chunk)
                            yield chunk
                    except Exception as e:
                        logger.exception("Error in LLM stream: %s", e)
                        yield "\n[Error: Stream interrupted.]"
                        return

                    total_time = time.perf_counter() - start_time
                    logger.info(
                        "API response complete. Total response time: %.4f seconds. First token: %.4f seconds",
                        total_time, first_token_latency
                    )
                    # Log the full response into short-term memory once generation completes
                    self.memory.add_message(role="assistant", content="".join(full_response))

                return stream_generator()
            else:
                response = self.provider.generate(history_payload, stream=False)
                total_time = time.perf_counter() - start_time
                logger.info(
                    "API response received. Total response time: %.4f seconds. End time: %f",
                    total_time, time.perf_counter()
                )
                text = response.text if hasattr(response, "text") else str(response)
                self.memory.add_message(role="assistant", content=text, raw_content=getattr(response, "raw_content", None))
                return text


        except Exception as e:
            logger.exception("LLM Provider encountered an error during generate: %s", e)
            fallback = (
                "I'm sorry, I encountered an issue contacting my AI brain. "
                "Please verify your network connection or GEMINI_API_KEY config, "
                "and try again."
            )
            if stream:
                def fallback_gen() -> Generator[str, None, None]:
                    yield fallback
                return fallback_gen()
            return fallback
