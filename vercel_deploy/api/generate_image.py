"""
NOVA Web API - /api/generate-image  v2.2
Image Generation with robust subject-preserving prompt enhancement.

Pipeline:
  RAW PROMPT
      -> TYPO FIX -> SUBJECT EXTRACTION -> KNOWN-SUBJECT LOOKUP
      -> IF KNOWN: IDENTITY ENRICHMENT + USER SCENE/STYLE PRESERVED
      -> IF UNKNOWN: GROQ LLM ENHANCEMENT (with subject-preservation validation)
      -> SAFE FALLBACK PROMPT (always contains original subject)
      -> PROVIDER 1: Gemini image generation (if available)
      -> PROVIDER 2: Pollinations.ai (retry + exponential backoff)
      -> CLEAR ERROR RESPONSE

Response:
  { success: true,  image_b64, mime, provider, prompt, original_prompt, enhance_method }
  { success: false, error }
"""

import os
import sys
import json
import re
import time
import base64
import hashlib
import traceback
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler

from dotenv import load_dotenv

_GENAI_AVAILABLE = False


# ===========================================================================
# CONSTANTS -- defined before any functions to avoid NameError
# ===========================================================================

# Romanized Telugu / Hindi filler/action words (command-only, not visual)
# NOTE: 'chesi' is removed from standalone list because it can appear in
# scene descriptions. Only multi-word forms 'chesi ivu' / 'chesi ivvu' are stripped.
# 'generate', 'create', 'make', 'draw' are always command words (never visual
# descriptors) so they appear here for mid-sentence Telugu-English stripping,
# AND in _COMMAND_PREFIX for prefix-stripping of pure-English prompts.
_FILLER_NOISE = re.compile(
    r'\b(?:'
    r'naku|naaku|nannu|meeru|oka|okati|please|andi|'
    r'cheyyi|cheseyyi|cheyandi|chupinchu|chupinchandi|chesivvu|'
    r'chesi\s+ivu|chesi\s+ivvu|ivvu|ivvandi|'
    r'generate|create|make|draw|'
    r'chudataneki|choodataniku|choodali|'
    r'diggaja|ga\s+undali|vundali'
    r')\b',
    re.IGNORECASE,
)

# Image/visual noun command words — stripped from prompt
# NOTE: 'poster' is NOT included here — it is a valid visual style word.
_VISUAL_FILLER = re.compile(
    r'\b(?:photos?|images?|pictures?|pics?|okati|wallpaper)\b',
    re.IGNORECASE,
)

# English image-request command words to strip from the start of a prompt
# (only at the beginning of the sentence, not mid-sentence)
_COMMAND_PREFIX = re.compile(
    r'^\s*(?:generate|create|make|draw|show\s+me|give\s+me|'
    r'produce|render|design)\s+(?:a\s+|an\s+|me\s+(?:a\s+|an\s+)?)?',
    re.IGNORECASE,
)

# Telugu quality/style adverbs -> English equivalents
_STYLE_MAP = [
    (re.compile(r'\bstylish\s*ga\b',      re.IGNORECASE), 'stylish, fashionable'),
    (re.compile(r'\bbeautiful\s*ga\b',    re.IGNORECASE), 'beautiful, elegant'),
    (re.compile(r'\bcinematic\s*ga\b',    re.IGNORECASE), 'cinematic'),
    (re.compile(r'\brealistic\s*ga\b',    re.IGNORECASE), 'photorealistic'),
    (re.compile(r'\bcute\s*ga\b',         re.IGNORECASE), 'cute, adorable'),
    (re.compile(r'\bcool\s*ga\b',         re.IGNORECASE), 'cool'),
    (re.compile(r'\bbold\s*ga\b',         re.IGNORECASE), 'bold, striking'),
    (re.compile(r'\bprofessional\s*ga\b', re.IGNORECASE), 'professional, polished'),
    (re.compile(r'\bartistic\s*ga\b',     re.IGNORECASE), 'artistic'),
    (re.compile(r'\btraditional\s*ga\b',  re.IGNORECASE), 'traditional Indian style'),
    (re.compile(r'\bmodern\s*ga\b',       re.IGNORECASE), 'modern, contemporary'),
]

# Detect Romanized Telugu-English mixing (signals non-English cleanup needed)
_TE_MARKER = re.compile(
    r'\b(?:naku|naaku|nannu|meeru|oka\b|cheyyi|chesi|ivvu|chudataneki|'
    r'vundali|madhyalo|stylish\s+ga|beautiful\s+ga|cinematic\s+ga|realistic\s+ga)\b',
    re.IGNORECASE,
)

# Romanized Telugu scene/relationship words that have visual meaning
# These should be preserved or translated, not stripped
_TE_SCENE_MAP = [
    (re.compile(r'\bmadhyalo\b', re.IGNORECASE), 'in the middle of'),
    (re.compile(r'\bpakkana\b',  re.IGNORECASE), 'beside'),
    (re.compile(r'\bvaetiki\b',  re.IGNORECASE), 'behind'),
    (re.compile(r'\bmuందు\b',   re.IGNORECASE), 'in front of'),
]

# Common typo corrections
_TYPO_MAP = [
    (re.compile(r'\bpictuer\b',    re.IGNORECASE), 'picture'),
    (re.compile(r'\bimge\b',       re.IGNORECASE), 'image'),
    (re.compile(r'\bphotu\b',      re.IGNORECASE), 'photo'),
    (re.compile(r'\bgenerete\b',   re.IGNORECASE), 'generate'),
    (re.compile(r'\bcreat\b',      re.IGNORECASE), 'create'),
    (re.compile(r'\bbeautifull\b', re.IGNORECASE), 'beautiful'),
    (re.compile(r'\bcolorfull\b',  re.IGNORECASE), 'colorful'),
    (re.compile(r'\bportriat\b',   re.IGNORECASE), 'portrait'),
    (re.compile(r'\blandscpae\b',  re.IGNORECASE), 'landscape'),
]

