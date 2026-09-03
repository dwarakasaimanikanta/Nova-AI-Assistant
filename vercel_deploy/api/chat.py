"""
NOVA Web API — /api/chat  v3.0 (Multi-Provider + Independent Web Search Layer)
- Primary Provider: Google Gemini (google-genai SDK)
- Fallback Providers: Groq, OpenRouter, OpenAI, Gemini Secondary (Zero external deps via urllib)
- Provider-Independent Web Search: DuckDuckGo (zero-dep) + Serper.dev (if SERPER_API_KEY set)
- Search runs BEFORE AI provider selection — Groq & Gemini both receive real live context
- Resilient: Every exception returns valid JSON; function never crashes
"""

import os
import sys
import json
import base64
import traceback
import urllib.request
import urllib.error
import urllib.parse
import re
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from dotenv import load_dotenv

# Try importing google-genai SDK
try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except Exception:
    _GENAI_AVAILABLE = False
    genai = None
    types = None

def _get_gemini_client(api_key: str):
    if not _GENAI_AVAILABLE or not genai:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

def _safe_log(msg: str):
    """Write log messages safely to stderr without Windows charmap errors."""
    try:
        sys.stderr.write(f"{msg}\n")
        sys.stderr.flush()
    except Exception:
        try:
            safe = msg.encode("ascii", errors="replace").decode("ascii")
            sys.stderr.write(f"{safe}\n")
            sys.stderr.flush()
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Multimodal Vision Analysis Models Cascade
# ---------------------------------------------------------------------------
VISION_MODELS_CASCADE = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.7-flash",
    "gemini-flash-latest",
    "gemini-3.1-pro-preview",
    "gemini-pro-latest"
]

DEFAULT_IMAGE_ANALYSIS_PROMPT = "Describe this image in detail, including the main objects, people, environment, colors, and important visual details."

LANGUAGE_INSTRUCTIONS = {
    "te": "Please provide your answer in natural, fluent Telugu (తెలుగు) using conversational Telugu style.",
    "hi": "Please provide your answer in natural, fluent Hindi (हिन्दी).",
    "ta": "Please provide your answer in natural, fluent Tamil (தமிழ்).",
    "kn": "Please provide your answer in natural, fluent Kannada (ಕನ್ನಡ).",
    "en": "Please provide your answer in clear, natural English."
}

# ---------------------------------------------------------------------------
# Deferred SDK imports
# ---------------------------------------------------------------------------
try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError as _ie:
    _GENAI_AVAILABLE = False
    _GENAI_IMPORT_ERROR = str(_ie)

# ---------------------------------------------------------------------------
# NOVA System Persona
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """You are NOVA (Neural Online Virtual Assistant), a premium, state-of-the-art AI assistant. \
You are highly knowledgeable, intelligent, helpful, practical, fast, and above all — accurate, truthful, and strictly factual.

DEPLOYMENT NOTE: This is the WEB DEPLOYMENT of NOVA hosted on Vercel. Local desktop operations \
(launching VS Code, Paint, Notepad, opening local file paths, executing local command-line commands, \
PortAudio/SAPI speech devices) are unavailable here. If the user asks for desktop-only actions, \
explain that those require the local desktop version of NOVA, but you can generate code, documents, \
and analysis right here.

LANGUAGES: You communicate naturally and fluently in English, Telugu, Hindi, Tamil, Kannada, and other languages. \
If the user writes in Telugu script or Telugu using English letters (e.g. "Allu Arjun cinemalu cheppu", "1 rupee yantha dubai loo"), \
understand the context naturally and respond in the same comfortable style with 100% accurate facts.

═══════════════════════════════════════
STRICT ANTI-HALLUCINATION MANDATE
═══════════════════════════════════════
- NEVER invent, fabricate, or guess fake movie titles, fake character names, fake cameo appearances, fake directors, fake awards, fake dates, or fake statistics.
- If you are asked for a filmography, list of works, biography, or factual data, include ONLY real, verified entries.
- If certain details (e.g., upcoming unannounced projects or future release dates) are unconfirmed, clearly state that they are unannounced or unconfirmed rather than inventing titles or dates.
- Do NOT output internal debug tags, system source labels (such as [moderate], [strong-source], [reference-db], [low-confidence]), or confidence scores in your user-facing response. Present your answers cleanly, directly, and professionally.

═══════════════════════════════════════
CANONICAL CINEMA & FILMOGRAPHY FACTS
═══════════════════════════════════════
Provide 100% verified facts for Indian and Telugu cinema:
- Allu Arjun (Telugu Cinema Filmography):
  • 2003: Gangotri — Simhadri (Debut as lead)
  • 2004: Arya — Arya
  • 2005: Bunny — Bunny / Raja
  • 2006: Happy — Bunny
  • 2007: Desamuduru — Bala Govind
  • 2008: Parugu — Krishna
  • 2009: Arya 2 — Arya
  • 2010: Varudu — Sandeep (Sandy)
  • 2010: Vedam — Cable Raju (Anand Raj)
  • 2011: Badrinath — Badrinath
  • 2012: Julayi — Ravindra Narayan (Ravi)
  • 2013: Iddarammayilatho — Sanju Reddy
  • 2014: Race Gurram — Lakshman "Lucky" Prasad
  • 2015: S/O Satyamurthy — Viraj Anand
  • 2015: Rudhramadevi — Gona Ganna Reddy (Special appearance)
  • 2016: Sarrainodu — Gana (Ganesh)
  • 2017: Duvvada Jagannadham (DJ) — Duvvada Jagannadham / DJ
  • 2018: Naa Peru Surya, Naa Illu India — Surya
  • 2020: Ala Vaikunthapurramuloo — Bantu
  • 2021: Pushpa: The Rise (Part 1) — Pushpa Raj
  • 2024: Pushpa 2: The Rule (Part 2) — Pushpa Raj
  • Note: Allu Arjun never had guest roles in Bheemla Nayak or Mangalavaaram. Never list fake unannounced films like "Madhura" or "Maa Sannidhi".
- Prabhas: Eeswar (2002), Raghavendra (2003), Varsham (2004), Adavi Ramudu (2004), Chakram (2005), Chatrapathi (2005 - Shivaji), Pournami (2006), Yogi (2007), Munna (2007), Bujjigadu (2008), Billa (2009), Ek Niranjan (2009), Darling (2010 - Prabha), Mr. Perfect (2011 - Vicky), Rebel (2012), Mirchi (2013 - Jai), Baahubali: The Beginning (2015 - Shivudu/Baahubali), Baahubali 2: The Conclusion (2017 - Amarendra/Mahendra Baahubali), Saaho (2019 - Siddharth/Ashok), Radhe Shyam (2022 - Vikramaditya), Adipurush (2023 - Raghava), Salaar: Part 1 – Ceasefire (2023 - Deva), Kalki 2898 AD (2024 - Bhairava).
- Mahesh Babu: Rajakumarudu (1999), Yuvaraju (2000), Vamsi (2000), Murari (2001), Takkari Donga (2002), Bobby (2002), Okkadu (2003 - Ajay), Nijam (2003), Naani (2004), Arjun (2004), Athadu (2005 - Nanda Gopal / Pardhu), Pokiri (2006 - Pandu / Krishna Manohar), Sainikudu (2006), Athidhi (2007), Khaleja (2010 - Seetharama Raju), Dookudu (2011 - Ajay), Businessman (2012 - Surya), Seethamma Vakitlo Sirimalle Chettu (2013 - Chinnodu), 1: Nenokkadine (2014 - Gautham), Aagadu (2014 - Shankar), Srimanthudu (2015 - Harsha), Brahmotsavam (2016), Spyder (2017 - Shiva), Bharat Ane Nenu (2018 - Bharat Ram), Maharshi (2019 - Rishi Kumar), Sarileru Neekevvaru (2020 - Ajay Krishna), Sarkaru Vaari Paata (2022 - Mahi), Guntur Kaaram (2024 - Ramana).
- Jr NTR (Nandamuri Taraka Rama Rao Jr.): Ninnu Choodalani (2001), Student No. 1 (2001), Subbu (2001), Aadi (2002), Allari Ramudu (2002), Simhadri (2003), Andhrawala (2004), Samba (2004), Naa Alludu (2005), Narasimhudu (2005), Ashok (2006), Rakhi (2006), Yamadonga (2007 - Raja), Kantri (2008), Adhurs (2010 - Narasimha / Chari), Brindavanam (2010 - Krish), Shakti (2011), Oosaravelli (2011 - Tony), Dammu (2012), Baadshah (2013 - Baadshah / Rama Rao), Ramayya Vasthavayya (2013), Temper (2015 - Daya), Nannaku Prematho (2016 - Abhiram), Janatha Garage (2016 - Anand), Jai Lava Kusa (2017 - Jai, Lava, Kusa), Aravinda Sametha Veera Raghava (2018 - Veera Raghava), RRR (2022 - Komaram Bheem), Devara: Part 1 (2024 - Devara / Vara).

═══════════════════════════════════════
ACCURACY & SPORTS / CRICKET FACTS
═══════════════════════════════════════
Provide accurate, comprehensive, and up-to-date facts directly:
- Virat Kohli Career Centuries (Total International & All Competitive Cricket):
  • International Centuries: 80 (50 in ODIs — All-time World Record, 29 in Tests, 1 in T20Is)
  • IPL (Indian Premier League) Centuries: 8 (All-time Record in IPL history)
  • Total Career Centuries (International + IPL): 88 Total Centuries (80 International + 8 IPL)
  • When the user asks about Virat Kohli's total centuries, always clearly present both: the International total (80) AND the Overall competitive total including IPL (88 centuries), so the answer is 100% complete and unambiguous.
- Sachin Tendulkar: 100 International Centuries (51 Test, 49 ODI) + 1 IPL Century = 101 professional centuries.
- Rohit Sharma: 48 International Centuries (31 ODI, 12 Test, 5 T20I) + 2 IPL Centuries = 50 total centuries.
- Always answer factual, sports, cinema, historical, political, science, mathematics, coding, and general knowledge questions with 100% precision, completeness, and clarity.

═══════════════════════════════════════
FINANCIAL & CURRENCY LOGIC RULES
═══════════════════════════════════════
When discussing currency values, exchange rates, and currency strength ("stronger / weaker" or "ekkuva / thakkuva" in Telugu):
- A foreign currency is STRONGER (High Value / ఎక్కువ విలువ) than INR if 1 Unit of that foreign currency costs MORE than 1 INR:
  • Kuwaiti Dinar (KWD) ≈ ₹275 INR
  • Bahraini Dinar (BHD) ≈ ₹225 INR
  • Omani Rial (OMR) ≈ ₹220 INR
  • British Pound (GBP) ≈ ₹110 INR
  • Euro (EUR) ≈ ₹95 INR
  • US Dollar (USD) ≈ ₹85 INR
  • Singapore Dollar (SGD) ≈ ₹65 INR
  • Australian Dollar (AUD) ≈ ₹56 INR
  • UAE Dirham (AED) ≈ ₹23-26 INR (1 AED ≈ 26 INR, so 500 AED ≈ ₹13,000 INR)
- A foreign currency is WEAKER (Lower Value / తక్కువ విలువ) than INR if 1 Unit of that foreign currency costs LESS than 1 INR:
  • Japanese Yen (JPY) ≈ ₹0.58 INR (1 JPY is only 58 paise)
  • Sri Lankan Rupee (LKR) ≈ ₹0.28 INR (1 LKR is only 28 paise)
  • Pakistani Rupee (PKR) ≈ ₹0.30 INR (1 PKR is only 30 paise)
  • Nepalese Rupee (NPR) ≈ ₹0.62 INR (1 NPR is only 62 paise)
  • South Korean Won (KRW) ≈ ₹0.06 INR
  • Indonesian Rupiah (IDR) ≈ ₹0.005 INR
  • Vietnamese Dong (VND) ≈ ₹0.003 INR
  • Iranian Rial (IRR) ≈ ₹0.002 INR
- NEVER invert this logic. 1 USD = ₹85 means USD is STRONGER / HIGHER VALUE than the Rupee.

═══════════════════════════════════════
ANSWER QUALITY & FORMATTING
═══════════════════════════════════════
- Give direct, helpful, and correct answers for any topic asked (cricket, cinema, science, general knowledge, math, coding, current events, etc.).
- Never invent fake current news or hallucinate.
- Use Markdown headers, tables, and clean bullet points for clarity.
"""

