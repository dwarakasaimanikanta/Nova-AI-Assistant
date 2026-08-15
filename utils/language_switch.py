import logging
import re
import difflib
from typing import Any, Optional
from core.conversation_context import get_conversation_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# STT phonetic variant sets for each language name.
# Whisper (base model) frequently mis-hears language names, especially
# Tamil ("tameel", "thamil") and Kannada ("kanada"). These variants are
# used in the fuzzy switch-intent detection path.
# ---------------------------------------------------------------------------
_LANG_VARIANTS: dict = {
    "en": {"english", "inglish", "englis", "englsh", "anglish", "inglis", "ఇంగ్లీష్", "ఇంగ్లిష్", "இங்கிலீஷ்", "இங்கிலிஷ்", "ಇಂಗ್ಲಿಷ್", "ಇಂಗ್ಲಿಶ್", "englishlo", "english-lo"},
    "te": {"telugu", "telgu", "telugoo", "telug", "telegu", "telugo", "teluguu", "తెలుగు", "తెలుగులో", "telugulo", "telugulomatladu", "telugulomatlaadu", "telugulo maatlaadu", "telugu lo matladu", "telugulo matladu"},
    "hi": {"hindi", "hindee", "hindy", "hind", "hindii", "hinde", "हिंदी", "हिन्दी", "హిందీ", "hindime", "hindi me bolo", "hindi mein bolo"},
    "ta": {"tamil", "tameel", "thamil", "thameel", "tamila", "tamla", "thamila", "tamill", "tamils", "tamilz", "தமிழ்", "தமிழில்", "tamilla", "tamil la pesu"},
    "kn": {"kannada", "kanada", "kannad", "kannadaa", "kanad", "kanned", "ಕನ್ನಡ", "ಕನ್ನಡದಲ್ಲಿ", "kannadadalli", "kannadanalli", "kannada dalli maatadu", "kannada nalli maatadu", "kannadadalli maatadu"},
}

# Words that signal explicit language-switch intent.
# ONLY these verbs may trigger a switch — prevents "What is Tamil Nadu?" etc.
_SWITCH_INTENT_WORDS = {
    "switch", "speak", "talk", "change", "use", "select",
    "start", "begin", "set", "enable", "activate",
}
def extract_intended_language(text: str) -> Optional[str]:
    """
    Core language intent extractor.
    Returns 'en', 'te', 'hi', 'ta', 'kn', or None.
    Handles exact names, phonetics, negations, switch command verification,
    and returns the last spoken language as a correction fallback when multiple are listed.
    """
    if not text:
        return None

    # Normalization: lower, strip punctuation, collapse whitespace
    cleaned = re.sub(r'[.,!?\-_()"\'\`:]', ' ', text.lower())
    normalized = " ".join(cleaned.split())
    if not normalized:
        return None

    # Find all occurrences of any language variants in the text
    lang_matches = []  # list of (lang, start_pos, end_pos)
    for lang, variants in _LANG_VARIANTS.items():
        for variant in variants:
            # Check with non-ASCII safe word boundaries (space, start/end of string)
            pat = r"(?:^|(?<=\s))" + re.escape(variant) + r"(?=\s|$)"
            for match in re.finditer(pat, normalized):
                lang_matches.append((lang, match.start(), match.end()))

    if not lang_matches:
        return None

    # Check negations for each match
    # E.g. "not", "no", "dont", "don't", "instead of", "never", "n't"
    negations = ["not", "no", "dont", "don't", "instead of", "never", "n't"]
    non_negated_matches = []

    for lang, start, end in lang_matches:
        # Look back up to 15 characters before the word
        prefix = normalized[max(0, start - 15):start].strip()
        is_negated = False
        for neg in negations:
            if re.search(r'\b' + re.escape(neg) + r'\b', prefix):
                is_negated = True
                break
        if not is_negated:
            non_negated_matches.append((lang, start))

    # If all matches were negated, we cannot select any language
    if not non_negated_matches:
        return None

    # Check for explicit switch commands pointing to a language
    # Switch phrases: "switch to X", "speak in X", "talk in X", "X lo matladu", etc.
    for lang, start in non_negated_matches:
        for variant in _LANG_VARIANTS[lang]:
            sub_patterns = [
                r"\b(switch\s+to|speak\s+in|talk\s+in|change\s+to|use|select|set|enable|activate)\s+" + re.escape(variant) + r"\b",
                r"\b" + re.escape(variant) + r"\s+(mode|please)\b",
                r"\b" + re.escape(variant) + r"\s+lo\s+(matladu|maatlaadu|matladandi|maatlaadandi)\b",
                r"తెలుగులో\s*(మాట్లాడు|మాట్లాడండి|సంభాషించు)"
            ]
            for pat in sub_patterns:
                if re.search(pat, normalized):
                    return lang

    # If there is only one non-negated language mentioned, return it
    unique_langs = list(set(lang for lang, _ in non_negated_matches))
    if len(unique_langs) == 1:
        return unique_langs[0]

    # If multiple languages are mentioned (e.g. "Hindi. Tamil."), select the last one (correction behavior)
    non_negated_matches.sort(key=lambda x: x[1])
    return non_negated_matches[-1][0]