_DEFAULT_QUALITY = (
    'highly detailed, 8K resolution, cinematic lighting, sharp focus, vibrant colors'
)

# ---------------------------------------------------------------------------
# Known-Subject Enrichment Table
# Each entry: (match_key_lowercase, identity_description)
#
# The identity_description contains ONLY the subject's core visual identity.
# It does NOT include a background/scene/setting — those come from the user's
# original request and are appended separately.
# ---------------------------------------------------------------------------
_KNOWN_SUBJECTS: list[tuple[str, str]] = [
    # Hindu deities — identity only (no scene/background)
    ('lord krishna',
     'Lord Krishna, youthful Hindu deity, blue complexion, peacock feather crown, '
     'holding a flute, traditional yellow silk dhoti, Vaijayanti flower garland, '
     'golden ornaments, serene divine smile'),
    ('krishna',
     'Lord Krishna, youthful Hindu deity, blue complexion, peacock feather crown, '
     'holding a flute, traditional yellow silk dhoti, golden ornaments, '
     'serene divine expression'),
    ('lord rama',
     'Lord Rama, Hindu deity, blue complexion, golden crown, bow and sacred arrow, '
     'royal warrior attire, serene noble expression'),
    ('lord shiva',
     'Lord Shiva, Hindu deity, pale blue skin, third eye on forehead, '
     'crescent moon in matted hair, sacred serpent, trident, tiger skin, '
     'Rudraksha beads'),
    ('lord ganesha',
     'Lord Ganesha, Hindu deity, elephant head, large kind eyes, four arms, '
     'orange-red complexion, modak sweet, lotus flowers'),
    ('lord hanuman',
     'Lord Hanuman, Hindu deity, powerful monkey devotee, orange complexion, '
     'carrying a gada mace, devotional orange attire, fierce devoted expression'),
    ('goddess durga',
     'Goddess Durga, Hindu deity, ten arms holding divine weapons, riding a lion, '
     'radiant golden complexion, fierce yet compassionate expression, lotus throne'),
    ('goddess lakshmi',
     'Goddess Lakshmi, Hindu deity, serene beautiful form, golden complexion, '
     'seated on lotus, holding lotus flowers, gold coins flowing, red and gold saree'),
    ('lord vishnu',
     'Lord Vishnu, Hindu deity, blue complexion, four arms holding conch chakra club lotus, '
     'golden crown, divine aura'),
    # South Indian cinema — identity only
    ('allu arjun',
     'Stylized cinematic portrait of Allu Arjun, Tollywood superstar, '
     'signature stylish look, confident charismatic expression'),
    ('pawan kalyan',
     'Stylized cinematic portrait of Pawan Kalyan, Tollywood actor-politician, '
     'strong confident expression'),
    ('mahesh babu',
     'Stylized cinematic portrait of Mahesh Babu, Tollywood superstar, '
     'charming confident smile'),
    ('ram charan',
     'Stylized cinematic portrait of Ram Charan, Tollywood hero, '
     'athletic energetic build'),
    ('ntr',
     'Stylized cinematic portrait of Jr. NTR, Tollywood star, '
     'intense powerful expression'),
    ('vijay',
     'Stylized cinematic portrait of Vijay Thalapathy, Tamil superstar, '
     'energetic mass-hero pose'),
    ('ajith',
     'Stylized cinematic portrait of Ajith Kumar, Tamil actor, '
     'cool confident expression'),
    ('rajinikanth',
     'Stylized cinematic portrait of Rajinikanth, iconic Tamil superstar, '
     'legendary signature style, dramatic entrance pose'),
    ('kamal haasan',
     'Stylized cinematic portrait of Kamal Haasan, legendary Tamil actor, '
     'expressive face'),
    # Bollywood
    ('shahrukh khan',
     'Stylized cinematic portrait of Shah Rukh Khan, iconic Bollywood star, '
     'signature charming expression'),
    ('salman khan',
     'Stylized cinematic portrait of Salman Khan, Bollywood superstar, '
     'powerful confident expression'),
    # Cricket
    ('virat kohli',
     'Stylized sports portrait of Virat Kohli, Indian cricket captain, '
     'intense focused expression, cricket jersey'),
    ('ms dhoni',
     'Stylized sports portrait of MS Dhoni, legendary Indian cricket captain, '
     'calm composed expression, cricket gear'),
]


# ===========================================================================
# ENVIRONMENT HELPERS
# ===========================================================================
_env_loaded = False


def _ensure_env():
    global _env_loaded
    if _env_loaded:
        return
    here = Path(__file__).resolve().parent
    candidates = [here, here.parent, Path.cwd(), here.parent.parent]
    for directory in candidates:
        for filename in (".env.local", ".env"):
            env_path = directory / filename
            if env_path.is_file():
                load_dotenv(dotenv_path=env_path, override=False)
    _env_loaded = True


def _get_api_key(var_name: str) -> str | None:
    _ensure_env()
    key = os.environ.get(var_name, "")
    placeholders = {
        "your_gemini_api_key_here", "your_api_key", "your_api_key_here",
        "your_gemini_api_key", "your_groq_api_key_here",
    }
    if key and key.strip() and key.strip().lower() not in placeholders:
        return key.strip()
    return None


# ===========================================================================
# GEMINI CLIENT CACHE
# ===========================================================================
_cached_gemini_client = None
_cached_gemini_key    = None


def _get_gemini_client(api_key: str):
    global _cached_gemini_client, _cached_gemini_key
    if not _GENAI_AVAILABLE:
        raise RuntimeError("google-genai SDK not installed")
    if _cached_gemini_client is None or _cached_gemini_key != api_key:
        _cached_gemini_client = genai.Client(api_key=api_key)
        _cached_gemini_key    = api_key
    return _cached_gemini_client