# ---------------------------------------------------------------------------
# Provider & Model Configuration
# ---------------------------------------------------------------------------
PRIMARY_PROVIDER = os.environ.get("PRIMARY_PROVIDER", "gemini").lower().strip()
PRIMARY_MODEL    = os.environ.get("PRIMARY_MODEL", "gemini-3.6-flash").strip()

FALLBACK_PROVIDER = os.environ.get("FALLBACK_PROVIDER", "groq").lower().strip()
FALLBACK_MODEL    = os.environ.get("FALLBACK_MODEL", "openai/gpt-oss-120b").strip()

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

_WEB_TRIGGER_PHRASES = {
    "latest", "current", "currently", "today", "now", "recent", "news",
    "upcoming", "score", "weather", "stock", "price", "announce", "announced",
    "released", "release", "just", "2024", "2025", "2026", "trending", "trend", "trends",
    "working on", "new movie", "new song", "new album", "this week",
    "this month", "this year", "update", "updated", "who is", "what is happening",
    "right now", "this year's", "new project", "new film", "upcoming movie",
    "upcoming film", "next movie", "what happened", "who won", "result",
    "live", "breaking", "confirmed", "official",
    # Cinema, movies & actors
    "movie", "movies", "film", "films", "cinema", "filmography", "discography",
    "actor", "actress", "hero", "heroine", "director", "cast", "box office",
    "collection", "songs", "trailer", "teaser", "review",
    # Telugu cinema & question triggers
    "cinemalu", "cinemala", "cinemalo", "perlu", "herolu", "paatalu", "patalu",
    "recent ga", "ippudu", "chivari", "latest movie", "latest film",
    "act chesina", "chesthunnadu", "chestunnadu", "evaru", "yevaru", "eppudu",
    "yentha", "yenta", "release ayyindi", "release ayindi", "act chesadu",
    # Sports, politics & live data
    "match", "vs", "stats", "century", "centuries", "record", "records",
    "president", "prime minister", "chief minister", "minister", "election", "winner",
    "gold rate", "silver rate", "exchange rate", "dollar rate", "gdp", "rank", "ranking",
    "net worth", "biography", "age of", "height of",
}


# ---------------------------------------------------------------------------
# Search Query Normalizer
# Rewrites Telugu-English mixed queries to clean English so DDG/Serper
# returns relevant results instead of generic dumps.
# ---------------------------------------------------------------------------

# Telugu phrase -> canonical English intent
_TELUGU_QUERY_MAP: list[tuple[str, str]] = [
    # Released-movie signals
    ("recent ga act chesina movie",  "most recently released movie"),
    ("recent ga act chesina film",   "most recently released film"),
    ("recent ga chesina movie",      "most recently released movie"),
    ("chivari movie",                "latest released movie"),
    ("chivari film",                 "latest released film"),
    ("last ga chesina movie",        "most recently released movie"),
    # Current-project signals
    ("ippudu ye movie chesthunnadu", "currently shooting which movie"),
    ("ippudu ye movie chestunnadu",  "currently shooting which movie"),
    ("ippudu chesthunnadu",          "currently working on"),
    ("ippudu chestunnadu",           "currently working on"),
    # Upcoming signals
    ("tarvata movie",                "upcoming next movie"),
    ("mundhu vachithe movie",        "upcoming movie"),
    # General cinema
    ("cinemalu list",                "movies list filmography"),
    ("cinemalu",                     "movies filmography"),
    ("cinemala perlu",               "movies list"),
]

# Suffix phrases to remove from raw message before passing to search
_QUERY_NOISE_SUFFIXES = (
    " enti", " ante enti", " cheppandi", " cheppу", " tell me",
    " em", " ela", " enduku",
)


def _normalize_search_query(message: str, intent: str) -> str:
    """
    Rewrite a raw user message (possibly Telugu in English letters) into
    a clean English search query optimised for DDG/Serper.

    Returns the normalised query string.
    """
    lower = message.lower().strip()

    # Strip noisy Telugu question suffixes
    for suffix in _QUERY_NOISE_SUFFIXES:
        if lower.endswith(suffix):
            lower = lower[: -len(suffix)].strip()

    # Replace known Telugu phrases with English equivalents
    for tel_phrase, eng_phrase in _TELUGU_QUERY_MAP:
        if tel_phrase in lower:
            lower = lower.replace(tel_phrase, eng_phrase)

    # Intent-specific query enhancement
    if intent == "released":
        # For released-movie queries, use "box office release date" keywords
        # so DDG/Serper returns actual release-news articles, not filmography pages.
        if "box office" not in lower and "release date" not in lower:
            if "most recently released" not in lower and "latest released" not in lower:
                if "release" not in lower:
                    lower = lower.rstrip(".?,") + " latest released film box office"
                else:
                    lower = lower.rstrip(".?,") + " box office release date"
            else:
                lower = lower.rstrip(".?,") + " box office release date"
        # Append year range to bias toward recent coverage
        if "2025" not in lower and "2024" not in lower:
            lower = lower + " 2024 2025"
    elif intent == "current_project":
        if "currently" not in lower and "shooting" not in lower:
            lower = lower.rstrip(".?,") + " currently shooting film"
    elif intent == "upcoming":
        if "upcoming" not in lower and "next" not in lower:
            lower = lower.rstrip(".?,") + " upcoming announced movie"

    # Capitalise first letter for cleaner search
    query = lower.strip()
    if query:
        query = query[0].upper() + query[1:]

    return query