def parse_spoken_language(transcript: str, detected_lang: Optional[str] = None, confidence: float = 0.0) -> Optional[str]:
    """
    Parse the spoken language from the transcript, with fallback to Whisper's detected language.
    Returns one of 'te', 'en', 'hi', 'ta', 'kn', or None if unrecognized.
    """
    matched = extract_intended_language(transcript)
    if matched:
        return matched

    # Fallback evidence signal if transcript matches nothing but Whisper detected a language with confidence
    if detected_lang and confidence >= 0.5:
        cleaned = detected_lang.strip().lower()
        normal_map = {
            "en": "en", "english": "en",
            "te": "te", "telugu": "te",
            "hi": "hi", "hindi": "hi",
            "ta": "ta", "tamil": "ta",
            "kn": "kn", "kannada": "kn"
        }
        return normal_map.get(cleaned)

    return None


def _perform_switch(matched_lang: str, target_obj: Any) -> bool:
    """Helper executing all steps to change session language across subsystems."""
    _voice_map = {
        "en": "en-US-AriaNeural",
        "te": "te-IN-ShrutiNeural",
        "hi": "hi-IN-SwaraNeural",
        "ta": "ta-IN-PallaviNeural",
        "kn": "kn-IN-SapnaNeural",
    }
    logger.info("[LANGUAGE] Language switch requested: true")
    logger.info("[LANGUAGE] Target language: %s | Voice: %s", matched_lang, _voice_map.get(matched_lang, "unknown"))

    # Step 1: Resolve engine and voice_manager references
    engine = None
    voice_manager = None

    if hasattr(target_obj, "selected_language"):
        if hasattr(target_obj, "engine") and target_obj.engine:
            engine = target_obj.engine
        if hasattr(target_obj, "voice_manager") and target_obj.voice_manager:
            voice_manager = target_obj.voice_manager
    if not engine and hasattr(target_obj, "engine"):
        engine = target_obj.engine
    if not voice_manager and hasattr(target_obj, "voice_manager"):
        voice_manager = target_obj.voice_manager

    # Step 2: Immediately stop any active TTS before switching
    _interrupt_tts(voice_manager or target_obj)

    # Step 3: Update selected_language on all objects atomically (delegates to singleton)
    from core.language_session import LanguageSession
    LanguageSession().selected_language = matched_lang

    for obj in filter(None, [target_obj, engine, voice_manager]):
        if hasattr(obj, "selected_language"):
            try:
                obj.selected_language = matched_lang
            except Exception:
                pass
        if hasattr(obj, "response_language"):
            try:
                obj.response_language = matched_lang
            except Exception:
                pass


    # Clear previous language context/history so LLM starts fresh
    try:
        get_conversation_context().reset()
        logger.info("[LANGUAGE] ConversationContext reset completed.")
    except Exception as reset_err:
        logger.debug("[LANGUAGE] Context reset failed: %s", reset_err)

    logger.info("[LANGUAGE-STATE]")
    logger.info("Selected response language: %s", matched_lang)

    # Speak confirmation in the new language if target is VoiceManager or has _safe_speak
    confirm_target = voice_manager or target_obj
    if hasattr(confirm_target, "_safe_speak"):
        confirmations = {
            "en": "Sure Boss. I'll speak in English. How can I help you?",
            "te": "సరే బాస్. ఇక నుంచి తెలుగులో మాట్లాడతాను. మీకు ఏం సహాయం కావాలి?",
            "hi": "ठीक है बॉस। अब से मैं हिंदी में बात करूंगा। मैं आपकी कैसे मदद कर सकता हूँ?",
            "ta": "சரி பாஸ். இனிமேல் நான் தமிழில் பேசுவேன். நான் உங்களுக்கு எப்படி உதவலாம்?",
            "kn": "ಸರಿ ಬಾಸ್. ಇನ್ನು ಮುಂದೆ ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"
        }
        confirm_msg = confirmations.get(matched_lang, "Sure Boss. I'll speak in English.")
        try:
            confirm_target._safe_speak(confirm_msg, response_language=matched_lang)
        except Exception as speak_err:
            logger.error("[LANGUAGE] Failed speaking confirmation: %s", speak_err)

    return True