# ===========================================================================
# STAGE 1A -- TYPO FIXING
# ===========================================================================

def _fix_typos(text: str) -> str:
    for pattern, replacement in _TYPO_MAP:
        text = pattern.sub(replacement, text)
    return text


# ===========================================================================
# STAGE 1B -- SUBJECT EXTRACTION
# ===========================================================================

def _extract_primary_subject(raw: str) -> str:
    """
    Strip command/filler language and return the core visual subject (lowercase).

    Preserves:
    - Visual nouns (mountains, river, robot, city)
    - Place names (Hyderabad, Mumbai)
    - Style/mood words (cyberpunk, realistic, night)
    - Meaningful Telugu scene words (madhyalo -> 'in the middle of')

    Removes:
    - Request/filler Telugu words (naku, oka, cheyyi, etc.)
    - Visual command nouns (image, photo, picture)
    - English command prefixes (generate, create, make, draw)
    """
    working = _fix_typos(raw)
    # Translate meaningful Telugu scene words before stripping fillers
    for pattern, replacement in _TE_SCENE_MAP:
        working = pattern.sub(replacement, working)
    # Strip English command prefix FIRST (e.g. 'generate a', 'create an', 'draw')
    working = _COMMAND_PREFIX.sub('', working)
    # Strip filler noise and visual command nouns
    working = _FILLER_NOISE.sub(' ', working)
    working = _VISUAL_FILLER.sub(' ', working)
    # Clean whitespace and punctuation
    working = re.sub(r'\s{2,}', ' ', working).strip().strip(',.;')
    return working.lower()


def _lookup_known_subject(subject_lower: str) -> tuple[str, str] | None:
    """
    Return (matched_key, identity_description) if subject matches a known entity.
    Uses word-boundary matching to prevent accidental substring matches.
    Returns None if no match.
    """
    for key, description in _KNOWN_SUBJECTS:
        pattern = r'\b' + re.escape(key) + r'\b'
        if re.search(pattern, subject_lower, re.IGNORECASE):
            return key, description
    return None


# ===========================================================================
# STAGE 1C -- USER SCENE EXTRACTION
# ===========================================================================

def _extract_user_scene(raw: str, known_key: str) -> str:
    """
    Given a raw prompt and the matched known-subject key, extract the user's
    requested scene, environment, style, mood, and composition -- everything
    that is NOT the subject identity.

    Returns a clean string of user modifiers, or '' if none.

    Example:
      raw       = "Lord Krishna standing in cyberpunk Hyderabad at night"
      known_key = "lord krishna"
      returns   = "standing in cyberpunk Hyderabad at night"
    """
    working = _fix_typos(raw)

    # Translate Telugu scene words
    for pattern, replacement in _TE_SCENE_MAP:
        working = pattern.sub(replacement, working)

    # Remove the matched subject key (case-insensitive, word-boundary)
    key_pattern = r'\b' + re.escape(known_key) + r'\b'
    working = re.sub(key_pattern, '', working, flags=re.IGNORECASE)

    # Strip English command prefix FIRST
    working = _COMMAND_PREFIX.sub('', working)

    # Remove filler command words
    working = _FILLER_NOISE.sub(' ', working)
    working = _VISUAL_FILLER.sub(' ', working)

    # Normalise whitespace and punctuation
    working = re.sub(r'\s{2,}', ' ', working).strip().strip(',.;:')

    # Collect Telugu style modifiers and translate them
    style_parts: list[str] = []
    for pattern, replacement in _STYLE_MAP:
        if pattern.search(working):
            style_parts.append(replacement)
            working = pattern.sub(' ', working)

    working = re.sub(r'\s{2,}', ' ', working).strip().strip(',.;:')

    # Recombine: scene description + translated style modifiers
    parts = [p.strip() for p in [working] + style_parts if p.strip()]
    return ', '.join(parts)


# ===========================================================================
# STAGE 1D -- SUBJECT VALIDATION
# ===========================================================================

def _normalize_for_stem(word: str) -> list[str]:
    """
    Return a list of stem variants for a word to support soft matching.
    Handles common English plural forms without external libraries.
    """
    wl = word.lower()
    variants = [wl]
    # -ies -> -y  (cities -> city, countries -> country)
    if wl.endswith('ies') and len(wl) > 4:
        variants.append(wl[:-3] + 'y')
    # -es -> remove -es (beaches -> beach)
    elif wl.endswith('es') and len(wl) > 4:
        variants.append(wl[:-2])
    # -s -> remove -s (mountains -> mountain, robots -> robot)
    elif wl.endswith('s') and len(wl) > 4:
        variants.append(wl[:-1])
    return variants