# ---------------------------------------------------------------------------
# Independent Web Search Layer (provider-agnostic, zero extra pip deps)
# ---------------------------------------------------------------------------

def _web_search_serper(query: str, serper_key: str, num: int = 8) -> list[dict]:
    """
    Serper.dev JSON search API. Fetches extra so the ranker can select best ones.
    Returns list of {title, url, snippet}.
    """
    payload = json.dumps({"q": query, "num": num}).encode("utf-8")
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-KEY": serper_key,
            "User-Agent": "NOVA-AI-Assistant/3.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3.5) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("organic", [])[:num]:
        title   = item.get("title", "")
        link    = item.get("link", "")
        snippet = item.get("snippet", "")
        if link and snippet:
            results.append({"title": title, "url": link, "snippet": snippet})

    answer_box = data.get("answerBox", {})
    if answer_box.get("answer") or answer_box.get("snippet"):
        results.insert(0, {
            "title":   answer_box.get("title", "Featured Answer"),
            "url":     answer_box.get("link", ""),
            "snippet": answer_box.get("answer") or answer_box.get("snippet", ""),
        })
    return results


def _web_search_ddg(query: str, num: int = 8) -> list[dict]:
    """
    DuckDuckGo HTML scraper. Fetches more results than needed so the ranker
    can pick the best ones. Returns list of {title, url, snippet}.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}&kl=wt-wt"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=3.5) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    results = []
    block_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>'
        r'[\s\S]*?class="result__snippet"[^>]*>([\s\S]*?)</a>',
        re.IGNORECASE
    )
    for m in block_pattern.finditer(html):
        raw_url = m.group(1)
        title   = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        snippet = re.sub(r'<[^>]+>', '', m.group(3)).strip()
        uddg = re.search(r'uddg=([^&"]+)', raw_url)
        final_url = urllib.parse.unquote(uddg.group(1)) if uddg else raw_url
        if final_url and snippet:
            results.append({"title": title or final_url, "url": final_url, "snippet": snippet})
        if len(results) >= num:
            break
    return results


# ---------------------------------------------------------------------------
# Source Quality Ranking and Filtering
# ---------------------------------------------------------------------------

_LOW_QUALITY_DOMAINS = {
    "bollywoodhungama.com", "filmibeat.com", "filmfare.com",
    "cinestaan.com", "moviecrow.com", "cinejosh.com",
    "gulte.com", "123telugu.com", "greatandhra.com",
    "idlebrain.com", "nowrunning.com", "gomolo.com",
    "koimoi.com", "pinkvilla.com", "desimartini.com",
    "glamsham.com", "apherald.com", "fandango.com",
    "rottentomatoes.com", "bookmyshow.com",
    # Aggregator / listicle sites  —  unverified upcoming-movie lists
    "kulfiy.com", "bollymoviereviewz.com", "technosports.co.in",
    "movietalkies.com", "cineblitz.in", "cinemaholic.com",
    "filmy.io", "tollywood.net", "filmiwatch.com",
    "allyourchoice.co.in", "desidust.com", "moneywood.in",
}

# Tier B: major established news / entertainment publications (+20)
_HIGH_QUALITY_DOMAINS = {
    "variety.com", "hollywoodreporter.com", "deadline.com",
    "thehindu.com", "ndtv.com", "hindustantimes.com",
    "timesofindia.indiatimes.com", "scroll.in", "theprint.in",
    "wionews.com", "indiatoday.in", "firstpost.com",
    "deccanchronicle.com", "telanganatoday.com", "sakshi.com",
    "timesnownews.com", "screen.in",
    "instagram.com", "twitter.com", "x.com",
}

# Tier C: reference databases (IMDb, Wikipedia) — useful, but NOT "official confirmation" (+10)
_REFERENCE_DOMAINS = {
    "imdb.com", "wikipedia.org",
}

_LOW_QUALITY_PATH_RE = re.compile(
    # filmography pages: penalise HEAVILY (offset must exceed high-quality domain bonus)
    r'filmography'
    r'|[/-]upcoming-movies'    # /upcoming-movies, -upcoming-movies variants
    r'|/movies-list'
    r'|/all-movies'
    r'|/celebrity/'
    r'|/actor/'
    r'|/actress/'
    r'|/topic/'
    r'|/tag/'
    r'|/search\?'
    r'|full.?movie'
    r'|watch.?online'
    r'|download',
    re.IGNORECASE
)

# Filmography-specific regex for a stronger penalty (-40 instead of -20)
_FILMOGRAPHY_PATH_RE = re.compile(r'filmography', re.IGNORECASE)

# URLs with old year paths — stale content for released-movie queries
_OLD_YEAR_PATH_RE = re.compile(r'/20(1[0-9]|2[0-2])/', re.IGNORECASE)

_NEWS_PATH_RE = re.compile(r'/20(2[3-9]|[3-9]\d)/', re.IGNORECASE)

# Snippets containing these phrases are GOOD evidence for a "released" query
_RELEASED_EVIDENCE_KWS = (
    "released", "release date", "theatrical release", "hit theatres",
    "box office", "premiered", "now playing", "opening",
    "december 2024", "january 2025", "february 2025", "march 2025",
    "april 2025", "may 2025", "june 2025", "july 2025", "august 2025",
    "september 2025", "october 2025", "november 2025", "december 2025",
    "2025 release", "2026 release",
)

# Snippets containing these phrases are BAD evidence for a "released" query
_UPCOMING_EVIDENCE_KWS = (
    "upcoming", "to be released", "will release", "scheduled",
    "in production", "shooting", "announced", "pre-production",
    "set to release", "expected release",
)


def _source_score(result: dict) -> int:
    """Score a search result 0-100. Higher = better quality.
    Also stores '_tier' metadata: 'strong' | 'reference' | 'weak' | 'neutral'
    """
    url     = (result.get("url") or "").lower()
    title   = (result.get("title") or "").lower()
    snippet = (result.get("snippet") or "").lower()
    score   = 50
    tier    = "neutral"

    domain = ""
    try:
        parts = url.split("/")
        if len(parts) >= 3:
            domain = parts[2].replace("www.", "").replace("m.", "")
    except Exception:
        pass

    if any(domain == lq or domain.endswith("." + lq) for lq in _LOW_QUALITY_DOMAINS):
        score -= 25
        tier = "weak"
    elif any(domain == hq or domain.endswith("." + hq) for hq in _HIGH_QUALITY_DOMAINS):
        score += 20
        tier = "strong"
    elif any(domain == rd or domain.endswith("." + rd) for rd in _REFERENCE_DOMAINS):
        score += 10   # reference databases: useful but not authoritative on their own
        tier = "reference"

    # Filmography pages get a heavy penalty regardless of domain quality
    if _FILMOGRAPHY_PATH_RE.search(url):
        score -= 40
    elif _LOW_QUALITY_PATH_RE.search(url):
        score -= 20

    if _NEWS_PATH_RE.search(url):
        score += 15
    if _OLD_YEAR_PATH_RE.search(url):
        score -= 18

    if "youtube.com" in url or "youtu.be" in url:
        if any(kw in title for kw in ["official", "trailer", "teaser", "announcement", "first look"]):
            score += 10
        else:
            score -= 15
        if tier == "neutral":
            tier = "weak"

    for yr in ("2026", "2025"):
        if yr in snippet or yr in title:
            score += 8
            break

    if any(kw in snippet for kw in ["confirmed", "announced", "official", "first look", "teaser", "trailer"]):
        score += 8
    if any(kw in snippet for kw in ["upcoming", "working on", "currently", "in production", "shooting"]):
        score += 5

    if len(snippet) < 60:
        score -= 10

    result["_tier"] = tier
    return max(0, min(score, 100))


def _rank_and_filter(results: list[dict], max_results: int = 5,
                     intent: str = "general") -> list[dict]:
    """Deduplicate, score (base + intent-aware), sort best-first, return top N."""
    if not results:
        return []
    seen_urls: set = set()
    unique: list[dict] = []
    for r in results:
        url = (r.get("url") or "").rstrip("/")
        if url and url not in seen_urls:
            seen_urls.add(url)
            r["_score"] = _source_score(r)
            unique.append(r)

    # Intent-aware secondary scoring pass
    if intent == "released":
        for r in unique:
            snip  = (r.get("snippet") or "").lower()
            title = (r.get("title")   or "").lower()
            # Boost sources that contain clear release-date evidence
            if any(kw in snip or kw in title for kw in _RELEASED_EVIDENCE_KWS):
                r["_score"] = min(100, r["_score"] + 18)
            # Penalise sources that are clearly about upcoming/unreleased films
            if any(kw in snip or kw in title for kw in _UPCOMING_EVIDENCE_KWS):
                r["_score"] = max(0,   r["_score"] - 15)
            # Heavily penalise snippets that only mention very old movies
            # (heuristic: snippet contains years like 2012, 2013 … 2022 but NOT 2023+)
            old_years = re.findall(r'\b(201[0-9]|202[0-2])\b', snip)
            new_years = re.findall(r'\b(202[3-9]|20[3-9]\d)\b', snip)
            if old_years and not new_years:
                r["_score"] = max(0, r["_score"] - 20)
    elif intent == "current_project":
        for r in unique:
            snip = (r.get("snippet") or "").lower()
            if any(kw in snip for kw in ["shooting", "filming", "production", "currently"]):
                r["_score"] = min(100, r["_score"] + 12)
    elif intent == "upcoming":
        for r in unique:
            snip = (r.get("snippet") or "").lower()
            if any(kw in snip for kw in _UPCOMING_EVIDENCE_KWS):
                r["_score"] = min(100, r["_score"] + 12)

    unique.sort(key=lambda x: x["_score"], reverse=True)
    kept = unique[:max_results]
    print(
        f"[NOVA] Source filter ({intent}): {len(results)} raw -> {len(kept)} kept "
        f"(scores: {[r['_score'] for r in kept]})",
        file=sys.stderr,
    )
    return kept


# ---------------------------------------------------------------------------
# Search Intent Classifier
# ---------------------------------------------------------------------------

def _classify_search_intent(message: str) -> str:
    """
    Detect whether the user wants: released movie, upcoming project,
    current active project, or general info.
    Returns: 'released' | 'upcoming' | 'current_project' | 'general'
    """
    lower = message.lower()

    released_signals = [
        "recent ga act chesina", "recent ga", "recently acted", "recently released",
        "last movie", "previous movie", "acted recently", "latest released",
        "chivari", "released movie",
    ]
    current_signals = [
        "currently working", "working on", "currently acting", "shooting now",
        "currently shooting", "current project", "right now", "ippudu",
        "currently", "at present",
    ]
    upcoming_signals = [
        "upcoming", "next movie", "future movie", "announced", "scheduled",
        "releasing soon", "will release", "going to release",
        "new announcement", "upcoming film", "next film",
    ]

    for phrase in released_signals:
        if phrase in lower:
            return "released"
    for phrase in current_signals:
        if phrase in lower:
            return "current_project"
    for phrase in upcoming_signals:
        if phrase in lower:
            return "upcoming"
    if "latest movie" in lower or "latest film" in lower:
        return "released"
    return "general"


def _do_web_search(query: str, intent: str = "general") -> list[dict]:
    """
    Dispatcher: tries Serper.dev first (if SERPER_API_KEY configured),
    then falls back to DuckDuckGo HTML scraper.
    Applies intent-aware source ranking/filtering before returning.
    Returns list of {title, url, snippet} (max 5, best-first).
    """
    raw_results: list[dict] = []

    serper_key = _get_api_key("SERPER_API_KEY")
    if serper_key:
        try:
            raw_results = _web_search_serper(query, serper_key, num=8)
            if raw_results:
                print(f"[NOVA] Serper raw: {len(raw_results)} for: {query[:60]}", file=sys.stderr)
        except Exception as e:
            print(f"[NOVA] Serper failed: {e} - falling back to DDG", file=sys.stderr)

    if not raw_results:
        try:
            raw_results = _web_search_ddg(query, num=8)
            if raw_results:
                print(f"[NOVA] DDG raw: {len(raw_results)} for: {query[:60]}", file=sys.stderr)
        except Exception as e:
            print(f"[NOVA] DDG failed: {e}", file=sys.stderr)

    return _rank_and_filter(raw_results, max_results=5, intent=intent)


def _format_search_context(results: list[dict], message: str = "",
                           intent: str | None = None) -> str:
    """
    Format ranked search results into a concise, intent-aware context block
    for injection into Gemini or Groq prompts.
    Accept pre-computed intent to avoid double-classification.
    """
    if not results:
        return ""

    # Use pre-computed intent if provided; derive from message as fallback
    if intent is None:
        intent = _classify_search_intent(message) if message else "general"

    intent_rules = {
        "released": (
            "User wants the MOST RECENTLY RELEASED movie/film (already in theatres or on streaming).",
            [
                "Use tiered evidence to determine your answer:",
                "  STRONG evidence: a snippet from a news publication, box-office report, or official site that explicitly names the film and its release year.",
                "  REFERENCE evidence: IMDb or Wikipedia listing the film with a release year.",
                "  WEAK evidence: aggregator/blog with no date or conflicting info.",
                "If STRONG or REFERENCE sources consistently name the same film as recently released, answer with cautious wording: 'According to available sources, the most recently released movie is X (released YEAR).'",
                "If evidence is mixed or only WEAK sources are available, say: 'I could not find reliable confirmation of the most recently released movie from available sources.'",
                "CRITICAL: Before attributing a movie to a person, the snippet must EXPLICITLY connect that person to that movie. Do NOT infer from name proximity alone.",
                "EXCLUDE any film described as 'upcoming', 'in production', 'announced', or 'scheduled'.",
                "Do NOT mix released movies with upcoming projects.",
                "Do NOT rely on training knowledge to fill gaps — use only what the snippets say.",
            ]
        ),
        "current_project": (
            "User wants the CURRENT project being actively worked on (in production / shooting right now).",
            [
                "Identify films described as 'currently shooting', 'in production', or 'filming'.",
                "Do NOT mention already-released films as the answer.",
                "Do NOT mention unconfirmed rumours.",
            ]
        ),
        "upcoming": (
            "User wants the NEXT UPCOMING/ANNOUNCED project (not yet released).",
            [
                "Use source tiers to determine your confidence level:",
                "  [strong-source]: news publications or official announcements — you may say 'officially announced' or 'confirmed'.",
                "  [reference-db] (IMDb, Wikipedia): say 'listed on IMDb' or 'reported' — NEVER say 'official confirmation' or 'officially announced' for these alone.",
                "  [low-confidence] aggregators: treat as supporting context only, not as evidence.",
                "If only [reference-db] or [low-confidence] sources exist: say 'There are listings/reports about this project, but I cannot confirm it as officially announced.'",
                "Do NOT mention films already released as the answer.",
                "Do NOT invent production details, co-stars, or release dates not present in the snippets.",
            ]
        ),
        "general": (
            "Answer the user's question using the most relevant and recent information.",
            [
                "Use only the evidence in the sources. Do not invent facts.",
                "Before attributing a movie/project/role to a specific person, verify the snippet EXPLICITLY links that person to that item.",
                "If evidence is insufficient, say clearly that you cannot verify the information.",
            ]
        ),
    }

    intent_desc, extra_rules = intent_rules.get(intent, intent_rules["general"])

    lines = [
        "LIVE WEB SEARCH RESULTS",
        "-" * 40,
        f"QUESTION TYPE: {intent_desc}",
        "",
        "MANDATORY INSTRUCTIONS:",
        "1. Answer strictly based on the real factual information from the sources below.",
        "2. Never invent fake movies, fake names, fake dates, or unverified claims.",
        "3. CRITICAL: DO NOT mention internal tags, bracketed labels (like [moderate], [strong-source], [reference-db]), or source rating words in your response. Answer naturally and cleanly.",
        "4. If the user wrote in Telugu (or Telugu in English script), respond comfortably in the same style with accurate facts.",
        "5. INTENT-SPECIFIC RULES:",
    ]
    for idx, rule in enumerate(extra_rules, ord('a')):
        lines.append(f"   {chr(idx)}) {rule}")
    lines.append("")
    lines.append("SOURCES (best-first):")
    lines.append("")

    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   URL: {r['url']}")
        lines.append(f"   {r['snippet']}")
        lines.append("")
    lines.append("-" * 40)
    lines.append(
        "Provide a direct, complete, and factually accurate answer. "
        "Do not invent details not present in the verified facts."
    )
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Environment Variable Resolver
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Module-level cached Gemini client
# ---------------------------------------------------------------------------
_cached_gemini_client = None
_cached_gemini_key: str | None = None


def _get_gemini_client(api_key: str):
    global _cached_gemini_client, _cached_gemini_key
    if _cached_gemini_client is None or _cached_gemini_key != api_key:
        _cached_gemini_client = genai.Client(api_key=api_key)
        _cached_gemini_key = api_key
    return _cached_gemini_client


def _needs_web_search(message: str) -> bool:
    lower = message.lower()
    return any(phrase in lower for phrase in _WEB_TRIGGER_PHRASES)


def _extract_sources(response) -> list:
    sources: list = []
    try:
        for candidate in (response.candidates or []):
            gm = getattr(candidate, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web:
                    uri   = getattr(web, "uri",   "") or ""
                    title = getattr(web, "title", "") or ""
                    if uri and uri not in [s["url"] for s in sources]:
                        sources.append({"title": title or uri, "url": uri})
    except Exception:
        pass
    return sources[:6]


def _classify_gemini_error(exc: Exception) -> tuple[str, str, bool]:
    """
    Return (error_type, friendly_message, is_retryable_or_recoverable)
    """
    msg = str(exc).lower()
    if "429" in msg or "resource_exhausted" in msg or "quota" in msg:
        return (
            "rate_limit",
            "The primary Gemini API is rate-limited or your daily quota has been reached. "
            "Free-tier quotas reset at midnight Pacific Time.",
            True
        )
    if "503" in msg or "unavailable" in msg or "overload" in msg or "high traffic" in msg:
        return (
            "server_overload",
            "Gemini servers are experiencing high traffic right now. Please wait a moment.",
            True
        )
    if "api_key" in msg or "api key" in msg or "authentication" in msg or "401" in msg or "403" in msg:
        return (
            "auth_error",
            "There is a problem with the Gemini API key. Please verify your configuration.",
            False
        )
    if "not_found" in msg or "404" in msg or ("model" in msg and "not" in msg):
        return (
            "model_error",
            f"The primary model is unavailable: {str(exc)[:120]}",
            True
        )
    if "safety" in msg or "blocked" in msg or "harm" in msg:
        return (
            "safety_block",
            "The response was blocked by safety filters. Please rephrase your message.",
            False
        )
    if "timeout" in msg or "deadline" in msg or "timed out" in msg:
        return (
            "timeout",
            "The request timed out. Please try again.",
            True
        )
    return (
        "api_error",
        f"An error occurred: {str(exc)[:200]}",
        True
    )


# ---------------------------------------------------------------------------
# Fallback Execution via OpenAI-compatible endpoints (Zero Dependencies)
# ---------------------------------------------------------------------------
def _call_openai_compatible(
    endpoint_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    system_instruction: str,
    extra_headers: dict | None = None,
    timeout: int = 30
) -> str:
    full_messages = [{"role": "system", "content": system_instruction}] + messages
    payload = {
        "model": model,
        "messages": full_messages,
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "NOVA-AI-Assistant/2.5.0"
    }
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        choices = res_data.get("choices", [])
        if choices and "message" in choices[0] and "content" in choices[0]["message"]:
            return choices[0]["message"]["content"]
        raise ValueError("Malformed response from fallback provider")


def _execute_fallback(
    message: str,
    history: list[dict],
    language: str,
    search_context: str = "",
    file_context: str = "",
) -> tuple[bool, str, str, str]:
    """
    Attempt fallback provider.
    Returns (success, response_text, provider_name, model_name)
    """
    _ensure_env()
    provider = os.environ.get("FALLBACK_PROVIDER", "groq").lower().strip()
    model_env = os.environ.get("FALLBACK_MODEL", "").strip()

    # Build conversation history for OpenAI-compatible chat format.
    # Cap at last 6 messages (3 exchange pairs) to prevent old unrelated
    # turns from contaminating the current request context.
    recent_history = list(history or [])[-6:] if history else []
    formatted_messages: list[dict] = []
    for m in recent_history:
        role = "assistant" if m.get("role") in ("model", "assistant") else "user"
        content = m.get("content", "").strip()
        # Skip turns that are empty or that look like a search-context block
        # (search context is injected separately below, not from history)
        if content and not content.startswith("LIVE WEB SEARCH RESULTS"):
            formatted_messages.append({"role": role, "content": content})

    # Inject web search context as a separate preceding user-turn so it is
    # clearly separated from conversation history. Label it as evidence, not
    # as the current question, so the model does not confuse the two.
    if search_context:
        formatted_messages.append({
            "role": "user",
            "content": (
                "[SEARCH EVIDENCE — use ONLY this for time-sensitive facts]\n"
                + search_context
                + "\n[END SEARCH EVIDENCE]"
            )
        })
        formatted_messages.append({"role": "assistant", "content": "Understood. I will use only the above search evidence."})

    # Inject uploaded file content as context so fallback provider can
    # answer document-based questions even when Gemini is unavailable.
    if file_context and file_context.strip():
        formatted_messages.append({
            "role": "user",
            "content": (
                "[UPLOADED FILE CONTENT — answer ONLY based on this document]\n"
                "--- FILE START ---\n"
                + file_context[:15000]
                + "\n--- FILE END ---"
            )
        })
        formatted_messages.append({"role": "assistant", "content": "Understood. I will answer based only on the uploaded file content."})

    # Append the actual current user question as the final message
    if message:
        formatted_messages.append({"role": "user", "content": message})

    # Provider 1: Groq (Primary Fallback)
    groq_key = _get_api_key("GROQ_API_KEY")
    if (provider == "groq" or groq_key) and groq_key:
        # Each Groq model has its own per-model TPD (tokens-per-day) quota.
        # A 429 on one model does NOT mean other models are exhausted.
        # Continue the cascade on any per-model failure.
        candidate_models = [
            model_env,
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "groq/compound-mini",
            "qwen/qwen3.6-27b",
        ]
        seen = set()
        models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]
        for g_model in models_to_try:
            try:
                text = _call_openai_compatible(
                    endpoint_url="https://api.groq.com/openai/v1/chat/completions",
                    api_key=groq_key,
                    model=g_model,
                    messages=formatted_messages,
                    system_instruction=SYSTEM_INSTRUCTION
                )
                if text:
                    return True, text, "Groq", g_model
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(f"[NOVA] Groq model {g_model} rate-limited (429) — trying next model", file=sys.stderr)
                else:
                    print(f"[NOVA] Groq model {g_model} HTTP {e.code}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[NOVA] Groq fallback failed with model {g_model}: {e}", file=sys.stderr)

    # Provider 2: OpenRouter
    or_key = _get_api_key("OPENROUTER_API_KEY")
    if (provider == "openrouter" or or_key) and or_key:
        use_model = model_env or "meta-llama/llama-3.3-70b-instruct:free"
        try:
            text = _call_openai_compatible(
                endpoint_url="https://openrouter.ai/api/v1/chat/completions",
                api_key=or_key,
                model=use_model,
                messages=formatted_messages,
                system_instruction=SYSTEM_INSTRUCTION,
                extra_headers={"HTTP-Referer": "http://localhost:3000", "X-Title": "NOVA AI"}
            )
            if text:
                return True, text, "OpenRouter", use_model
        except Exception as e:
            print(f"[NOVA] OpenRouter fallback failed: {e}", file=sys.stderr)

    # Provider 3: OpenAI
    oa_key = _get_api_key("OPENAI_API_KEY")
    if (provider == "openai" or oa_key) and oa_key:
        use_model = model_env or "gpt-4o-mini"
        try:
            text = _call_openai_compatible(
                endpoint_url="https://api.openai.com/v1/chat/completions",
                api_key=oa_key,
                model=use_model,
                messages=formatted_messages,
                system_instruction=SYSTEM_INSTRUCTION
            )
            if text:
                return True, text, "OpenAI", use_model
        except Exception as e:
            print(f"[NOVA] OpenAI fallback failed: {e}", file=sys.stderr)

    # Provider 4: Secondary Gemini Key
    gemini_backup_key = _get_api_key("GEMINI_BACKUP_API_KEY") or _get_api_key("GEMINI_FALLBACK_API_KEY")
    if gemini_backup_key and _GENAI_AVAILABLE:
        try:
            client = genai.Client(api_key=gemini_backup_key)
            gen_contents = []
            for msg in (history or []):
                role = "model" if msg.get("role") in ("assistant", "model") else "user"
                cnt = msg.get("content", "").strip()
                if cnt:
                    gen_contents.append(types.Content(role=role, parts=[types.Part(text=cnt)]))
            if message:
                gen_contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

            use_model = model_env or PRIMARY_MODEL
            resp = client.models.generate_content(
                model=use_model,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
                contents=gen_contents
            )
            if resp.text:
                return True, resp.text, "Gemini (Backup Key)", use_model
        except Exception as e:
            print(f"[NOVA] Gemini secondary key fallback failed: {e}", file=sys.stderr)

    return False, "", "", ""


# ---------------------------------------------------------------------------
# Image Intent Detection (Safety Layer)
# ---------------------------------------------------------------------------
def _is_explicit_ai_image_request(text: str) -> bool:
    if not text or len(text.strip()) < 3:
        return False
    lower = text.strip().lower()
    explicit_ai_patterns = [
        r'\b(?:generate|create|make|draw|render|paint|design)\s+(?:an?\s+)?(?:ai|artificial\s+intelligence)\s+(?:image|photo|picture|pic|artwork|painting|art|avatar|poster|wallpaper|illustration)\b',
        r'\b(?:ai|artificial\s+intelligence)\s+(?:image|photo|picture|pic|artwork|painting|art|avatar|poster|wallpaper)\s+(?:generate|create|make|draw|cheyyi|chesi|ivvu)\b',
        r'\b(?:ai\s+image|ai\s+photo|ai\s+picture|ai\s+art|ai\s+artwork|ai\s+generation)\b',
        r'\bgenerate\s+(?:an?\s+)?(?:ai|artificial\s+intelligence)\b',
        r'\b(?:create|make|generate)\s+(?:an?\s+)?(?:fantasy|surreal|cyberpunk|steampunk|sci-fi)\s+(?:artwork|art|painting|drawing|illustration|scene|image)\b',
        r'\b(?:generate|create)\s+(?:a\s+|an\s+)?(?:cinematic\s+fantasy|digital\s+art|concept\s+art)\b',
        r'\b(?:create\s+artwork|generate\s+artwork|make\s+artwork)\b',
        r'\b(?:ai\s+image\s+generate\s+cheyyi|ai\s+photo\s+generate\s+cheyyi)\b',
        r'\b(?:generate|create|make)\s+(?:an?\s+)?ai\s+picture\b',
        r'\bgenerate\s+a\s+cinematic\s+fantasy\b',
    ]
    return any(re.search(pat, lower) for pat in explicit_ai_patterns)


def _is_web_image_search_request(text: str) -> bool:
    if not text or len(text.strip()) < 3:
        return False
    raw = text.strip()
    lower = raw.lower()
    if raw.endswith("?"):
        if not re.search(r'^(?:can|could|will|please)\s+(?:you\s+)?(?:show|give|find|search|display)\s+(?:me\s+)?(?:photos?|images?|pictures?|pics?)', lower):
            return False
    if re.search(r'^(?:what|who|where|when|why|how|which|whom|whose|is|are|was|were|do|does|did|tell\s+me\s+about|explain|describe\s+the|help\s+me\s+with|summarize|translate|write|solve|calculate|define)\b', lower):
        return False
    if re.search(r'^(?:hi|hello|hey|good\s+morning|good\s+evening|good\s+night|thanks|thank\s+you|ok|okay|bye)\b', lower):
        return False

    image_search_patterns = [
        r'\b(?:photos?|images?|pictures?|pics?|wallpapers?)\b',
        r'^(?:show\s+me|find|search|display|look\s+up|give\s+me)\s+(?:photos?|images?|pictures?|pics?|wallpapers?)\b',
        r'\b(?:image|photo|picture|pic|photos|images|pictures|pics)\s+(?:ivu|ivvandi|chupinchu|chupinchandi|kavali|kavale|chudali)\b',
        r'\b(?:real\s+photos?|real\s+images?|real\s+pictures?)\b',
        r'\b(?:waterfalls|mountains|beaches|rivers|forests|sunset|sunrise|nature|landscape|flowers|animals|birds|temples|monuments)\s+(?:in|at|near|with|and)\s+[\w\s]+',
        r'^(?:waterfalls|mountains|beaches|nature|forests|taj\s+mahal|eiffel\s+tower)\b',
    ]
    return any(re.search(pat, lower) for pat in image_search_patterns)


# ---------------------------------------------------------------------------
# Request Handler
# ---------------------------------------------------------------------------
class handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        print(f"[NOVA] {fmt % args}", file=sys.stderr)

    def do_POST(self):
        """
        POST /api/chat v2.5 (Multi-Provider with Resilient Fallback)
        Outermost try/except guarantees valid JSON is ALWAYS returned.
        """
        language = "en"
        try:
            self._handle_chat()
        except Exception as fatal:
            tb = traceback.format_exc()
            print(f"[NOVA FATAL] Unhandled exception in do_POST:\n{tb}", file=sys.stderr)
            try:
                self._json(200, {
                    "response":            "NOVA encountered an unexpected internal error. Please try again.",
                    "language":            language,
                    "web_search_used":     False,
                    "web_search_fallback": False,
                    "sources":             [],
                    "is_error":            True,
                    "error_type":          "internal_error",
                    "provider":            "error"
                })
            except Exception:
                pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    # -------------------------------------------------------------------------
    # Core Chat Logic
    # -------------------------------------------------------------------------
    def _handle_chat(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return self._json(400, {"error": "Invalid JSON request body."})

        message = (payload.get("message") or "").strip()
        history = payload.get("history") or []
        language = payload.get("language") or "en"
        image_b64 = payload.get("image")
        image_mime = payload.get("image_mime") or "image/jpeg"
        file_context = payload.get("file_context") or ""
        search_mode = payload.get("search_mode") or "auto"

        if not message and not image_b64:
            return self._json(400, {"error": "Message or image is required."})

        # ── 1a. Direct Image to PDF Conversion Detection ─────────────────
        if image_b64 and (not message or any(k in message.lower() for k in ["pdf", "document", "docx", "convert", "save as pdf", "pdf loo", "pdf chesi", "pdf ivu"])):
            try:
                try:
                    from . import generate_document
                except Exception:
                    try:
                        import generate_document
                    except Exception:
                        sys.path.insert(0, str(Path(__file__).parent))
                        import generate_document

                doc_res = generate_document.generate_image_pdf(message or "Image Document", image_b64, image_mime)
                if doc_res and doc_res.get("success"):
                    return self._json(200, {
                        "success": True,
                        "response": f"Successfully converted image to PDF document: **{doc_res.get('filename')}**",
                        "type": "document_generated",
                        "doc_data": doc_res,
                        "filename": doc_res.get("filename"),
                        "file_size": doc_res.get("file_size"),
                        "base64_data": doc_res.get("base64_data"),
                        "mime_type": doc_res.get("mime_type"),
                        "web_search_used": False,
                        "sources": [],
                        "is_error": False,
                    })
            except Exception as _de:
                print(f"[NOVA-CHAT] Direct Image-to-PDF error: {_de}", file=sys.stderr)

        # ── 1b. Server-Side Explicit AI Image Generation Intent Detection ──
        if message and not image_b64 and not file_context and _is_explicit_ai_image_request(message):
            print(f"[NOVA-CHAT] Explicit AI generation intent detected for: {message[:60]!r}", file=sys.stderr)
            try:
                try:
                    from . import generate_image
                except Exception:
                    try:
                        import generate_image
                    except Exception:
                        sys.path.insert(0, str(Path(__file__).parent))
                        import generate_image

                final_prompt, enhance_method, extracted_subject = generate_image._enhance_prompt(message)

                # 1. Try Gemini image generation
                img_result = None
                gemini_key = _get_api_key("GEMINI_API_KEY")
                if gemini_key and getattr(generate_image, "_GENAI_AVAILABLE", False):
                    img_result = generate_image._generate_with_gemini(final_prompt, gemini_key)

                # 2. Try Pollinations fallback
                if not img_result:
                    img_result = generate_image._generate_with_pollinations(final_prompt)

                if img_result:
                    mime = img_result.get("mime", "image/jpeg")
                    provider = img_result.get("provider", "Image Generation")
                    b64 = img_result.get("image_b64", "")
                    url = img_result.get("image_url", "")
                    display_src = f"data:{mime};base64,{b64}" if b64 else url

                    return self._json(200, {
                        "success": True,
                        "response": f"![Generated Image]({display_src})\n\n✦ *{message}*",
                        "type": "image_generated",
                        "image": display_src,
                        "image_b64": b64,
                        "image_url": url,
                        "mime": mime,
                        "provider": provider,
                        "prompt": final_prompt,
                        "original_prompt": message,
                        "method": enhance_method,
                        "enhance_method": enhance_method,
                        "web_search_used": False,
                        "sources": [],
                        "is_error": False,
                    })
            except Exception as _ie:
                print(f"[NOVA-CHAT] Image generation delegation error: {_ie}", file=sys.stderr)

        # ── 1c. Multimodal Vision Analysis & OCR Pipeline ─────────────────
        if image_b64:
            _safe_log(f"[IMAGE ANALYSIS] Image received (base64 chars: {len(image_b64)})")
            _safe_log(f"[IMAGE ANALYSIS] MIME type detected: {image_mime}")

            try:
                image_bytes = base64.b64decode(image_b64)
            except Exception as be:
                _safe_log(f"[IMAGE ANALYSIS] Image decoding failed: {be}")
                return self._json(400, {"error": "Image data is malformed or corrupted."})

            if len(image_bytes) > MAX_IMAGE_BYTES:
                _safe_log(f"[IMAGE ANALYSIS] Image exceeds max size: {len(image_bytes)} bytes")
                return self._json(400, {"error": "Image too large. Maximum size is 10 MB."})

            user_question = (message or "").strip()
            lower_q = user_question.lower()

            # Classify Vision Sub-Intent
            vision_subintent = "general"
            if any(k in lower_q for k in ["extract text", "read text", "what does this image say", "copy text", "extract all text", "read the text", "ocr", "words in this image"]):
                vision_subintent = "ocr"
                specialized_prefix = (
                    "You are an expert OCR and text extraction system. Extract ALL visible text from this image with complete precision.\n"
                    "- Preserve original layout, lines, numbers, headings, code, and punctuation.\n"
                    "- Do NOT alter spelling or omit any words.\n"
                    "- If text is in a table or columnar layout, preserve the alignment.\n\n"
                )
            elif any(k in lower_q for k in ["error", "exception", "traceback", "fix", "bug", "why is this failing", "debug", "crash"]):
                vision_subintent = "error_analysis"
                specialized_prefix = (
                    "You are an expert software engineer and error troubleshooter.\n"
                    "Analyze the error or issue shown in this screenshot:\n"
                    "1. Identify the exact error message, exception type, and failing line/component.\n"
                    "2. Explain the root cause in simple, clear terms.\n"
                    "3. Provide step-by-step practical troubleshooting instructions.\n"
                    "4. Provide the exact corrected and runnable code block to fix the problem.\n\n"
                )
            elif any(k in lower_q for k in ["ui", "ux", "website design", "design", "layout", "user experience", "improve", "landing page", "interface", "app design"]):
                vision_subintent = "ui_analysis"
                specialized_prefix = (
                    "You are a Senior UI/UX Designer and Product Architect.\n"
                    "Perform a thorough, actionable design audit of this UI / website screenshot:\n"
                    "1. Visual Hierarchy & Typography: Readability, contrast, font sizing, and visual flow.\n"
                    "2. Layout & Spacing: Alignment, whitespace balance, clutter, and grid structure.\n"
                    "3. Usability & UX Issues: Call-to-action visibility, navigation clarity, cognitive friction.\n"
                    "4. Accessibility (A11y): Color contrast and element touch targets.\n"
                    "5. Top 3 Concrete Actionable Improvements: Exactly what to change to make it look 10x better.\n\n"
                )
            elif user_question:
                vision_subintent = "qa"
                specialized_prefix = "Analyze this image and answer the user's specific question in detail.\n\n"
            else:
                vision_subintent = "general"
                user_question = DEFAULT_IMAGE_ANALYSIS_PROMPT
                specialized_prefix = "Provide a comprehensive, high-quality description of this image, identifying all key objects, people, setting, text, and visual atmosphere.\n\n"

            lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["en"])
            full_vision_prompt = f"{specialized_prefix}User Request: {user_question}\n\n[Language Requirement: {lang_instruction}]"

            vision_parts = [
                types.Part(text=full_vision_prompt),
                types.Part(inline_data=types.Blob(mime_type=image_mime, data=image_bytes))
            ]

            # Build history if provided
            vision_history = []
            for msg in (history or []):
                r = "model" if msg.get("role") == "assistant" else "user"
                c = msg.get("content", "").strip()
                if c and _GENAI_AVAILABLE:
                    vision_history.append(types.Content(role=r, parts=[types.Part(text=c)]))

            # Candidate Gemini API keys
            candidate_keys = []
            for kn in ["GEMINI_API_KEY", "GEMINI_BACKUP_API_KEY", "GEMINI_FALLBACK_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY_2"]:
                k_val = _get_api_key(kn)
                if k_val and not any(k_val == existing_val for _, existing_val in candidate_keys):
                    candidate_keys.append((kn, k_val))

            vision_success = False
            vision_response_text = ""
            provider_used = "Google Gemini Vision"
            model_used = "gemini-3.6-flash"

            for key_name, api_key in candidate_keys:
                if not _GENAI_AVAILABLE:
                    break
                try:
                    client = genai.Client(api_key=api_key)
                except Exception as ce:
                    _safe_log(f"[IMAGE ANALYSIS] Failed to initialize client for {key_name}: {ce}")
                    continue

                for model_name in VISION_MODELS_CASCADE:
                    _safe_log(f"[IMAGE ANALYSIS] Sending request to Gemini Vision (key: {key_name}, model: {model_name}, subintent: {vision_subintent})")
                    try:
                        resp = client.models.generate_content(
                            model=model_name,
                            config=types.GenerateContentConfig(
                                system_instruction=SYSTEM_INSTRUCTION
                            ),
                            contents=vision_history + [types.Content(role="user", parts=vision_parts)]
                        )
                        if resp and resp.text:
                            vision_success = True
                            vision_response_text = resp.text
                            model_used = model_name
                            provider_used = f"Google Gemini Vision ({model_name})"
                            _safe_log(f"[IMAGE ANALYSIS] Analysis successful (provider: Google Gemini Vision, model: {model_name})")
                            break
                    except Exception as vex:
                        _safe_log(f"[IMAGE ANALYSIS] Primary provider failed ({model_name}): {vex}")
                        _safe_log(f"[IMAGE ANALYSIS] Trying fallback provider / model...")

                if vision_success:
                    break

            # ── Fallback to Groq Vision if Gemini exhausted ──
            if not vision_success:
                groq_key = _get_api_key("GROQ_API_KEY")
                if groq_key:
                    _safe_log("[IMAGE ANALYSIS] Attempting Groq Vision fallback...")
                    for g_model in ["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"]:
                        try:
                            g_payload = {
                                "model": g_model,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": full_vision_prompt},
                                            {
                                                "type": "image_url",
                                                "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}
                                            }
                                        ]
                                    }
                                ],
                                "temperature": 0.2
                            }
                            req = urllib.request.Request(
                                "https://api.groq.com/openai/v1/chat/completions",
                                data=json.dumps(g_payload).encode("utf-8"),
                                headers={
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {groq_key}",
                                    "User-Agent": "NOVA-Vision/3.0"
                                },
                                method="POST"
                            )
                            with urllib.request.urlopen(req, timeout=20) as g_resp:
                                g_data = json.loads(g_resp.read().decode("utf-8"))
                                g_text = g_data["choices"][0]["message"]["content"]
                                if g_text:
                                    vision_success = True
                                    vision_response_text = g_text
                                    provider_used = "Groq Vision"
                                    model_used = g_model
                                    _safe_log(f"[IMAGE ANALYSIS] Groq Vision succeeded with {g_model}")
                                    break
                        except Exception as g_err:
                            _safe_log(f"[IMAGE ANALYSIS] Groq vision model {g_model} failed: {g_err}")

            if vision_success:
                return self._json(200, {
                    "response": vision_response_text,
                    "language": language,
                    "vision_subintent": vision_subintent,
                    "web_search_used": False,
                    "web_search_fallback": False,
                    "sources": [],
                    "is_error": False,
                    "error_type": None,
                    "provider": provider_used,
                    "model": model_used
                })
            else:
                _safe_log("[IMAGE ANALYSIS] All vision providers and fallback models failed")
                return self._json(200, {
                    "response": (
                        "Image analysis is temporarily unavailable. "
                        "The vision service could not process your image at this moment. "
                        "Please try again in a few moments."
                    ),
                    "language": language,
                    "vision_subintent": vision_subintent,
                    "web_search_used": False,
                    "web_search_fallback": False,
                    "sources": [],
                    "is_error": True,
                    "error_type": "vision_unavailable",
                    "provider": "none"
                })

        # ── 2. Check Primary API Key ──────────────────────────────────────
        primary_key = _get_api_key("GEMINI_API_KEY")

        # ── 3. Decide Web Search ──────────────────────────────────────────
        # Skip web search when a file is attached (file requests).
        want_web_search = False
        if not file_context:  # text-only requests only
            if search_mode == "web":
                want_web_search = True
            elif search_mode == "auto" and message:
                want_web_search = _needs_web_search(message)

        # ── 3b. Web Search & Content Preparation ─────────────────────────
        parts: list = []
        try:
            if file_context and file_context.strip():
                prefix = (
                    "The user has uploaded a file. Extracted text:\n"
                    "--- FILE START ---\n"
                    f"{file_context[:15000]}\n"
                    "--- FILE END ---\n\n"
                    "User's question about the file:\n"
                )
                text_content = prefix + (message or "Please analyse this file.")
                if _GENAI_AVAILABLE and types:
                    parts.append(types.Part(text=text_content))
                else:
                    parts.append(text_content)
            elif message:
                if _GENAI_AVAILABLE and types:
                    parts.append(types.Part(text=message))
                else:
                    parts.append(message)
        except Exception as e:
            return self._json(400, {"error": f"Failed to process request content: {e}"})

        # ── 5. Build History for Gemini ───────────────────────────────────
        chat_history: list = []
        try:
            for msg in (history or []):
                role = "model" if msg.get("role") == "assistant" else "user"
                content = msg.get("content", "").strip()
                if content and _GENAI_AVAILABLE:
                    chat_history.append(types.Content(
                        role=role,
                        parts=[types.Part(text=content)]
                    ))
        except Exception:
            chat_history = []

        # ── 6. Try Primary Provider (Gemini) ──────────────────────────────
        primary_succeeded  = False
        primary_response   = None
        grounding_used     = False
        grounding_fallback = False
        last_error_type    = "no_api_key"
        last_error_msg     = "Gemini API key is not configured. Set GEMINI_API_KEY in vercel_deploy/.env"
        model_used         = PRIMARY_MODEL
        independent_search_results: list[dict] = []
        independent_search_context: str = ""

        gemini_candidate_models = [
            PRIMARY_MODEL,
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
        ]
        # Deduplicate
        seen_gmodels = set()
        gemini_models_to_try = [m for m in gemini_candidate_models if m and not (m in seen_gmodels or seen_gmodels.add(m))]

        if primary_key and _GENAI_AVAILABLE:
            try:
                client = _get_gemini_client(primary_key)
                contents = chat_history + [types.Content(role="user", parts=parts)]

                if want_web_search:
                    # Attempt 1: Fast Direct Google Search grounding
                    hit_quota = False
                    for g_m in gemini_models_to_try:
                        try:
                            primary_response = client.models.generate_content(
                                model=g_m,
                                config=types.GenerateContentConfig(
                                    system_instruction=SYSTEM_INSTRUCTION,
                                    tools=[types.Tool(google_search=types.GoogleSearch())],
                                ),
                                contents=contents,
                            )
                            if primary_response and primary_response.text:
                                grounding_used     = True
                                grounding_fallback = False
                                primary_succeeded  = True
                                model_used         = g_m
                                break
                        except Exception as g_exc:
                            _g_msg = str(g_exc).lower()
                            if any(k in _g_msg for k in ("429", "resource_exhausted", "quota")):
                                hit_quota = True
                                print(f"[NOVA] Gemini ({g_m}) quota exhausted (429)", file=sys.stderr)
                                break
                            print(f"[NOVA] Gemini ({g_m}) with Google Search failed: {g_exc}", file=sys.stderr)

                    # Attempt 2: If direct Google Search tool failed (and not full quota block), try independent search context
                    if not primary_succeeded and not hit_quota:
                        grounding_used     = False
                        grounding_fallback = True
                        search_intent = _classify_search_intent(message)
                        normalized_query = _normalize_search_query(message, search_intent)
                        independent_search_results = _do_web_search(normalized_query, intent=search_intent)
                        if independent_search_results:
                            independent_search_context = _format_search_context(
                                independent_search_results, message, intent=search_intent
                            )

                        fallback_parts = []
                        if independent_search_context:
                            fallback_parts.append(types.Part(text=independent_search_context + "\n\nUser question: " + message))
                        else:
                            fallback_parts.append(types.Part(text=message))

                        for g_m in gemini_models_to_try:
                            try:
                                primary_response = client.models.generate_content(
                                    model=g_m,
                                    config=types.GenerateContentConfig(
                                        system_instruction=SYSTEM_INSTRUCTION,
                                    ),
                                    contents=chat_history + [
                                        types.Content(role="user", parts=fallback_parts)
                                    ],
                                )
                                if primary_response and primary_response.text:
                                    primary_succeeded = True
                                    model_used = g_m
                                    break
                            except Exception as g_exc:
                                _g_msg = str(g_exc).lower()
                                if any(k in _g_msg for k in ("429", "resource_exhausted", "quota")):
                                    break
                                print(f"[NOVA] Gemini ({g_m}) with independent search context failed: {g_exc}", file=sys.stderr)
                else:
                    # Direct AI generation across candidate models
                    for g_m in gemini_models_to_try:
                        try:
                            primary_response = client.models.generate_content(
                                model=g_m,
                                config=types.GenerateContentConfig(
                                    system_instruction=SYSTEM_INSTRUCTION,
                                ),
                                contents=contents,
                            )
                            if primary_response and primary_response.text:
                                primary_succeeded = True
                                model_used = g_m
                                break
                        except Exception as exc:
                            _g_msg = str(exc).lower()
                            if any(k in _g_msg for k in ("429", "resource_exhausted", "quota")):
                                break
                            print(f"[NOVA] Gemini ({g_m}) direct generation failed: {exc}", file=sys.stderr)

            except Exception as exc:
                err_type, err_msg, is_recoverable = _classify_gemini_error(exc)
                last_error_type = err_type
                last_error_msg  = err_msg
                print(f"[NOVA] Primary provider initialization failed ({err_type}): {exc}", file=sys.stderr)

        # ── 7. Fallback Provider Execution ────────────────────────────────
        if not primary_succeeded:
            if want_web_search and not independent_search_context and message:
                search_intent = _classify_search_intent(message)
                normalized_query = _normalize_search_query(message, search_intent)
                try:
                    independent_search_results = _do_web_search(normalized_query, intent=search_intent)
                    if independent_search_results:
                        independent_search_context = _format_search_context(
                            independent_search_results, message, intent=search_intent
                        )
                except Exception as _fe:
                    print(f"[NOVA] Fallback search fetch error: {_fe}", file=sys.stderr)

            fb_ok, fb_text, fb_provider, fb_model = _execute_fallback(
                message=message,
                history=history,
                language=language,
                search_context=independent_search_context,
                file_context=file_context or "",
            )
            if fb_ok and fb_text:
                fallback_sources = [
                    {"title": r["title"], "url": r["url"]}
                    for r in independent_search_results
                ] if independent_search_results else []
                return self._json(200, {
                    "response":            fb_text,
                    "language":            language,
                    "web_search_used":     bool(independent_search_results),
                    "web_search_fallback": want_web_search and not bool(independent_search_results),
                    "sources":             fallback_sources,
                    "is_error":            False,
                    "error_type":          None,
                    "provider":            fb_provider,
                    "model":               fb_model,
                    "fallback_used":       True
                })

            # No fallback configured or fallback also exhausted
            return self._json(200, {
                "response":            last_error_msg,
                "language":            language,
                "web_search_used":     False,
                "web_search_fallback": grounding_fallback,
                "sources":             [],
                "is_error":            True,
                "error_type":          last_error_type,
                "provider":            "none"
            })

        # ── 8. Return Primary Response ────────────────────────────────────
        try:
            response_text = primary_response.text
            if not response_text:
                raise ValueError("Empty response text from Gemini")
        except Exception as e:
            return self._json(200, {
                "response":            "Gemini returned an empty response. Please try again.",
                "language":            language,
                "web_search_used":     False,
                "web_search_fallback": grounding_fallback,
                "sources":             [],
                "is_error":            True,
                "error_type":          "empty_response",
            })

        # Gemini grounding sources take priority; fall back to independent search sources
        gemini_sources = _extract_sources(primary_response) if grounding_used else []
        if not gemini_sources and independent_search_results:
            gemini_sources = [{"title": r["title"], "url": r["url"]} for r in independent_search_results]

        return self._json(200, {
            "response":            response_text,
            "language":            language,
            "web_search_used":     grounding_used or bool(independent_search_results),
            "web_search_fallback": grounding_fallback,
            "sources":             gemini_sources,
            "is_error":            False,
            "error_type":          None,
            "provider":            "Google Gemini",
            "model":               model_used
        })

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age",       "86400")

    def _json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)