def detect_and_handle_language_switch(command_text: str, target_obj: Any) -> bool:
    """
    Checks if command_text is an explicit language switch command.
    If so: stops current TTS, updates selected_language everywhere, and returns True.
    Returns False if no language switch was detected.

    Enforces that random speech mentions of a language (e.g. "tell me about Hindi history")
    do NOT trigger a switch. Only explicit switch verbs/commands or exact name matches are accepted.
    """
    if not command_text:
        return False

    cleaned = re.sub(r'[.,!?\-_()"\'\`:]', ' ', command_text.lower()).strip()
    normalized = " ".join(cleaned.split())
    if not normalized:
        return False

    # 1. Exact name matches (e.g. user just said "Telugu" or "English")
    for lang, variants in _LANG_VARIANTS.items():
        if normalized in variants:
            return _perform_switch(lang, target_obj)

    # 2. Check for explicit switch commands in normalized text
    has_switch_cmd = False
    for lang, variants in _LANG_VARIANTS.items():
        for variant in variants:
            patterns = [
                r"\b(switch\s+to|speak\s+in|talk\s+in|change\s+to|use|select|set|enable|activate)\s+" + re.escape(variant) + r"\b",
                r"\b" + re.escape(variant) + r"\s+(mode|please)\b",
                r"\b" + re.escape(variant) + r"\s+lo\s+(matladu|maatlaadu|matladandi|maatlaadandi)\b",
                r"తెలుగులో\s*(మాట్లాడు|మాట్లాడండి|సంభాషించు)",
                r"हिंदी\s*में\s*(बात\s*करो|बोलो)",
                r"தமிழில்\s*(பேசு|பேசுங்கள்)",
                r"ಕನ್ನಡದಲ್ಲಿ\s*(ಮಾತನಾಡು|ಮಾತನಾಡಿ)"
            ]
            for pat in patterns:
                if re.search(pat, normalized):
                    has_switch_cmd = True
                    break
            if has_switch_cmd:
                break
        if has_switch_cmd:
            break

    # If it is an explicit switch command, parse it using negation rules and perform switch
    if has_switch_cmd:
        matched_lang = extract_intended_language(command_text)
        if matched_lang:
            return _perform_switch(matched_lang, target_obj)

    return False


def _interrupt_tts(obj: Any) -> None:
    """Best-effort TTS interruption when switching language. Never raises."""
    try:
        from voice.speech_controller import SpeechController
        if SpeechController._instance is not None:
            SpeechController._instance.interrupt()
            return
    except Exception:
        pass
    for attr in ("interrupt", "speech_controller"):
        try:
            target = getattr(obj, attr, None)
            if callable(target):
                target()
                return
            if target and hasattr(target, "interrupt") and callable(target.interrupt):
                target.interrupt()
                return
        except Exception:
            pass

