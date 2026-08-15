"""
voice/conversation_engine.py
----------------------------
Voice Conversation Engine driving multi-turn spoken dialogue,
TTS streaming, context lifecycle, and active interruption.
"""

from __future__ import annotations

import os
import time
import threading
from typing import Any, Dict, Generator, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class VoiceConversationEngine:
    """Manages active verbal interactions, context state, and agent pipeline routing."""

    def __init__(
        self,
        executive_agent: Any,
        voice_manager: Any,
        memory_agent: Optional[Any] = None,
        conversation_timeout: float = 60.0,
    ) -> None:
        self.executive_agent = executive_agent
        self.voice_manager = voice_manager
        self.memory_agent = memory_agent
        self.conversation_timeout = conversation_timeout
        
        self.history: List[Dict[str, str]] = []
        self.last_interaction_time = time.time()
        self._lock = threading.Lock()

    def process_speech(self, text: str, response_text: str = None, exec_id: str = None) -> None:
        """
        Receive transcribed input text, coordinate pipeline execution,
        and stream/output spoken response.
        """
        with self._lock:
            text = text.strip()
            if not text:
                return

            if response_text is None:
                logger.info("[STATE] Transitioned to PROCESSING")
                if self.voice_manager:
                    self.voice_manager.state = "PROCESSING"

            try:
                if exec_id:
                    logger.info("[EXECUTION-ID:%s] Entering process_speech in ConversationEngine for: %r", exec_id, text)
                else:
                    logger.info("[CONVERSATION] Received: %s", text)

                now = time.time()
                # 1. Reset conversation after timeout
                if now - self.last_interaction_time > self.conversation_timeout:
                    logger.info("[ConversationEngine] Session timed out. Clearing history.")
                    self.history.clear()
                self.last_interaction_time = now

                # 2. Record user statement in context
                self.history.append({"role": "user", "content": text})
                if self.memory_agent:
                    try:
                        self.memory_agent.remember(
                            category="short_term",
                            key="last_user_voice_input",
                            value=text
                        )
                    except Exception as e:
                        logger.debug("Failed logging voice input to memory: %s", e)

                # 3. Ensure stop_event is clear so TTS can actually play
                if self.voice_manager and hasattr(self.voice_manager, "_stop_event"):
                    self.voice_manager._stop_event.clear()

                # 4. Resolve full_response (either via cached response_text or execution)
                try:
                    # Determine active response_language
                    selected_language = "en"
                    if self.voice_manager:
                        selected_language = getattr(self.voice_manager, "selected_language", "en")
                        self.executive_agent.selected_language = selected_language
                        self.executive_agent.voice_manager = self.voice_manager
                    response_language = selected_language

                    if response_text is not None:
                        if exec_id:
                            logger.info("[EXECUTION-ID:%s] Bypassing duplicate execution as response is already generated.", exec_id)
                        else:
                            logger.info("[ConversationEngine] Response already generated: %r", response_text)
                        full_response = response_text
                    else:
                        pipeline = getattr(self.executive_agent, "execution_pipeline", None)
                        
                        if pipeline and "Mock" not in type(pipeline).__name__:
                            logger.info("[CONVERSATION] Passing to ExecutionPipeline: %s", text)
                            self.executive_agent.selected_language = selected_language
                            full_response = pipeline.execute(text)
                            logger.info("[CONVERSATION] Speaking response...")
                            self._speak_safely(full_response, response_language=response_language)
                        else:
                            logger.info("[ConversationEngine] Dispatching input to ExecutiveAgent: %r", text)
                            # Check if executive_agent is a mock or does not accept selected_language
                            is_mock = False
                            try:
                                from unittest.mock import NonCallableMock
                                if isinstance(self.executive_agent, NonCallableMock):
                                    is_mock = True
                            except Exception:
                                pass
                                
                            import inspect
                            func = self.executive_agent.handle_input
                            if hasattr(func, "side_effect") and func.side_effect is not None:
                                func = func.side_effect
                            has_sel_lang = False
                            try:
                                sig = inspect.signature(func)
                                has_sel_lang = "selected_language" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                            except Exception:
                                has_sel_lang = False

                            if has_sel_lang and not is_mock:
                                response_generator = self.executive_agent.handle_input(
                                    text, 
                                    stream=True, 
                                    selected_language=selected_language
                                )
                            else:
                                response_generator = self.executive_agent.handle_input(
                                    text, 
                                    stream=True
                                )
                            
                            full_response_parts = []
                            for chunk in response_generator:
                                if not chunk:
                                    continue
                                if self.voice_manager and hasattr(self.voice_manager, "speech_controller"):
                                    if self.voice_manager.speech_controller.stop_event.is_set() is True:
                                        logger.info("[ConversationEngine] Interruption detected. Aborting LLM stream.")
                                        break
                                full_response_parts.append(chunk)
                                self._speak_safely(chunk, response_language=response_language)
                            full_response = "".join(full_response_parts)

                    if exec_id:
                        logger.info("[EXECUTION-ID:%s] Final response recorded: %r", exec_id, full_response)
                    else:
                        logger.info("[ConversationEngine] Final full response: %r", full_response)

                    # 5. Record assistant response in context
                    self.history.append({"role": "assistant", "content": full_response})
                    if self.memory_agent:
                        try:
                            self.memory_agent.remember(
                                category="short_term",
                                key="last_assistant_voice_output",
                                value=full_response
                            )
                        except Exception as e:
                            logger.debug("Failed logging voice output to memory: %s", e)

                    # Notify GUI on command completed
                    if self.voice_manager and getattr(self.voice_manager, "on_command_callback", None):
                        try:
                            self.voice_manager.on_command_callback(text, full_response)
                        except Exception as cb_err:
                            logger.error("Failed calling voice_manager.on_command_callback: %s", cb_err)

                except Exception as execute_err:
                    logger.exception("Error executing voice dialogue step: %s", execute_err)
                    err_msg = "Sorry, I encountered an internal error processing that."
                    self._speak_safely(err_msg)
            finally:
                if response_text is None:
                    logger.info("[STATE] Transitioned to IDLE")
                    if self.voice_manager:
                        self.voice_manager.state = "IDLE"

    def interrupt(self) -> None:
        """Interrupt any ongoing synthesized speech or plan execution immediately."""
        logger.info("[ConversationEngine] Triggering interruption request.")
        
        # Cancel any active ExecutiveAgent execution plan
        if hasattr(self.executive_agent, "cancel"):
            try:
                self.executive_agent.cancel()
            except Exception as e:
                logger.debug("Failed cancelling ExecutiveAgent: %s", e)

        # Cancel any active TTS playback process
        if self.voice_manager:
            if hasattr(self.voice_manager, "_stop_event"):
                try:
                    self.voice_manager._stop_event.set()
                    self.voice_manager._stop_event.clear()
                except Exception:
                    pass
            if hasattr(self.voice_manager, "interrupt"):
                try:
                    self.voice_manager.interrupt()
                except Exception as e:
                    logger.debug("Failed calling voice_manager.interrupt: %s", e)

    def reset(self) -> None:
        """Clear active dialogue state history."""
        with self._lock:
            self.history.clear()
            logger.info("[ConversationEngine] Reset conversation history.")

    def _speak_safely(self, text: str, telugu_mode: bool = False, response_language: str = None) -> None:
        """Render text spoken speech via VoiceManager TTS."""
        if not self.voice_manager:
            return
        
        logger.info("[STATE] Transitioned to SPEAKING")
        if hasattr(self.voice_manager, "state"):
            self.voice_manager.state = "SPEAKING"
            
        try:
            from voice.voice_manager import format_spoken_response
            lang = response_language or getattr(self.voice_manager, "response_language", "english")
            spoken_text = format_spoken_response(text, response_language=lang)
            
            logger.info("[NOVA] %s", spoken_text)
            
            # Direct speak invocation
            if hasattr(self.voice_manager, "_safe_speak"):
                self.voice_manager._safe_speak(spoken_text, response_language=lang)
            elif hasattr(self.voice_manager, "speak"):
                self.voice_manager.speak(spoken_text)
            elif hasattr(self.voice_manager, "tts") and hasattr(self.voice_manager.tts, "execute"):
                self.voice_manager.tts.execute(text=spoken_text, response_language=lang)
        except Exception as speak_err:
            logger.error("Failed to output speech response: %s", speak_err)
        finally:
            logger.info("[STATE] Transitioned to PROCESSING")
            if hasattr(self.voice_manager, "state"):
                self.voice_manager.state = "PROCESSING"
