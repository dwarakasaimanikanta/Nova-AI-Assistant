import os
import pytest
from unittest.mock import MagicMock, patch

from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from voice.voice_manager import VoiceManager
from tools.voice import VoiceTool, get_voice_for_language
from utils.language_switch import detect_and_handle_language_switch
from core.planner import AgentPlanner
from llm.routing_provider import RoutingLLMProvider

def test_language_lock_and_switching():
    # 1. Default language = English
    engine = NovaEngine(memory=ShortTermMemory())
    
    # Force initialize conversation/planner using RoutingLLMProvider for hermetic unit testing
    provider = RoutingLLMProvider(gemini_key="mock_key")
    engine.conversation = AgentPlanner(
        provider=provider,
        memory=engine.memory,
        registry=engine.registry,
        executor=engine.executor,
        permission_gate=engine.permission_gate,
    )
    
    assert engine.selected_language == "en"

    # 2. Switch to Telugu via detect_and_handle_language_switch
    # Explicit switch
    res = detect_and_handle_language_switch("switch to Telugu", engine)
    assert res is True
    assert engine.selected_language == "te"

    # 3. English command while Telugu selected -> System instruction should enforce Telugu
    with patch("llm.routing_provider.RoutingLLMProvider.generate") as mock_gen:
        mock_gen.return_value = MagicMock(function_calls=[], raw_content=None, text="సరే బాస్")
        engine.handle_input("How is the weather?")
        called_args, called_kwargs = mock_gen.call_args
        assert "Respond ONLY in Telugu." in called_kwargs.get("system_instruction", "")

    # 4. Telugu command while Telugu selected -> Telugu response
    with patch("llm.routing_provider.RoutingLLMProvider.generate") as mock_gen:
        mock_gen.return_value = MagicMock(function_calls=[], raw_content=None, text="సరే బాస్")
        engine.handle_input("సమయం ఎంత?")
        called_args, called_kwargs = mock_gen.call_args
        assert "Respond ONLY in Telugu." in called_kwargs.get("system_instruction", "")

    # 5. Hindi command while Telugu selected -> Telugu response
    with patch("llm.routing_provider.RoutingLLMProvider.generate") as mock_gen:
        mock_gen.return_value = MagicMock(function_calls=[], raw_content=None, text="సరే బాస్")
        engine.handle_input("समय क्या हुआ है?")
        called_args, called_kwargs = mock_gen.call_args
        assert "Respond ONLY in Telugu." in called_kwargs.get("system_instruction", "")

    # 6. Switch to English
    res = detect_and_handle_language_switch("switch to English", engine)
    assert res is True
    assert engine.selected_language == "en"

    # 7. Telugu command while English selected -> English response
    with patch("llm.routing_provider.RoutingLLMProvider.generate") as mock_gen:
        mock_gen.return_value = MagicMock(function_calls=[], raw_content=None, text="Sure Boss")
        engine.handle_input("సమయం ఎంత?")
        called_args, called_kwargs = mock_gen.call_args
        assert "Respond ONLY in English." in called_kwargs.get("system_instruction", "")

    # 8. Switch to Hindi
    res = detect_and_handle_language_switch("switch to Hindi", engine)
    assert res is True
    assert engine.selected_language == "hi"

    # 9. English command while Hindi selected -> Hindi response
    with patch("llm.routing_provider.RoutingLLMProvider.generate") as mock_gen:
        mock_gen.return_value = MagicMock(function_calls=[], raw_content=None, text="ठीक है")
        engine.handle_input("How is the weather?")
        called_args, called_kwargs = mock_gen.call_args
        assert "Respond ONLY in Hindi." in called_kwargs.get("system_instruction", "")

    # 10. Switch to Tamil
    res = detect_and_handle_language_switch("switch to Tamil", engine)
    assert res is True
    assert engine.selected_language == "ta"

    # 11. English command while Tamil selected -> Tamil response
    with patch("llm.routing_provider.RoutingLLMProvider.generate") as mock_gen:
        mock_gen.return_value = MagicMock(function_calls=[], raw_content=None, text="சரி")
        engine.handle_input("How is the weather?")
        called_args, called_kwargs = mock_gen.call_args
        assert "Respond ONLY in Tamil." in called_kwargs.get("system_instruction", "")

    # 12. Switch to Kannada
    res = detect_and_handle_language_switch("switch to Kannada", engine)
    assert res is True
    assert engine.selected_language == "kn"

    # 13. English command while Kannada selected -> Kannada response
    with patch("llm.routing_provider.RoutingLLMProvider.generate") as mock_gen:
        mock_gen.return_value = MagicMock(function_calls=[], raw_content=None, text="ಸರಿ")
        engine.handle_input("How is the weather?")
        called_args, called_kwargs = mock_gen.call_args
        assert "Respond ONLY in Kannada." in called_kwargs.get("system_instruction", "")

    # 14. Normal commands never change selected_language
    engine.selected_language = "te"
    res_switch = detect_and_handle_language_switch("Telugu lo YouTube open cheyyi", engine)
    assert res_switch is False
    assert engine.selected_language == "te"

    # 15. Conversation reset does not change selected_language
    from voice.conversation_engine import VoiceConversationEngine
    conv_eng = VoiceConversationEngine(executive_agent=engine, voice_manager=MagicMock())
    engine.selected_language = "te"
    conv_eng.reset()
    assert engine.selected_language == "te"

    # 16. TTS voice follows selected_language
    assert get_voice_for_language("en") == "en-US-AriaNeural"
    assert get_voice_for_language("te") == "te-IN-ShrutiNeural"
    assert get_voice_for_language("hi") == "hi-IN-SwaraNeural"
    assert get_voice_for_language("ta") == "ta-IN-PallaviNeural"
    assert get_voice_for_language("kn") == "kn-IN-SapnaNeural"

    # 17. File manager permission callback is registered
    assert engine.permission_gate._callback is not None

    # 18. Create-folder command actually creates a folder
    fm_tool = engine.registry.get_tool("file_manager")
    assert fm_tool is not None
    import shutil
    test_dir = os.path.abspath("./test_nova_folder")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
        
    try:
        # Check permission gate check
        assert engine.permission_gate.check_permission(fm_tool, {"action": "create_folder", "path": test_dir}) is True
        # Execute tool
        res = engine.executor.execute_tool(fm_tool, {"action": "create_folder", "path": test_dir})
        assert "Folder created" in res or "Success" in res
        assert os.path.exists(test_dir)
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # 19. Edge TTS non-English failure never falls back incorrectly to English SAPI
    tool = VoiceTool()
    with patch("tools.voice.platform.system", return_value="Windows"):
        with patch("tools.voice.get_voice_for_language", return_value="te-IN-ShrutiNeural"):
            with patch("edge_tts.Communicate") as mock_comm:
                mock_comm.side_effect = RuntimeError("Network error")
                with patch("win32com.client.Dispatch") as mock_sapi:
                    # Configure mock_sapi's GetVoices to have no Telugu-capable voice
                    mock_speaker = MagicMock()
                    mock_sapi.return_value = mock_speaker
                    mock_voices = MagicMock()
                    mock_speaker.GetVoices.return_value = mock_voices
                    mock_voices.__len__.return_value = 0
                    
                    res = tool.execute(text="సరే బాస్", response_language="te")
                    assert "Failure" in res
                    mock_speaker.Speak.assert_not_called()
