"""
voice/conversation_engine.py
----------------------------
Voice Conversation Engine driving multi-turn spoken dialogue,
TTS streaming, context lifecycle, and active interruption.
"""

from __future__ import annotations

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

    def process_speech(self, text: str) -> None:
        """
        Receive transcribed input text, coordinate pipeline execution,
        and stream/output spoken response.
        """
        with self._lock:
            text = text.strip()
            if not text:
                return

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

            # 3. Handle active interruption (stop any ongoing TTS playback)
            self.interrupt()

            # 4. Process command using ExecutiveAgent handle_input stream
            logger.info("[ConversationEngine] Dispatching input to ExecutiveAgent: %r", text)
            try:
                # Pass stream=True for chunked response capability
                response_generator = self.executive_agent.handle_input(text, stream=True)
                
                # Consume stream chunks
                full_response_parts = []
                for chunk in response_generator:
                    if not chunk:
                        continue
                    full_response_parts.append(chunk)
                    
                    # Speak chunk immediately
                    self._speak_safely(chunk)

                full_response = "".join(full_response_parts)
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

            except Exception as execute_err:
                logger.exception("Error executing voice dialogue step: %s", execute_err)
                err_msg = "Sorry, I encountered an internal error processing that."
                self._speak_safely(err_msg)

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
                    # Re-clear stop event to allow subsequent speech outputs
                    self.voice_manager._stop_event.clear()
                except Exception as e:
                    logger.debug("Failed triggering stop_event on VoiceManager: %s", e)
            
            # If voice_manager has a running tts instance stop it directly
            if hasattr(self.voice_manager, "tts") and hasattr(self.voice_manager.tts, "stop_event"):
                try:
                    self.voice_manager.tts.stop_event.set()
                    self.voice_manager.tts.stop_event.clear()
                except Exception as e:
                    logger.debug("Failed clearing VoiceTool stop_event: %s", e)

    def reset(self) -> None:
        """Clear active dialogue state history."""
        with self._lock:
            self.history.clear()
            logger.info("[ConversationEngine] Reset conversation history.")

    def _speak_safely(self, text: str) -> None:
        """Render text spoken speech via VoiceManager TTS."""
        if not self.voice_manager:
            return
        try:
            from voice.voice_manager import format_spoken_response
            spoken_text = format_spoken_response(text)
            
            # Direct speak invocation
            if hasattr(self.voice_manager, "_safe_speak"):
                self.voice_manager._safe_speak(spoken_text)
            elif hasattr(self.voice_manager, "speak"):
                self.voice_manager.speak(spoken_text)
            elif hasattr(self.voice_manager, "tts") and hasattr(self.voice_manager.tts, "execute"):
                self.voice_manager.tts.execute(text=spoken_text)
        except Exception as speak_err:
            logger.error("Failed to output speech response: %s", speak_err)
