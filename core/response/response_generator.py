from core.response.language_templates import TEMPLATES

class ResponseGenerator:
    """Generates localized responses for the voice TTS output system."""

    @staticmethod
    def generate(key: str, lang: str = "en", **kwargs) -> str:
        # Standardize language code
        normalized_lang = {
            "en": "en", "english": "en",
            "te": "te", "telugu": "te",
            "hi": "hi", "hindi": "hi",
            "ta": "ta", "tamil": "ta",
            "kn": "kn", "kannada": "kn"
        }.get(lang.strip().lower(), "en")

        lang_templates = TEMPLATES.get(normalized_lang, TEMPLATES["en"])
        template_str = lang_templates.get(key, TEMPLATES["en"].get(key, ""))
        
        if not template_str:
            return ""
            
        try:
            return template_str.format(**kwargs)
        except Exception:
            return template_str
