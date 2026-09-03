"""
NOVA Web API — /api/search_images  v5.0
Real Web Image Search Engine with Strict Entity Matching, Result Validation & Confidence Scoring

Features:
1. Exact Entity Matching: Detects specific celebrities, monuments, and nature queries.
2. Query Normalization: Strips conversational Telugu & English filler words (ivu, chupinchu, naku, photos, etc.).
3. Strict Conflict Rejection: Automatically rejects relatives, other cricketers, and conflicting entities (e.g. Allu Aravind for Allu Arjun, Rohit Sharma for Virat Kohli).
4. Multi-Attempt Search Cascade: Exact Wikipedia Articles -> Wikimedia Commons -> Google Custom Search -> Serper -> Bing -> Openverse.
5. Confidence Scoring & Deduplication: Scores every candidate image (+50 exact match, -100 conflict) and removes duplicate URLs.
"""

import os
import sys
import json
import re
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler

from dotenv import load_dotenv


def _safe_log(msg: str):
    """Write log messages safely to stderr without UnicodeEncodeError on Windows."""
    try:
        sys.stderr.write(f"[NOVA-IMGSEARCH] {msg}\n")
        sys.stderr.flush()
    except Exception:
        try:
            safe = msg.encode("ascii", errors="replace").decode("ascii")
            sys.stderr.write(f"[NOVA-IMGSEARCH] {safe}\n")
            sys.stderr.flush()
        except Exception:
            pass


