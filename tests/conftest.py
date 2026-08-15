import pytest
from core.executive_agent import ExecutiveAgent
from core.language_session import LanguageSession

@pytest.fixture(autouse=True)
def clean_processed_requests():
    ExecutiveAgent._processed_requests.clear()
    LanguageSession().selected_language = "en"
    yield
    ExecutiveAgent._processed_requests.clear()
    LanguageSession().selected_language = "en"


@pytest.fixture(autouse=True)
def cleanup_voice_threads():
    yield
    try:
        from voice.always_listening import _active_engines
        for engine in list(_active_engines):
            try:
                engine.stop()
            except Exception:
                pass
        _active_engines.clear()
    except Exception:
        pass

    try:
        from voice.voice_manager import _active_managers
        for vm in list(_active_managers):
            try:
                vm.stop()
            except Exception:
                pass
        _active_managers.clear()
    except Exception:
        pass

    try:
        from voice.speech_controller import _active_speech_controllers
        for sc in list(_active_speech_controllers):
            try:
                sc.stop()
            except Exception:
                pass
        _active_speech_controllers.clear()
    except Exception:
        pass