def _validate_subject_preserved(extracted_subject: str, enhanced_prompt: str) -> bool:
    """
    Validate that the key subject is preserved in the enhanced prompt.

    Two-tier check:
    1. STRICT named-entity check: if the subject contains a known name token,
       ALL name tokens must appear in the enhanced prompt verbatim.
       A generic replacement ('a divine person') must FAIL.
    2. SOFT word-coverage check: >= 60% of meaningful subject words must appear
       (with stem normalization: 'mountains' matches 'mountain', 'cities' matches 'city').
    """
    if not extracted_subject or not enhanced_prompt:
        return False

    enh_lower = enhanced_prompt.lower()

    # Known name tokens used for strict entity validation
    _NAME_TOKENS = {
        # Deities
        'krishna', 'rama', 'shiva', 'ganesha', 'hanuman', 'durga',
        'lakshmi', 'vishnu', 'brahma', 'saraswati', 'parvati', 'kali',
        # South Indian actors
        'arjun', 'pawan', 'kalyan', 'mahesh', 'babu', 'charan', 'ntr',
        'vijay', 'ajith', 'rajinikanth', 'kamal', 'haasan',
        # Bollywood
        'shahrukh', 'salman', 'amitabh', 'bachchan', 'deepika', 'katrina',
        # Cricket
        'kohli', 'dhoni', 'tendulkar', 'rohit', 'sharma',
    }

    subj_words = extracted_subject.split()
    name_words = [w for w in subj_words if w.lower() in _NAME_TOKENS]

    # -- Tier 1: strict named-entity check --
    if name_words:
        all_name_present = all(n.lower() in enh_lower for n in name_words)
        if not all_name_present:
            return False

    # -- Tier 2: soft word-coverage check --
    _STOP = {'the', 'and', 'for', 'with', 'from', 'that', 'this',
             'are', 'was', 'has', 'have', 'had', 'its', 'in', 'of', 'a', 'an'}
    words = [w for w in subj_words if len(w) >= 3 and w.lower() not in _STOP]
    if not words:
        return True

    def _word_in(w: str) -> bool:
        for variant in _normalize_for_stem(w):
            if variant in enh_lower:
                return True
        return False

    matched = sum(1 for w in words if _word_in(w))
    return (matched / len(words)) >= 0.60


# ===========================================================================
# STAGE 1E -- GROQ LLM ENHANCEMENT
# ===========================================================================

_ENHANCER_SYSTEM = """\
You are an AI image prompt engineer. Convert the user's image request into a
detailed English visual prompt for an AI image generator.

CRITICAL RULES:
1. Output ONLY the final image prompt. No labels, no explanation, no quotes, no markdown.
2. PRESERVE THE PRIMARY SUBJECT EXACTLY. If the user mentions "Lord Krishna", your output
   MUST contain the words "Lord Krishna". If they mention "Allu Arjun", output MUST
   contain "Allu Arjun". NEVER replace a named deity, person, or place with a generic
   description like "a woman", "a man", "a person", or "an actor".
3. For Hindu deities, expand with correct iconography, colors, attributes, setting.
4. For celebrities, keep their exact name. Add stylized portrait description.
5. Strip Romanized Telugu/Hindi filler words ONLY: naku, naaku, oka, okati, cheyyi,
   chesi ivu, chupinchu, generate, create, image, photo, picture, ivvu.
6. Fix typos: pictuer->picture, imge->image, photu->photo.
7. Preserve style/mood words: cyberpunk, realistic, stylish, beautiful, cinematic,
   black and white, night, dark, bright, vintage, futuristic, minimal, dramatic.
8. Preserve place names: Hyderabad, Mumbai, mountains, river, beach, forest, stadium.
9. Preserve composition/pose words: standing, sitting, running, portrait, poster, close-up.
10. Do NOT start the prompt with command words like "generate", "create", "make", "draw".
11. Always append: highly detailed, 8K resolution, cinematic lighting, sharp focus.
12. Maximum 250 tokens output.

Examples:
  Input:  "naku Lord Krishna image generate chesi ivu"
  Output: Lord Krishna, youthful Hindu deity, blue complexion, peacock feather crown, holding a flute, traditional yellow silk dhoti, golden ornaments, serene divine smile, Vrindavan background, lotus flowers, soft golden divine light, highly detailed devotional Indian artwork, cinematic lighting, 8K resolution

  Input:  "generate a futuristic robot"
  Output: A futuristic humanoid robot with advanced metallic armor, glowing blue energy cores, sleek chrome surfaces, cinematic sci-fi environment, dramatic studio lighting, highly detailed, photorealistic, 8K resolution

  Input:  "naku oka cyberpunk Hyderabad city image create cheyyi"
  Output: Cyberpunk cityscape of Hyderabad, neon-lit streets, futuristic Charminar with holographic projections, dense rain, flying vehicles, dark moody atmosphere, ultra-detailed digital art, cinematic wide shot, 8K resolution

  Input:  "Allu Arjun stylish image generate cheyyi"
  Output: Stylized cinematic portrait of Allu Arjun, fashionable designer outfit, confident charismatic pose, dramatic studio lighting, movie-poster aesthetic, vibrant colors, highly detailed, 8K resolution

  Input:  "mountains madhyalo river image generate cheyyi"
  Output: Majestic mountain range with a crystal-clear river flowing through the valley, misty peaks, lush green forest, golden morning light, highly detailed landscape photography, cinematic composition, 8K resolution
"""


def _enhance_prompt_with_groq(raw: str, groq_key: str) -> str | None:
    """
    Use Groq LLM to enhance an UNKNOWN-subject prompt.
    Uses the exact same verified model cascade as chat.py _execute_fallback().
    Returns the enhanced prompt string, or None if all models fail.
    """
    models_to_try = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "groq/compound-mini",
        "qwen/qwen3.6-27b",
    ]
    payload = {
        "messages": [
            {"role": "system", "content": _ENHANCER_SYSTEM},
            {"role": "user",   "content": f"Convert this image request into a detailed visual prompt: {raw}"},
        ],
        "max_tokens":  280,
        "temperature": 0.25,
    }
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {groq_key}",
        "User-Agent":    "NOVA-AI-Assistant/2.5.0",
    }
    for model in models_to_try:
        payload["model"] = model
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                enhanced = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if enhanced and len(enhanced) > 10:
                    return enhanced
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[NOVA-IMGGEN] Groq {model} 429 -- trying next", file=sys.stderr)
                time.sleep(0.5)
            else:
                print(f"[NOVA-IMGGEN] Groq {model} HTTP {e.code}", file=sys.stderr)
        except Exception as exc:
            print(f"[NOVA-IMGGEN] Groq {model} failed: {exc}", file=sys.stderr)
    return None


