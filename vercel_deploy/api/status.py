"""
NOVA Web API — /api/status  v3.0
- Reports primary and fallback AI provider status
- Reports live web search capability (Serper.dev or DuckDuckGo)
"""

import os
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler

from dotenv import load_dotenv


def _ensure_env():
    here = Path(__file__).resolve().parent
    candidates = [here, here.parent, Path.cwd(), here.parent.parent]
    for directory in candidates:
        for filename in (".env.local", ".env"):
            env_path = directory / filename
            if env_path.is_file():
                load_dotenv(dotenv_path=env_path, override=False)


def _is_real_key(value: str) -> bool:
    if not value:
        return False
    cleaned = value.strip()
    placeholders = {
        "your_gemini_api_key_here", "your_api_key",
        "your_gemini_api_key", "your_api_key_here",
        "your_groq_api_key_here", "your_openrouter_api_key_here",
        "your_openai_api_key_here",
    }
    return bool(cleaned) and cleaned.lower() not in placeholders


def _get_api_key(var_name: str) -> str | None:
    _ensure_env()
    key = os.environ.get(var_name, "")
    if _is_real_key(key):
        return key.strip()
    return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        _ensure_env()

        primary_key = _get_api_key("GEMINI_API_KEY")
        groq_key = _get_api_key("GROQ_API_KEY")
        openrouter_key = _get_api_key("OPENROUTER_API_KEY")
        openai_key = _get_api_key("OPENAI_API_KEY")
        gemini_backup_key = _get_api_key("GEMINI_BACKUP_API_KEY") or _get_api_key("GEMINI_FALLBACK_API_KEY")

        fallback_configured = bool(groq_key or openrouter_key or openai_key or gemini_backup_key)
        fallback_provider = "none"
        fallback_model = "none"

        if groq_key:
            fallback_provider = "Groq"
            fallback_model = os.environ.get("FALLBACK_MODEL", "openai/gpt-oss-120b")
        elif openrouter_key:
            fallback_provider = "OpenRouter"
            fallback_model = os.environ.get("FALLBACK_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        elif openai_key:
            fallback_provider = "OpenAI"
            fallback_model = os.environ.get("FALLBACK_MODEL", "gpt-4o-mini")
        elif gemini_backup_key:
            fallback_provider = "Gemini Backup Key"
            fallback_model = os.environ.get("PRIMARY_MODEL", "gemini-3.6-flash")

        serper_key     = _get_api_key("SERPER_API_KEY")
        web_search_provider = "Serper.dev" if serper_key else "DuckDuckGo (scraper)"
        # DuckDuckGo is always available (no key needed); Serper is better if configured
        web_search_configured = True  # DDG always available as baseline

        body = json.dumps({
            "status":                 "online",
            "assistant":              "NOVA AI Assistant",
            "version":                "3.0.0",
            "environment":            "Vercel Serverless",
            "primary_provider":       "Google Gemini",
            "primary_model":          os.environ.get("PRIMARY_MODEL", "gemini-3.6-flash"),
            "primary_configured":     bool(primary_key),
            "fallback_provider":      fallback_provider,
            "fallback_model":         fallback_model,
            "fallback_configured":    fallback_configured,
            "web_search_provider":    web_search_provider,
            "web_search_configured":  web_search_configured,
            "capabilities": {
                "conversational_ai":          True,
                "multi_provider_failover":    True,
                "google_search_grounding":    bool(primary_key),
                "independent_web_search":     True,
                "web_search_with_fallback":   True,
                "multilingual_support":       True,
                "image_analysis":             True,
                "file_context":               True,
                "desktop_automation":         False,
                "local_voice_recording":      False,
            },
        }, indent=2).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
