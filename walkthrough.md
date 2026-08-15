# Walkthrough - Multilingual TTS, Language Lock & GUI Permission Callbacks

We have successfully resolved the remaining multilingual issues and security gate permission callback bugs in Nova, completing all implementation phases.

## Changes Made

### 1. Strict Language Lock & State Sync
- In [voice/voice_manager.py](file:///c:/Users/asus/OneDrive/Desktop/nova/voice/voice_manager.py):
  - Updated `selected_language` properties to store and return standardized ISO language codes (`en`, `te`, `hi`, `ta`, `kn`).
  - Synced language changes directly to the `engine` instance to prevent state divergence.
  - Formatted instructions in `_safe_engine` to map short codes back to full language names (e.g. `te` -> `Telugu`) for prompt propagation compatibility.

### 2. Provider Instruction Routing
- Modified [core/planner.py](file:///c:/Users/asus/OneDrive/Desktop/nova/core/planner.py) to disable `should_direct_return` optimization for non-English queries, enabling the LLM to translate tool outputs into the target selected language.
- Configured LLM system instructions to enforce responses strictly in `selected_language` regardless of input query language.

### 3. Edge-TTS & Windows SAPI Capability Verification
- In [tools/voice.py](file:///c:/Users/asus/OneDrive/Desktop/nova/tools/voice.py):
  - Created a robust Edge-TTS voice-mapping mechanism (`get_voice_for_language`).
  - Configured local SAPI fallback to allow non-English fallbacks ONLY if a matching language voice is actually installed (e.g. Telugu voice matching `"44a"` or description containing `"telugu"`).
  - Prevented silent English SAPI fallback for non-English text to stop English voices from attempting to speak foreign unicode texts.

### 4. Thread-Safe GUI Permission Gate Popups
- In [interface/gui/gui_app.py](file:///c:/Users/asus/OneDrive/Desktop/nova/interface/gui/gui_app.py):
  - Imported `QObject` and integrated a `PermissionRequester` class with PyQt6 `pyqtSignal`.
  - Connected the signal using a thread-safe `Qt.ConnectionType.BlockingQueuedConnection`.
  - Registered `gui_permission_callback` with `engine.permission_gate`.
  - Safely prompt the user on the main thread via a `QMessageBox` question dialog for high-risk actions, blocking the background planning thread until the user clicks Yes/No.

### 5. Automated Tests
- Created a comprehensive test suite in [tests/test_language_lock.py](file:///c:/Users/asus/OneDrive/Desktop/nova/tests/test_language_lock.py) testing:
  1. Default language = English.
  2. Language switches to Telugu.
  3. Non-switch multilingual queries (e.g. `"Telugu lo YouTube open cheyyi"`) do not alter `selected_language`.
  4. System instructions route response languages correctly.
  5. Conversation history resets preserve `selected_language`.
  6. Folder creation permissions verify the registered callback.
  7. Edge-TTS network errors do not fall back to English SAPI for non-English text.

---

## Verification Results

### 1. Compilation Verification
All Python files compiled successfully without syntax or import errors:
```powershell
.venv\Scripts\python -m py_compile core/engine.py core/planner.py voice/voice_manager.py voice/always_listening.py voice/conversation_engine.py voice/speech_to_text.py tools/voice.py utils/language_switch.py llm/gemini_provider.py llm/ollama_provider.py llm/routing_provider.py interface/gui/gui_app.py
```

### 2. Unit and Regression Test Suites
**All 11 Multilingual, TTS, and SAPI Regression Tests Passed Successfully:**
- `tests/test_language_lock.py` — **1 passed**
- `tests/test_multilingual_tts.py` — **3 passed**
- `tests/test_multilingual_selection.py` — **3 passed**
- `tests/test_telugu_tts_automated.py` — **4 passed**
```
tests/test_language_lock.py::test_language_lock_and_switching PASSED
tests/test_multilingual_tts.py::test_language_voice_mapping PASSED
tests/test_multilingual_tts.py::test_response_language_changes_and_propagation PASSED
tests/test_multilingual_tts.py::test_no_actual_network_calls_during_unit_tests PASSED
tests/test_multilingual_selection.py::test_language_selection_variations PASSED
tests/test_multilingual_selection.py::test_language_selection_retry_limit PASSED
tests/test_multilingual_selection.py::test_whisper_multilingual_mode_parameter PASSED
tests/test_telugu_tts_automated.py::test_prompt_propagation_and_telugu_unicode PASSED
tests/test_telugu_tts_automated.py::test_voice_selection_fails_when_english_only_selected PASSED
tests/test_telugu_tts_automated.py::test_voice_selection_passes_when_telugu_voice_available PASSED
tests/test_telugu_tts_automated.py::test_english_voice_restoration PASSED

======================== 11 passed, 1 warning in 9.75s ========================
```