# ===========================================================================
# STAGE 1F -- RULES-BASED FALLBACK (English normalization)
# ===========================================================================

def _fallback_normalize(raw: str) -> str:
    """
    Rules-based fallback for unknown subjects when Groq is unavailable.
    Also used to clean up English prompts:
    - Strips command prefix (generate, create, make, draw)
    - Capitalizes first letter
    - Appends quality suffix if short
    """
    if not raw:
        return raw
    working = _fix_typos(raw)

    if not _TE_MARKER.search(working):
        # Pure English prompt — strip command prefix and add quality
        cleaned = _COMMAND_PREFIX.sub('', working).strip().strip(',.;')
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        if len(cleaned) < 80:
            cleaned = cleaned + ', ' + _DEFAULT_QUALITY
        return cleaned

    # Telugu-English mixed prompt — apply style translations then strip fillers
    for pattern, replacement in _TE_SCENE_MAP:
        working = pattern.sub(replacement, working)

    style_parts: list[str] = []
    for pattern, replacement in _STYLE_MAP:
        if pattern.search(working):
            style_parts.append(replacement)
            working = pattern.sub(' ', working)

    working = _FILLER_NOISE.sub(' ', working)
    working = _VISUAL_FILLER.sub(' ', working)
    working = _COMMAND_PREFIX.sub('', working)
    working = re.sub(r'\s{2,}', ' ', working).strip().strip(',.;')

    if not working:
        working = raw

    parts = [working]
    if style_parts:
        parts.append(', '.join(style_parts))
    full = ', '.join(p.strip() for p in parts if p.strip())

    if _DEFAULT_QUALITY.split(',')[0].strip().lower() not in full.lower():
        full = full + ', ' + _DEFAULT_QUALITY
    return full


ENTITY_REGISTRY = [
    {
        "canonical": "Allu Arjun",
        "description": "Tollywood superstar actor Allu Arjun with signature groomed beard, coiffed stylish hair, and sharp charismatic facial features in modern stylish outfit",
        "aliases": ["allu arjun", "alluarjun", "allu arjun di", "allu arjun photo", "stylish star", "icon star", "pushpa"]
    },
    {
        "canonical": "Virat Kohli",
        "description": "Indian cricket legend Virat Kohli with signature fade haircut, sharp trimmed beard, intense focused eyes, and athletic build in modern casual jacket",
        "aliases": ["virat kohli", "viratkohli", "virtkohli", "virat koli", "viratkoli", "king kohli", "kohli", "virat"]
    },
    {
        "canonical": "MS Dhoni",
        "description": "Indian cricket legend MS Dhoni with calm iconic smile, short classic hairstyle, and athletic posture",
        "aliases": ["ms dhoni", "msdhoni", "dhoni", "mahi", "mahendra singh dhoni"]
    },
    {
        "canonical": "Rohit Sharma",
        "description": "Indian cricket captain Rohit Sharma with signature trimmed beard and recognizable features in modern athletic attire",
        "aliases": ["rohit sharma", "rohitsharma", "hitman", "rohit"]
    },
    {
        "canonical": "Mahesh Babu",
        "description": "Tollywood superstar Mahesh Babu with charming handsome face, fair complexion, and stylish youthful hair",
        "aliases": ["mahesh babu", "maheshbabu", "prince mahesh", "superstar mahesh", "mahesh"]
    },
    {
        "canonical": "Prabhas",
        "description": "Pan-Indian superstar actor Prabhas with tall imposing build, signature intense gaze, and rugged masculine styling",
        "aliases": ["prabhas", "darling prabhas", "rebel star prabhas", "bahubali"]
    },
    {
        "canonical": "Ram Charan",
        "description": "Global star actor Ram Charan with sharp athletic facial structure, styled hair, and charismatic smile",
        "aliases": ["ram charan", "ramcharan", "mega power star", "charan"]
    },
    {
        "canonical": "Jr NTR",
        "description": "Tollywood superstar Jr. NTR with expressive energetic facial features, groomed beard, and powerful stance",
        "aliases": ["jr ntr", "jrntr", "junior ntr", "ntr", "tarak"]
    },
    {
        "canonical": "Pawan Kalyan",
        "description": "Power star actor-politician Pawan Kalyan with intense charismatic gaze, trademark hairstyle, and traditional styling",
        "aliases": ["pawan kalyan", "pawankalyan", "power star", "kalyan babu"]
    },
    {
        "canonical": "Shah Rukh Khan",
        "description": "Bollywood megastar Shah Rukh Khan with iconic dimpled smile, charismatic expressive eyes, and classic styled flowy hair",
        "aliases": ["shah rukh khan", "shahrukh khan", "shahrukhkhan", "srk", "king khan"]
    },
    {
        "canonical": "Salman Khan",
        "description": "Bollywood superstar Salman Khan with strong muscular jawline, short trimmed hair, and trademark confident posture",
        "aliases": ["salman khan", "salmankhan", "bhaijaan", "salman"]
    },
    {
        "canonical": "Amitabh Bachchan",
        "description": "Indian film legend Amitabh Bachchan with distinguished grey French beard, tall stature, and royal charismatic presence",
        "aliases": ["amitabh bachchan", "amitabhbachchan", "amitabh", "big b", "bachchan"]
    },
    {
        "canonical": "Deepika Padukone",
        "description": "Indian actress Deepika Padukone with beautiful expressive eyes, elegant dimpled smile, and graceful posture",
        "aliases": ["deepika padukone", "deepikapadukone", "deepika"]
    },
    {
        "canonical": "Lord Krishna",
        "description": "Lord Krishna, youthful Hindu deity with radiant blue complexion, peacock feather crown, holding golden flute with divine serene smile",
        "aliases": ["lord krishna", "lordkrishna", "krishna", "sri krishna"]
    },
    {
        "canonical": "Lord Rama",
        "description": "Lord Rama, Hindu deity with bow and sacred arrow, royal divine attire and golden crown",
        "aliases": ["lord rama", "lordrama", "rama", "sri rama", "lord ram"]
    },
    {
        "canonical": "Lord Shiva",
        "description": "Lord Shiva, Hindu deity with third eye, crescent moon, sacred serpent and trident with calm meditative aura",
        "aliases": ["lord shiva", "lordshiva", "shiva", "mahadev", "bholenath"]
    },
    {
        "canonical": "Lord Ganesha",
        "description": "Lord Ganesha, Hindu deity with elephant head, kind eyes, golden ornaments and modak sweet",
        "aliases": ["lord ganesha", "lordganesha", "ganesha", "ganesh", "ganapathi", "vinayaka"]
    },
    {
        "canonical": "Lord Hanuman",
        "description": "Lord Hanuman, Hindu deity with golden gada mace, glowing orange divine aura, and devoted powerful expression",
        "aliases": ["lord hanuman", "lordhanuman", "hanuman", "anjaneya", "bajrangbali"]
    }
]