def _ensure_env():
    here = Path(__file__).resolve().parent
    candidates = [here, here.parent, Path.cwd(), here.parent.parent]
    for directory in candidates:
        for filename in (".env.local", ".env"):
            env_path = directory / filename
            if env_path.is_file():
                try:
                    with open(env_path, "r", encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip().strip("'\"")
                                if k and k not in os.environ:
                                    os.environ[k] = v
                except Exception:
                    pass


def _get_api_key(var_names: list[str] | str) -> str | None:
    _ensure_env()
    if isinstance(var_names, str):
        var_names = [var_names]
    placeholders = {
        "your_api_key_here", "your_api_key", "your_serper_api_key",
        "your_google_key", "none", "null", ""
    }
    for name in var_names:
        key = os.environ.get(name, "").strip()
        if key and key.lower() not in placeholders:
            return key
    return None


def _is_valid_http_url(url: str) -> bool:
    """Validate that URL is non-empty and starts with http:// or https://."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


# ---------------------------------------------------------------------------
# Strict Entity Knowledge Base & Conflict Matrix
# ---------------------------------------------------------------------------
KNOWN_ENTITIES = {
    "ravi teja": {
        "canonical": "Ravi Teja",
        "wiki_articles": ["Ravi Teja", "Ravi Teja filmography"],
        "positive_keywords": ["ravi teja", "raviteja", "mass maharaja", "dhamaka", "krack", "waltair veerayya", "eagle", "tiger nageswara rao", "vikramarkudu", "kick", "balupu", "venky", "bhadra", "actor"],
        "negative_keywords": [
            "raviteja padiri", "sai ravi teja", "tejas express", "tejas", "allu arjun", "mahesh babu", "ravi_teja.jpg"
        ],
        "search_queries": ["Ravi Teja actor", "Ravi Teja Dhamaka promotions", "Mass Maharaja Ravi Teja"],
        "is_person": True
    },
    "allu arjun": {
        "canonical": "Allu Arjun",
        "wiki_articles": ["Allu Arjun"],
        "positive_keywords": ["allu arjun", "pushpa", "arya", "stylish star", "icon star"],
        "negative_keywords": [
            "allu aravind", "allu sirish", "allu bobby", "allu sneha", "allu ayaan",
            "allu arha", "allu ramalingaiah", "chiranjeevi", "ram charan", "pawan kalyan",
            "naga chaitanya", "mahesh babu", "ntr", "venkatesh", "nagarjuna"
        ],
        "search_queries": ["Allu Arjun", "Allu Arjun actor", "Allu Arjun Filmfare"],
        "is_person": True
    },
    "virat kohli": {
        "canonical": "Virat Kohli",
        "wiki_articles": ["Virat Kohli"],
        "positive_keywords": ["virat kohli", "kohli", "king kohli"],
        "negative_keywords": [
            "rohit sharma", "ms dhoni", "hardik pandya", "kl rahul", "shikhar dhawan",
            "sachin tendulkar", "ravindra jadeja", "jasprit bumrah", "shubman gill",
            "rishabh pant", "sourav ganguly", "kapil dev", "brian lara", "ricky ponting",
            "steve smith", "kane williamson", "joe root", "babar azam", "gautam gambhir"
        ],
        "search_queries": ["Virat Kohli", "Virat Kohli cricket", "Virat Kohli batting"],
        "is_person": True
    },
    "mahesh babu": {
        "canonical": "Mahesh Babu",
        "wiki_articles": ["Mahesh Babu"],
        "positive_keywords": ["mahesh babu", "prince mahesh", "superstar mahesh"],
        "negative_keywords": [
            "krishna ghattamaneni", "namrata shirodkar", "gautham ghattamaneni",
            "sitara ghattamaneni", "sudheer babu", "manjula ghattamaneni", "allu arjun"
        ],
        "search_queries": ["Mahesh Babu", "Mahesh Babu actor"],
        "is_person": True
    },
    "pawan kalyan": {
        "canonical": "Pawan Kalyan",
        "wiki_articles": ["Pawan Kalyan"],
        "positive_keywords": ["pawan kalyan", "power star", "jana sena"],
        "negative_keywords": [
            "chiranjeevi", "naga babu", "ram charan", "varun tej", "sai dharam tej", "akira nandan"
        ],
        "search_queries": ["Pawan Kalyan", "Pawan Kalyan actor"],
        "is_person": True
    },
    "prabhas": {
        "canonical": "Prabhas",
        "wiki_articles": ["Prabhas"],
        "positive_keywords": ["prabhas", "baahubali", "salaar", "kalki"],
        "negative_keywords": ["krishnam raju", "rajamouli", "rana daggubati"],
        "search_queries": ["Prabhas", "Prabhas actor"],
        "is_person": True
    },
    "ram charan": {
        "canonical": "Ram Charan",
        "wiki_articles": ["Ram Charan"],
        "positive_keywords": ["ram charan", "mega power star", "rrr"],
        "negative_keywords": ["chiranjeevi", "allu arjun", "pawan kalyan", "naga babu"],
        "search_queries": ["Ram Charan", "Ram Charan actor"],
        "is_person": True
    },
    "jr ntr": {
        "canonical": "N. T. Rama Rao Jr.",
        "wiki_articles": ["N. T. Rama Rao Jr."],
        "positive_keywords": ["jr ntr", "junior ntr", "ntr", "tarak", "devara", "young tiger"],
        "negative_keywords": ["kalyan ram", "balakrishna"],
        "search_queries": ["N. T. Rama Rao Jr.", "Jr NTR actor"],
        "is_person": True
    },
    "chiranjeevi": {
        "canonical": "Chiranjeevi",
        "wiki_articles": ["Chiranjeevi"],
        "positive_keywords": ["chiranjeevi", "megastar chiranjeevi", "megastar"],
        "negative_keywords": ["ram charan", "pawan kalyan", "naga babu"],
        "search_queries": ["Chiranjeevi", "Chiranjeevi actor"],
        "is_person": True
    },
    "nani": {
        "canonical": "Nani",
        "wiki_articles": ["Nani (actor)"],
        "positive_keywords": ["nani", "natural star nani"],
        "negative_keywords": [],
        "search_queries": ["Nani actor", "Natural Star Nani"],
        "is_person": True
    },
    "vijay deverakonda": {
        "canonical": "Vijay Deverakonda",
        "wiki_articles": ["Vijay Deverakonda"],
        "positive_keywords": ["vijay deverakonda", "deverakonda", "arjun reddy"],
        "negative_keywords": ["anand deverakonda"],
        "search_queries": ["Vijay Deverakonda", "Vijay Deverakonda actor"],
        "is_person": True
    },
    "ms dhoni": {
        "canonical": "MS Dhoni",
        "wiki_articles": ["MS Dhoni"],
        "positive_keywords": ["ms dhoni", "dhoni", "captain cool", "thala"],
        "negative_keywords": ["virat kohli", "rohit sharma"],
        "search_queries": ["MS Dhoni", "MS Dhoni cricket"],
        "is_person": True
    },
    "rohit sharma": {
        "canonical": "Rohit Sharma",
        "wiki_articles": ["Rohit Sharma"],
        "positive_keywords": ["rohit sharma", "hitman"],
        "negative_keywords": ["virat kohli", "hardik pandya"],
        "search_queries": ["Rohit Sharma", "Rohit Sharma cricket"],
        "is_person": True
    },
    "charminar": {
        "canonical": "Charminar",
        "wiki_articles": ["Charminar"],
        "positive_keywords": ["charminar", "hyderabad monument"],
        "negative_keywords": [
            "golconda", "qutb shahi", "mecca masjid", "taj mahal", "hawa mahal",
            "red fort", "gateway of india", "india gate", "qutub minar", "mysore palace"
        ],
        "search_queries": ["Charminar Hyderabad", "Charminar monument", "Charminar"],
        "is_monument": True
    },
    "taj mahal": {
        "canonical": "Taj Mahal",
        "wiki_articles": ["Taj Mahal"],
        "positive_keywords": ["taj mahal", "agra", "mumtaz"],
        "negative_keywords": ["charminar", "qutub minar", "red fort", "humayun", "hawa mahal"],
        "search_queries": ["Taj Mahal Agra", "Taj Mahal monument"],
        "is_monument": True
    },
    "kerala waterfalls": {
        "canonical": "Kerala waterfalls",
        "wiki_articles": [
            "Athirappilly Falls", "Meenmutty Falls, Wayanad", "Soochipara Falls",
            "Kanthanpara Waterfalls", "Palaruvi Falls", "Vazhachal Falls", "Cheeyappara Waterfalls"
        ],
        "positive_keywords": [
            "kerala", "waterfall", "falls", "athirappilly", "athirapally", "meenmutty",
            "soochipara", "kanthanpara", "palaruvi", "vazhachal", "cheeyappara",
            "thommankuthu", "thusharagiri", "adayanpara", "marmala", "wayanad", "thrissur", "idukki"
        ],
        "negative_keywords": [
            "tamil nadu", "karnataka", "niagara", "jog falls", "courtallam",
            "hogenakkal", "dudhsagar", "iguazu", "victoria falls", "angel falls", "shivasamudram"
        ],
        "search_queries": [
            "Athirappilly Falls Kerala", "Meenmutty Falls Kerala", "Soochipara Falls Kerala",
            "Kerala waterfalls", "Waterfalls in Kerala"
        ],
        "is_nature": True
    },
    "kerala nature": {
        "canonical": "Kerala nature",
        "wiki_articles": [
            "Munnar", "Kerala backwaters", "Wayanad district", "Vagamon",
            "Silent Valley National Park", "Athirappilly Falls"
        ],
        "positive_keywords": [
            "kerala", "nature", "landscape", "scenery", "munnar", "wayanad",
            "alleppey", "allepey", "alappuzha", "kumarakom", "backwaters",
            "western ghats", "vagamon", "silent valley", "tea plantation",
            "tea garden", "tea", "hills", "forest", "lake", "river", "waterfall", "green", "beauty"
        ],
        "negative_keywords": [
            "kashmir", "himachal", "ladakh", "rajasthan", "desert", "snow mountains",
            "switzerland", "bali", "thailand"
        ],
        "search_queries": [
            "Kerala nature landscape", "Munnar Kerala tea gardens",
            "Kerala backwaters", "Kerala nature", "Wayanad Kerala"
        ],
        "is_nature": True
    }
}


def _normalize_text(text: str) -> str:
    """Normalize text by lowercasing, replacing punctuation/hyphens/underscores with spaces, and collapsing spaces."""
    if not text:
        return ""
    cleaned = re.sub(r'[_\-\.\,\:\;\(\)\[\]\{\}\/\\\"\'`~!?|@#$%^&*+=<>]+', ' ', text.lower())
    return re.sub(r'\s+', ' ', cleaned).strip()


def _clean_and_classify_query(raw: str) -> tuple[str, dict | None]:
    """
    Cleans conversational filler phrases and matches against the strict entity registry.
    e.g. "Allu Arjun images ivu" -> ("Allu Arjun", entity_config)
         "naku raviteja images ivu" -> ("Ravi Teja", entity_config)
         "waterfalls in Kerala images" -> ("Kerala waterfalls", entity_config)
    """
    cleaned = raw.strip()

    # 1. Strip leading conversational prefixes
    prefixes = [
        r'^(?:show\s+me|give\s+me|find|search|display|look\s+up|i\s+want\s+to\s+see)\s+(?:photos?|images?|pictures?|pictuers?|pichers?|pics?|wallpapers?)\s+(?:of|about|for)?\s*',
        r'^(?:show\s+me|give\s+me|find|search|display|look\s+up|i\s+want\s+to\s+see)\s+(?:a\s+|an\s+|some\s+)?',
        r'^(?:real\s+)?(?:photos?|images?|pictures?|pictuers?|pichers?|pics?|wallpapers?)\s+(?:of|about|for)\s*',
    ]
    for p in prefixes:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE).strip()

    # 2. Strip Telugu/Hindi filler request words
    telugu_fillers = [
        r'\b(?:photos?|images?|pictures?|pictuers?|pichers?|pics?|wallpaper)\s+(?:ivu|ivvandi|chupinchu|chupinchandi|kavali|kavale|chudali|ivvu)\b',
        r'\b(?:real\s+photos?|real\s+images?|real\s+pictures?)\s+(?:ivu|ivvandi|chupinchu|chupinchandi|ivvu)\b',
        r'\b(?:ivu|ivvandi|chupinchu|chupinchandi|kavali|kavale|chudali|ivvu)\b',
        r'\b(?:naku|naaku|oka|okati|please|andi)\b',
    ]
    for tf in telugu_fillers:
        cleaned = re.sub(tf, ' ', cleaned, flags=re.IGNORECASE).strip()

    # 3. Strip leading occupation/title indicators
    cleaned = re.sub(r'^(?:actor|hero|heroine|actress|star|cricketer|player|director)\s+', '', cleaned, flags=re.IGNORECASE).strip()

    # 4. Strip trailing visual nouns
    cleaned = re.sub(r'\s+(?:real\s+)?(?:images?|photos?|pictures?|pictuers?|pichers?|pics?|wallpapers?)$', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'^(?:real\s+)?(?:images?|photos?|pictures?|pictuers?|pichers?|pics?|wallpapers?)\s+of\s+', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

    lower_cleaned = _normalize_text(cleaned)

    # 5. Check for known entity matches
    if ("ravi" in lower_cleaned and "teja" in lower_cleaned) or "raviteja" in lower_cleaned or "mass maharaja" in lower_cleaned:
        return KNOWN_ENTITIES["ravi teja"]["canonical"], KNOWN_ENTITIES["ravi teja"]

    if "allu" in lower_cleaned and "arjun" in lower_cleaned:
        return KNOWN_ENTITIES["allu arjun"]["canonical"], KNOWN_ENTITIES["allu arjun"]

    if "virat" in lower_cleaned or ("kohli" in lower_cleaned and "cricket" in lower_cleaned):
        return KNOWN_ENTITIES["virat kohli"]["canonical"], KNOWN_ENTITIES["virat kohli"]

    if "mahesh" in lower_cleaned and "babu" in lower_cleaned:
        return KNOWN_ENTITIES["mahesh babu"]["canonical"], KNOWN_ENTITIES["mahesh babu"]

    if "prabhas" in lower_cleaned:
        return KNOWN_ENTITIES["prabhas"]["canonical"], KNOWN_ENTITIES["prabhas"]

    if "pawan" in lower_cleaned and "kalyan" in lower_cleaned:
        return KNOWN_ENTITIES["pawan kalyan"]["canonical"], KNOWN_ENTITIES["pawan kalyan"]

    if "ram" in lower_cleaned and "charan" in lower_cleaned:
        return KNOWN_ENTITIES["ram charan"]["canonical"], KNOWN_ENTITIES["ram charan"]

    if ("jr" in lower_cleaned and "ntr" in lower_cleaned) or ("junior" in lower_cleaned and "ntr" in lower_cleaned) or lower_cleaned == "ntr":
        return KNOWN_ENTITIES["jr ntr"]["canonical"], KNOWN_ENTITIES["jr ntr"]

    if "chiranjeevi" in lower_cleaned or "megastar" in lower_cleaned:
        return KNOWN_ENTITIES["chiranjeevi"]["canonical"], KNOWN_ENTITIES["chiranjeevi"]

    if lower_cleaned == "nani" or "natural star" in lower_cleaned:
        return KNOWN_ENTITIES["nani"]["canonical"], KNOWN_ENTITIES["nani"]

    if "deverakonda" in lower_cleaned:
        return KNOWN_ENTITIES["vijay deverakonda"]["canonical"], KNOWN_ENTITIES["vijay deverakonda"]

    if "dhoni" in lower_cleaned:
        return KNOWN_ENTITIES["ms dhoni"]["canonical"], KNOWN_ENTITIES["ms dhoni"]

    if "rohit" in lower_cleaned and "sharma" in lower_cleaned:
        return KNOWN_ENTITIES["rohit sharma"]["canonical"], KNOWN_ENTITIES["rohit sharma"]

    if "charminar" in lower_cleaned:
        return KNOWN_ENTITIES["charminar"]["canonical"], KNOWN_ENTITIES["charminar"]

    if "taj" in lower_cleaned and "mahal" in lower_cleaned:
        return KNOWN_ENTITIES["taj mahal"]["canonical"], KNOWN_ENTITIES["taj mahal"]

    if "waterfall" in lower_cleaned and "kerala" in lower_cleaned:
        return KNOWN_ENTITIES["kerala waterfalls"]["canonical"], KNOWN_ENTITIES["kerala waterfalls"]

    if "kerala" in lower_cleaned and any(w in lower_cleaned for w in ("nature", "landscape", "scenery", "hills", "forest", "backwater")):
        return KNOWN_ENTITIES["kerala nature"]["canonical"], KNOWN_ENTITIES["kerala nature"]

    for key, cfg in KNOWN_ENTITIES.items():
        if key in lower_cleaned:
            return cfg["canonical"], cfg

    # Return cleaned query with general entity config
    general_config = {
        "canonical": cleaned,
        "positive_keywords": [w.lower() for w in cleaned.split() if len(w) > 2],
        "negative_keywords": [],
        "search_queries": [cleaned, f"{cleaned} high resolution"],
        "is_general": True
    }
    return cleaned, general_config


def _validate_and_score_image(title: str, image_url: str, source_url: str, entity_config: dict | None, description: str = "") -> tuple[bool, int, str]:
    """
    Validates candidate image against entity rules and assigns an entity relevance score.
    Returns: (is_valid: bool, score: int, validation_status: str)

    Scoring Model:
      - Exact entity name in title = +100
      - Exact entity name in description / source = +80
      - Exact entity name in metadata / URL = +60
      - Partial name match = +20 (rejected for person mode)
      - Related person only (when requested entity missing) = -100
    """
    t_norm = _normalize_text(title)
    url_norm = _normalize_text(image_url)
    src_norm = _normalize_text(source_url)
    desc_norm = _normalize_text(description)
    combined_norm = f"{t_norm} {url_norm} {src_norm} {desc_norm}"

    # Filter out non-photo and junk file formats
    if re.search(r'\.(?:svg|ogg|oga|ogv|mp3|mp4|webm|pdf|doc|txt)$', image_url.lower()):
        return False, -1000, "REJECTED: Unsupported media extension (SVG/Audio/Video)"

    # Filter out diagrams, logos, flags, maps, and icons
    if re.search(r'\b(?:icon|flag|emblem|symbol|map|logo|coat_of_arms|diagram|signature|vector|silhouette|clipart)\b', combined_norm):
        return False, -1000, "REJECTED: Icon / logo / symbol / map excluded"

    if not entity_config:
        return True, 50, "ACCEPTED"

    canonical_norm = _normalize_text(entity_config.get("canonical", ""))
    canonical_pat = r'\b' + re.escape(canonical_norm) + r'\b'
    canonical_present = bool(re.search(canonical_pat, combined_norm))

    # Check for known conflicting entities / wrong persons (-100 points rejection)
    for neg in entity_config.get("negative_keywords", []):
        neg_norm = _normalize_text(neg)
        neg_pat = r'\b' + re.escape(neg_norm) + r'\b'
        if re.search(neg_pat, combined_norm):
            return False, -100, f"REJECTED: Related/conflicting person detected ('{neg}')"

    score = 0

    # -----------------------------------------------------------------------
    # A) CELEBRITY / PERSON SEARCH
    # -----------------------------------------------------------------------
    if entity_config.get("is_person"):
        # Exact entity name in title = +100
        if re.search(canonical_pat, t_norm):
            score += 100
        # Exact entity name in description / source = +80
        elif re.search(canonical_pat, desc_norm) or re.search(canonical_pat, src_norm):
            score += 80
        # Exact entity name in metadata / URL = +60
        elif re.search(canonical_pat, url_norm):
            score += 60
        elif any(re.search(r'\b' + re.escape(_normalize_text(pos)) + r'\b', t_norm) for pos in entity_config.get("positive_keywords", []) if _normalize_text(pos) != canonical_norm):
            score += 40

        # Check for partial name match = +20 (rejected if full name is missing)
        if score == 0:
            words = [w for w in canonical_norm.split() if len(w) > 2]
            if any(re.search(r'\b' + re.escape(w) + r'\b', t_norm) for w in words):
                score = 20
                return False, score, f"REJECTED: Partial name match (+20), exact '{canonical_norm}' required"
            else:
                return False, -100, f"REJECTED: Missing requested entity '{canonical_norm}'"

        is_valid = (score >= 60)
        status = "ACCEPTED" if is_valid else f"REJECTED: Score {score} below safe threshold 60"
        return is_valid, score, status


    # -----------------------------------------------------------------------
    # B) PLACE / LANDMARK SEARCH
    # -----------------------------------------------------------------------
    elif entity_config.get("is_monument") or entity_config.get("search_type") == "PLACE":
        if re.search(canonical_pat, t_norm):
            score += 100
        elif re.search(canonical_pat, desc_norm):
            score += 80
        elif re.search(canonical_pat, url_norm):
            score += 60

        is_valid = (score >= 60)
        status = "ACCEPTED" if is_valid else f"REJECTED: Missing landmark name '{canonical_norm}'"
        return is_valid, score, status

    # -----------------------------------------------------------------------
    # C) NATURE SEARCH
    # -----------------------------------------------------------------------
    elif entity_config.get("is_nature") or entity_config.get("search_type") == "NATURE":
        pos_hits = sum(1 for pos in entity_config.get("positive_keywords", []) if re.search(r'\b' + re.escape(_normalize_text(pos)) + r'\b', combined_norm))
        if "kerala" in combined_norm and pos_hits >= 1:
            score += 80 + (pos_hits * 10)
        elif pos_hits >= 2:
            score += 70 + (pos_hits * 10)
        elif pos_hits == 1:
            score += 50
        else:
            return False, -100, "REJECTED: Missing required nature/location keywords"

        is_valid = (score >= 50)
        status = "ACCEPTED" if is_valid else f"REJECTED: Score {score} below safe threshold 50"
        return is_valid, score, status

    # -----------------------------------------------------------------------
    # D) GENERAL OBJECT / SEMANTIC SEARCH
    # -----------------------------------------------------------------------
    else:
        pos_hits = sum(1 for pos in entity_config.get("positive_keywords", []) if re.search(r'\b' + re.escape(_normalize_text(pos)) + r'\b', combined_norm))
        if pos_hits > 0:
            score += 50 + (pos_hits * 20)
        else:
            score += 30

        is_valid = (score >= 40)
        status = "ACCEPTED" if is_valid else f"REJECTED: Score {score} below safe threshold 40"
        return is_valid, score, status



def validate_image_entity(query_entity: str, image_result: dict, entity_config: dict | None = None) -> tuple[bool, int, str]:
    """Public validator function matching requested validateImageEntity interface."""
    title = image_result.get("title", "")
    image_url = image_result.get("image_url", "")
    source_url = image_result.get("source_url", "")
    desc = image_result.get("description", "")
    return _validate_and_score_image(title, image_url, source_url, entity_config, description=desc)




def _normalize_image_item(title: str, thumbnail: str, image_url: str, source_url: str, provider: str, score: int = 50) -> dict | None:
    """Normalize and validate a single image search result."""
    t = (title or "Real Web Image").strip()
    img = (image_url or "").strip()
    thumb = (thumbnail or "").strip() or img
    src = (source_url or "").strip() or img

    if not _is_valid_http_url(img):
        if _is_valid_http_url(thumb):
            img = thumb
        else:
            return None

    if not _is_valid_http_url(thumb):
        thumb = img

    if not _is_valid_http_url(src):
        src = img

    return {
        "title": t,
        "thumbnail": thumb,
        "image_url": img,
        "source_url": src,
        "provider": provider,
        "_score": score
    }


# ---------------------------------------------------------------------------
# Provider 1: Wikipedia PageImages & Exact Article Images
# ---------------------------------------------------------------------------
def _fetch_wikipedia_exact_articles(articles: list[str], entity_config: dict) -> list[dict]:
    """Fetch lead and prominent images directly from exact Wikipedia articles."""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    for article in articles:
        encoded = urllib.parse.quote(article)
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query&titles={encoded}"
            f"&prop=pageimages|info&inprop=url&pithumbsize=960&format=json"
        )
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if "thumbnail" in page:
                    title = f"Photo of {page.get('title', article)}"
                    thumb = page["thumbnail"].get("source", "")
                    desc_url = page.get("fullurl") or thumb

                    valid, score, reason = _validate_and_score_image(title, thumb, desc_url, entity_config)
                    if valid:
                        norm = _normalize_image_item(title, thumb, thumb, desc_url, "Wikipedia (Official Article)", score=score + 30)
                        if norm:
                            results.append(norm)
        except Exception as e:
            _safe_log(f"Wikipedia exact article fetch failed for '{article}': {e}")
    return results


# ---------------------------------------------------------------------------
# Provider 1b: Dynamic Wikipedia Page Search (Finds verified images for any entity)
# ---------------------------------------------------------------------------
def _search_wikipedia_dynamic(query: str, entity_config: dict, num: int = 6) -> list[dict]:
    """Search Wikipedia pages dynamically and extract official page thumbnails."""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    encoded = urllib.parse.quote(query)
    url = (
        f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={encoded}&gsrlimit={min(num, 10)}&prop=pageimages|info&inprop=url&pithumbsize=960&format=json"
    )
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if "thumbnail" in page:
                page_title = page.get("title", query)
                title = f"Photo of {page_title}"
                thumb = page["thumbnail"].get("source", "")
                desc_url = page.get("fullurl") or thumb

                valid, score, reason = _validate_and_score_image(title, thumb, desc_url, entity_config)
                if valid:
                    norm = _normalize_image_item(title, thumb, thumb, desc_url, "Wikipedia", score=score + 25)
                    if norm:
                        results.append(norm)
    except Exception as e:
        _safe_log(f"Wikipedia dynamic search failed for '{query}': {e}")
    return results


# ---------------------------------------------------------------------------
# Provider 2: Wikimedia Commons (High-Resolution MediaWiki Search)
# ---------------------------------------------------------------------------
def _search_wikimedia_commons(query: str, entity_config: dict, num: int = 8) -> list[dict]:
    encoded = urllib.parse.quote(query)
    url = (
        f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
        f"&gsrnamespace=6&gsrsearch={encoded}&gsrlimit={min(num * 2, 20)}"
        f"&prop=imageinfo&iiprop=url&iiurlwidth=800&format=json"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
    )
    results = []
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            raw_title = page.get("title", "").replace("File:", "")
            clean_title = re.sub(r'\.(?:jpg|jpeg|png|webp|gif|svg)$', '', raw_title, flags=re.IGNORECASE).replace('_', ' ').strip()
            imageinfo = page.get("imageinfo", [{}])[0]
            full_url = imageinfo.get("url", "")
            thumb = imageinfo.get("thumburl") or full_url
            desc_url = imageinfo.get("descriptionurl") or full_url

            valid, score, reason = _validate_and_score_image(clean_title, full_url, desc_url, entity_config)
            if valid:
                norm = _normalize_image_item(clean_title, thumb, full_url, desc_url, "Wikimedia Commons", score=score)
                if norm:
                    results.append(norm)
            else:
                _safe_log(f"Wikimedia rejected item '{clean_title[:40]}': {reason}")
    except Exception as e:
        _safe_log(f"Wikimedia Commons search failed: {e}")
    return results


# ---------------------------------------------------------------------------
# Provider 3: Google Custom Search JSON API
# ---------------------------------------------------------------------------
def _search_google_custom_search(query: str, api_key: str, cx: str, entity_config: dict, num: int = 8) -> list[dict]:
    params = urllib.parse.urlencode({
        "key": api_key,
        "cx": cx,
        "q": query,
        "searchType": "image",
        "num": min(num, 10),
        "safe": "active",
    })
    url = f"https://www.googleapis.com/customsearch/v1?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "NOVA-AI-Assistant/5.0"})
    results = []
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("items", [])[:num]:
            title = item.get("title", "")
            img_url = item.get("link", "")
            thumb = item.get("image", {}).get("thumbnailLink") or img_url
            source_url = item.get("image", {}).get("contextLink") or img_url
            domain = item.get("displayLink", "")
            prov = domain or "Google Search"

            valid, score, reason = _validate_and_score_image(title, img_url, source_url, entity_config)
            if valid:
                norm = _normalize_image_item(title, thumb, img_url, source_url, prov, score=score)
                if norm:
                    results.append(norm)
            else:
                _safe_log(f"Google CS rejected item '{title[:40]}': {reason}")
    except Exception as e:
        _safe_log(f"Google Custom Search API error: {e}")
    return results


# ---------------------------------------------------------------------------
# Provider 4: Google Serper Images API
# ---------------------------------------------------------------------------
def _search_serper_images(query: str, serper_key: str, entity_config: dict, num: int = 8) -> list[dict]:
    payload = json.dumps({"q": query, "num": min(num, 10)}).encode("utf-8")
    req = urllib.request.Request(
        "https://google.serper.dev/images",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-KEY": serper_key,
            "User-Agent": "NOVA-AI-Assistant/5.0",
        },
        method="POST",
    )
    results = []
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("images", [])[:num]:
            title = item.get("title", "")
            img_url = item.get("imageUrl", "")
            thumb = item.get("thumbnailUrl") or img_url
            source_url = item.get("link", "")
            domain = item.get("domain") or item.get("source", "")
            prov = domain or "Google Serper"

            valid, score, reason = _validate_and_score_image(title, img_url, source_url, entity_config)
            if valid:
                norm = _normalize_image_item(title, thumb, img_url, source_url, prov, score=score)
                if norm:
                    results.append(norm)
            else:
                _safe_log(f"Serper rejected item '{title[:40]}': {reason}")
    except Exception as e:
        _safe_log(f"Google Serper error: {e}")
    return results


# ---------------------------------------------------------------------------
# Provider 5: Openverse Public Search API (Zero-Key Fallback)
# ---------------------------------------------------------------------------
def _search_openverse_images(query: str, entity_config: dict, num: int = 8) -> list[dict]:
    encoded = urllib.parse.quote(query)
    url = f"https://api.openverse.org/v1/images/?q={encoded}&page_size={min(num, 10)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    )
    results = []
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("results", [])[:num]:
            title = item.get("title") or f"Photo of {query}"
            img_url = item.get("url", "")
            thumb = item.get("thumbnail") or img_url
            source_url = item.get("foreign_landing_url") or img_url
            source_name = item.get("source") or "Openverse"
            prov = f"Openverse ({source_name.capitalize()})" if source_name else "Openverse"

            valid, score, reason = _validate_and_score_image(title, img_url, source_url, entity_config)
            if valid:
                norm = _normalize_image_item(title, thumb, img_url, source_url, prov, score=score)
                if norm:
                    results.append(norm)
    except Exception as e:
        _safe_log(f"Openverse API error: {e}")
    return results


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        _safe_log(f"Handler error: {fmt % args}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        query = params.get("q", [""])[0] or params.get("query", [""])[0]
        self._execute_search(query)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
            query = data.get("query") or data.get("q") or data.get("prompt") or ""
        except Exception as e:
            return self._json(400, {"success": False, "error": f"Invalid request body: {e}", "images": []})

        self._execute_search(query)

    def _execute_search(self, raw_query: str):
        query = (raw_query or "").strip()
        if not query:
            return self._json(400, {"success": False, "error": "Search query is required.", "images": []})

        cleaned_query, entity_config = _clean_and_classify_query(query)
        search_type = "PERSON" if entity_config.get("is_person") else ("PLACE" if (entity_config.get("is_monument") or entity_config.get("search_type") == "PLACE") else ("NATURE" if (entity_config.get("is_nature") or entity_config.get("search_type") == "NATURE") else "OBJECT"))

        _safe_log(f"[NOVA Image Search]\nQuery: {query}\nDetected Entity: {cleaned_query}\nSearch Type: {search_type}\n")

        all_candidates: list[dict] = []
        seen_urls = set()

        def add_unique(items: list[dict]):
            for it in items:
                u = it.get("image_url", "")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    all_candidates.append(it)

        # Attempt 1: Direct Wikipedia Article Leads (Highest accuracy for exact entities)
        if entity_config and entity_config.get("wiki_articles"):
            wiki_lead_items = _fetch_wikipedia_exact_articles(entity_config["wiki_articles"], entity_config)
            if wiki_lead_items:
                add_unique(wiki_lead_items)

        # Attempt 1b: Dynamic Wikipedia Page Search for cleaned entity query
        if len(all_candidates) < 4:
            wiki_dyn_items = _search_wikipedia_dynamic(cleaned_query, entity_config, num=4)
            if wiki_dyn_items:
                add_unique(wiki_dyn_items)

        # Attempt 2: Search queries from entity config
        search_terms = entity_config.get("search_queries", [cleaned_query]) if entity_config else [cleaned_query]

        # Try Google Custom Search if configured
        google_api_key = _get_api_key(["IMAGE_SEARCH_API_KEY", "GOOGLE_SEARCH_API_KEY"])
        google_cx = _get_api_key(["IMAGE_SEARCH_ENGINE_ID", "GOOGLE_SEARCH_ENGINE_ID"])
        if google_api_key and google_cx:
            for term in search_terms[:2]:
                g_items = _search_google_custom_search(term, google_api_key, google_cx, entity_config, num=6)
                if g_items:
                    add_unique(g_items)

        # Try Serper if configured
        serper_key = _get_api_key("SERPER_API_KEY")
        if serper_key and len(all_candidates) < 6:
            for term in search_terms[:2]:
                s_items = _search_serper_images(term, serper_key, entity_config, num=6)
                if s_items:
                    add_unique(s_items)

        # Attempt 3: Wikimedia Commons for each search term
        if len(all_candidates) < 6:
            for term in search_terms:
                wm_items = _search_wikimedia_commons(term, entity_config, num=6)
                if wm_items:
                    add_unique(wm_items)
                if len(all_candidates) >= 8:
                    break

        # Attempt 4: Openverse fallback
        if len(all_candidates) < 4:
            ov_items = _search_openverse_images(cleaned_query, entity_config, num=6)
            if ov_items:
                add_unique(ov_items)

        # Sort candidate results by relevance score descending
        all_candidates.sort(key=lambda x: x.get("_score", 0), reverse=True)

        final_images = []
        for idx, c in enumerate(all_candidates[:8], 1):
            _safe_log(f"Result {idx}:\nTitle: {c['title']}\nScore: {c.get('_score', 0)}\nStatus: ACCEPTED\n")
            # Clean internal scoring metadata before returning JSON
            final_images.append({
                "title": c["title"],
                "thumbnail": c["thumbnail"],
                "image_url": c["image_url"],
                "source_url": c["source_url"],
                "provider": c["provider"]
            })

        _safe_log(f"Search complete: {len(final_images)} verified results returned for '{cleaned_query}'")

        if final_images:
            return self._json(200, {
                "success": True,
                "query": cleaned_query,
                "provider": final_images[0]["provider"] if final_images else "Web Search",
                "images": final_images
            })
        else:
            return self._json(200, {
                "success": False,
                "query": cleaned_query,
                "error": f"No verified real images found on the web matching '{cleaned_query}'.",
                "images": []
            })


    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, status_code: int, data: dict):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except Exception:
            body = json.dumps({"error": "Failed to serialize response."}).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)