def detect_entities(raw_text: str) -> list[dict]:
    """
    Detects all unique entities mentioned in raw user prompt.
    Checks normalized (spaced/punctuated) and compact (space-stripped) forms.
    Returns: list of dicts [{"name": canonical, "description": desc}, ...]
    """
    raw_lower = raw_text.lower()
    normalized_input = re.sub(r'[^a-z0-9\s]', ' ', raw_lower)
    normalized_input = re.sub(r'\s+', ' ', normalized_input).strip()
    compact_input = re.sub(r'[^a-z0-9]', '', raw_lower)

    detected = []
    seen_canonicals = set()

    for item in ENTITY_REGISTRY:
        canonical = item["canonical"]
        if canonical in seen_canonicals:
            continue

        matched = False
        for alias in item["aliases"]:
            alias_norm = re.sub(r'[^a-z0-9\s]', ' ', alias.lower()).strip()
            alias_compact = re.sub(r'[^a-z0-9]', '', alias.lower())

            # 1. Word boundary match on normalized spaced input
            if re.search(r'\b' + re.escape(alias_norm) + r'\b', normalized_input):
                matched = True
                break
            # 2. Substring match on compact input (handles spaced & spaceless: viratkohli, alluarjun, virtkohli, etc.)
            if alias_compact in compact_input:
                matched = True
                break

        if matched:
            detected.append({
                "name": canonical,
                "description": item["description"]
            })
            seen_canonicals.add(canonical)

    return detected


NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}

NEGATIVE_PROMPT_CONSTRAINTS = (
    "generic faces, look-alike strangers, merged faces, blended features, distorted faces, "
    "extra people, duplicate people, crowd, incorrect facial identity, face swapping, "
    "deformed eyes, blurry faces, low quality, unnatural expressions, missing subjects"
)


# ===========================================================================
# STAGE 1 MASTER -- _enhance_prompt (single entry point)
# ===========================================================================

def _enhance_prompt(raw: str) -> tuple[str, str, str, list[dict]]:
    """
    Master enhancement entry point with full entity normalization, strict entity count,
    positional composition, and negative constraints.
    Returns: (final_prompt, enhance_method, canonical_subject_str, detected_entities)
    """
    raw_clean = raw.strip()
    raw_lower = raw_clean.lower()
    normalized_input = re.sub(r'[^a-z0-9\s]', ' ', raw_lower)
    normalized_input = re.sub(r'\s+', ' ', normalized_input).strip()
    compact_input = re.sub(r'[^a-z0-9]', '', raw_lower)

    detected_entities = detect_entities(raw_clean)
    entity_names = [e["name"] for e in detected_entities]

    # Required structured debug logs
    print(f"[NOVA Entity Detection] Raw input: {raw_clean}", file=sys.stderr)
    print(f"[NOVA Entity Detection] Normalized input: {normalized_input}", file=sys.stderr)
    print(f"[NOVA Entity Detection] Compact input: {compact_input}", file=sys.stderr)
    print(f"[NOVA Entity Detection] Detected entities: {entity_names}", file=sys.stderr)
    print(f"[NOVA Intent] Detected intent: AI_GENERATION", file=sys.stderr)
    print(f"[NOVA Intent] Routing to: /api/generate_image", file=sys.stderr)

    # 1. Multi-Entity Composition (2 or more entities with strict count and positioning)
    if len(detected_entities) >= 2:
        count_num = len(detected_entities)
        count_word = NUMBER_WORDS.get(count_num, str(count_num))
        
        positions = []
        if count_num == 2:
            positions = ["on the left", "on the right"]
        elif count_num == 3:
            positions = ["on the left", "in the center", "on the right"]
        else:
            positions = [f"at position {i+1}" for i in range(count_num)]

        positioned_entities = []
        for idx, ent in enumerate(detected_entities):
            pos = positions[idx] if idx < len(positions) else "standing together"
            positioned_entities.append(f"{ent['name']} ({ent['description']}) {pos}")

        subjects_str = " and ".join(positioned_entities) if len(positioned_entities) == 2 else "; ".join(positioned_entities)

        final_prompt = (
            f"A crystal-clear photorealistic portrait photograph showing exactly {count_word} recognizable public figures: "
            f"{subjects_str}. Standing together smiling side by side in a professional setting. "
            f"Both individuals must preserve their distinct, authentic facial identity, accurate individual hairstyles, and recognizable facial features. "
            f"Do not replace them with generic strangers. Do not merge their faces. Do not generate additional people. "
            f"Both people clearly visible with equal prominence. Ultra-detailed 8K resolution, masterwork quality, cinematic studio lighting, sharp focus."
        )
        print(f"[NOVA Image Generation] Final prompt: {final_prompt}", file=sys.stderr)
        return final_prompt, "multi_entity_composition", " + ".join(entity_names), detected_entities

    # 2. Single Public Figure
    if len(detected_entities) == 1:
        ent = detected_entities[0]
        user_scene = _extract_user_scene(raw_clean, ent["name"].lower())
        scene_clause = f", {user_scene}" if (user_scene and len(user_scene) > 3) else ""
        final_prompt = (
            f"A crystal-clear photorealistic portrait photograph of {ent['name']} ({ent['description']}){scene_clause}. "
            f"Highly recognizable celebrity facial likeness, authentic skin texture, sharp focus, natural charismatic expression, "
            f"professional 8K UHD photography, cinematic studio lighting, masterwork quality."
        )
        print(f"[NOVA Image Generation] Final prompt: {final_prompt}", file=sys.stderr)
        return final_prompt, "single_entity", ent["name"], detected_entities

    # 3. Known Scene / Object Templates
    if re.search(r'\b(?:sunset|sun\s*set)\b', normalized_input):
        final_prompt = (
            "Create a beautiful realistic sunset landscape with warm orange and pink skies, "
            "soft golden sunlight, cinematic lighting, peaceful atmosphere, highly detailed, high resolution."
        )
        print(f"[NOVA Image Generation] Final prompt: {final_prompt}", file=sys.stderr)
        return final_prompt, "sunset_scene", "sunset", []

    if re.search(r'\b(?:robot|cyborg|humanoid|futuristic\s*robot)\b', normalized_input):
        final_prompt = (
            "A futuristic humanoid robot with advanced metallic armor, glowing blue energy cores, "
            "sleek chrome surfaces, cinematic sci-fi environment, dramatic lighting, highly detailed, photorealistic, 8K resolution."
        )
        print(f"[NOVA Image Generation] Final prompt: {final_prompt}", file=sys.stderr)
        return final_prompt, "robot_scene", "futuristic robot", []

    # 4. Unknown subjects: try Groq LLM or fallback
    groq_key = _get_api_key("GROQ_API_KEY")
    llm_out = None
    if groq_key:
        llm_out = _enhance_prompt_with_groq(raw_clean, groq_key)
        if llm_out:
            print(f"[NOVA Image Generation] Final prompt: {llm_out}", file=sys.stderr)
            return llm_out, "groq_llm", raw_clean, []

    fallback = _fallback_normalize(raw_clean)
    print(f"[NOVA Image Generation] Final prompt: {fallback}", file=sys.stderr)
    return fallback, "rules_fallback", raw_clean, []



# ===========================================================================
# STAGE 2A -- GEMINI IMAGE GENERATION
# ===========================================================================
_GEMINI_IMAGE_MODELS = [
    "gemini-3.1-flash-lite-image",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
]


def _generate_with_gemini(prompt: str, api_key: str) -> dict | None:
    if not _GENAI_AVAILABLE:
        return None
    client = _get_gemini_client(api_key)
    for model in _GEMINI_IMAGE_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                ),
            )
            for part in resp.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    raw_data = part.inline_data.data
                    b64 = (
                        base64.b64encode(raw_data).decode("utf-8")
                        if isinstance(raw_data, (bytes, bytearray))
                        else raw_data
                    )
                    return {"image_b64": b64, "mime": part.inline_data.mime_type or "image/png", "model": model}
        except Exception as exc:
            err = str(exc).lower()
            print(f"[NOVA-IMGGEN] Gemini {model} failed: {exc}", file=sys.stderr)
            if "429" in err or "resource_exhausted" in err or "quota" in err:
                break
    return None


# ===========================================================================
# STAGE 2B -- POLLINATIONS.AI
# ===========================================================================
_POLLINATIONS_PARAMS = "width=1024&height=1024&nologo=true&enhance=false&model=flux"
_MIN_IMAGE_BYTES     = 2000


def _pollinations_seed(prompt: str) -> int:
    """
    Deterministic seed derived from SHA-256 of the prompt.
    Unlike Python's hash(), this is stable across processes and deployments.
    """
    return int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16) % 99991


def _generate_with_pollinations(prompt: str, negative_prompt: str | None = None, max_retries: int = 2) -> dict | None:
    encoded = urllib.parse.quote(prompt[:1200], safe="")
    seed    = _pollinations_seed(prompt)
    neg_clause = f"&negative={urllib.parse.quote(negative_prompt[:500], safe='')}" if negative_prompt else ""
    url     = f"https://image.pollinations.ai/prompt/{encoded}?{_POLLINATIONS_PARAMS}{neg_clause}&seed={seed}"
    headers = {"User-Agent": "NOVA-AI-Assistant/2.5.0", "Accept": "image/jpeg, image/png, image/*"}

    last_error = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = 2 ** attempt
            print(f"[NOVA-IMGGEN] Pollinations retry {attempt} after {wait}s", file=sys.stderr)
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                ct        = resp.headers.get("Content-Type", "")
                raw_bytes = resp.read()

                if "image" not in ct.lower():
                    print(f"[NOVA-IMGGEN] Pollinations non-image CT: {ct!r}", file=sys.stderr)
                    last_error = "non-image CT"; continue

                if len(raw_bytes) < _MIN_IMAGE_BYTES:
                    print(f"[NOVA-IMGGEN] Pollinations too small: {len(raw_bytes)}B", file=sys.stderr)
                    last_error = "too small"; continue

                is_jpeg = raw_bytes[:2] == b'\xff\xd8'
                is_png  = raw_bytes[:4] == b'\x89PNG'
                if not (is_jpeg or is_png):
                    print(f"[NOVA-IMGGEN] Unexpected magic {raw_bytes[:4].hex()!r} CT={ct!r} -- accepting", file=sys.stderr)

                b64  = base64.b64encode(raw_bytes).decode("utf-8")
                mime = ct.split(";")[0].strip() or "image/jpeg"
                print(f"[NOVA-IMGGEN] Pollinations OK: mime={mime!r}, bytes={len(raw_bytes)}", file=sys.stderr)
                return {"image_b64": b64, "mime": mime, "model": "pollinations-flux", "image_url": url}

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[NOVA-IMGGEN] Pollinations 429 attempt {attempt}", file=sys.stderr)
                last_error = "429"
            else:
                print(f"[NOVA-IMGGEN] Pollinations HTTP {e.code}: {e}", file=sys.stderr)
                last_error = f"HTTP {e.code}"; break
        except Exception as exc:
            print(f"[NOVA-IMGGEN] Pollinations attempt {attempt}: {exc}", file=sys.stderr)
            last_error = str(exc)

    print(f"[NOVA-IMGGEN] Pollinations gave up. last_error={last_error}", file=sys.stderr)
    return None


# ===========================================================================
# REQUEST HANDLER
# ===========================================================================
class handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        print(f"[NOVA-IMGGEN-ERR] {fmt % args}", file=sys.stderr)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        stage = "init"
        try:
            stage = "reading_body"
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            data   = json.loads(body.decode("utf-8"))

            raw_prompt = (data.get("prompt") or "").strip()
            if not raw_prompt:
                return self._json(400, {"success": False, "error": "Prompt is required."})
            if len(raw_prompt) > 1000:
                raw_prompt = raw_prompt[:1000]

            print("[IMAGE DEBUG] Request received", flush=True)
            print(f"[IMAGE DEBUG] Prompt: {raw_prompt}", flush=True)

            stage = "enhancing_prompt"
            final_prompt, enhance_method, extracted_subject, detected_entities = _enhance_prompt(raw_prompt)
            print(f"[IMAGE DEBUG] Enhancement method: {enhance_method}", flush=True)

            is_celebrity = len(detected_entities) > 0
            negative_constraints = NEGATIVE_PROMPT_CONSTRAINTS if is_celebrity else None

            # --- Gemini ---
            gemini_key = _get_api_key("GEMINI_API_KEY")
            if gemini_key and _GENAI_AVAILABLE:
                stage = "provider_gemini"
                print("[IMAGE DEBUG] Trying provider: Google Gemini", flush=True)
                try:
                    result = _generate_with_gemini(final_prompt, gemini_key)
                    if result:
                        print(f"[NOVA-IMGGEN] Gemini OK model={result.get('model')} mime={result.get('mime')}", file=sys.stderr, flush=True)
                        mime = result.get("mime", "image/jpeg")
                        b64 = result.get("image_b64", "")
                        display_img = f"data:{mime};base64,{b64}" if b64 else ""
                        return self._json(200, {
                            "success": True,
                            "image": display_img,
                            "image_b64": b64,
                            "image_url": None,
                            "mime": mime,
                            "provider": "Google Gemini",
                            "model": result.get("model"),
                            "prompt": final_prompt,
                            "original_prompt": raw_prompt,
                            "method": enhance_method,
                            "enhance_method": enhance_method,
                            "entities_detected": [e["name"] for e in detected_entities],
                            "entity_count": len(detected_entities),
                            "is_celebrity_request": is_celebrity,
                            "negative_prompt": negative_constraints,
                            "disclaimer": "AI-generated artistic interpretation. Generative diffusion models approximate public figure likenesses and cannot guarantee exact photographic facial identity match.",
                        })
                except Exception as ge:
                    print(f"[IMAGE ERROR] Gemini error: {type(ge).__name__} {ge}", file=sys.stderr, flush=True)

            # --- Pollinations ---
            stage = "provider_pollinations"
            print("[IMAGE DEBUG] Trying provider: Pollinations AI", flush=True)
            try:
                result = _generate_with_pollinations(final_prompt, negative_prompt=negative_constraints)
                if result:
                    mime = result.get("mime", "image/jpeg")
                    b64 = result.get("image_b64")
                    url = result.get("image_url")
                    display_img = f"data:{mime};base64,{b64}" if b64 else (url or "")
                    return self._json(200, {
                        "success": True,
                        "image": display_img,
                        "image_b64": b64,
                        "image_url": url,
                        "mime": mime,
                        "provider": "Pollinations AI",
                        "model": result.get("model"),
                        "prompt": final_prompt,
                        "original_prompt": raw_prompt,
                        "method": enhance_method,
                        "enhance_method": enhance_method,
                        "entities_detected": [e["name"] for e in detected_entities],
                        "entity_count": len(detected_entities),
                        "is_celebrity_request": is_celebrity,
                        "negative_prompt": negative_constraints,
                        "disclaimer": "AI-generated artistic interpretation. Generative diffusion models approximate public figure likenesses and cannot guarantee exact photographic facial identity match.",
                    })
            except Exception as pe:
                print(f"[IMAGE ERROR] Pollinations error: {type(pe).__name__} {pe}", file=sys.stderr, flush=True)


            stage = "all_providers_failed"
            return self._json(200, {
                "success": False,
                "error": "Image generation is temporarily unavailable. All providers failed -- usually a temporary rate-limit issue. Please try again in a few seconds.",
                "debug_stage": stage,
            })

        except Exception as e:
            print("[IMAGE ERROR]", type(e).__name__, str(e), file=sys.stderr, flush=True)
            tb = traceback.format_exc()
            print(f"[NOVA-IMGGEN FATAL]\n{tb}", file=sys.stderr, flush=True)
            try:
                self._json(200, {
                    "success": False,
                    "error": f"Image generation encountered an unexpected error: {e}",
                    "debug_stage": stage,
                    "debug_type": type(e).__name__
                })
            except Exception:
                pass

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age",       "86400")

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)
