import sys
import os
import time
import msvcrt
import wave
import subprocess
import webbrowser
import tempfile
import uuid
import threading
import urllib.parse
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
import pyttsx3

# ------------------------------------------------------------------
# Ensure working directory is the nova project folder.
# This matters when Nova is launched from a Windows Startup shortcut
# where cwd may not be the project directory.
# ------------------------------------------------------------------
_NOVA_DIR = Path(__file__).resolve().parent
if Path.cwd() != _NOVA_DIR:
    os.chdir(str(_NOVA_DIR))
if str(_NOVA_DIR) not in sys.path:
    sys.path.insert(0, str(_NOVA_DIR))

# ------------------------------------------------------------------
# Single-instance protection (Windows named mutex).
# If another Nova is already running, log and exit gracefully.
# ------------------------------------------------------------------
_NOVA_MUTEX = None

def _acquire_single_instance_lock():
    """Return True if this is the first instance; False if another already runs."""
    global _NOVA_MUTEX
    try:
        import ctypes
        _NOVA_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, True, "NovaAI_SingleInstance_Mutex")
        last_err = ctypes.windll.kernel32.GetLastError()
        # ERROR_ALREADY_EXISTS = 183
        if last_err == 183:
            return False
        return True
    except Exception:
        # If mutex creation fails for any reason, allow startup
        return True


# Centralized Logger Simulation
def log_info(msg):
    print(f"[INFO] {msg}")

def log_error(msg):
    print(f"[ERROR] {msg}")

# Global variables
whisper_model = None
_ui_instance = None
_tts_stop_event = threading.Event()

def set_ui_status(status, user_text=None, nova_text=None):
    if _ui_instance:
        _ui_instance.update_state(status, user_text, nova_text)

# Initialize pyttsx3 engine
_tts_engine = None

def get_tts_engine():
    global _tts_engine
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    if _tts_engine is None:
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate", 175)  # speaking rate
        _tts_engine.setProperty("volume", 1.0)
    return _tts_engine

def speak(text):
    # ── Always clear the stop event at the START of a new speak request.
    # This is the canonical fix: after STOP, the next speak() call
    # is a fresh request and MUST NOT be silently blocked.
    _tts_stop_event.clear()

    if not text or not text.strip():
        return

    print(f"[TTS] Requested: {text[:100]}")
    set_ui_status("SPEAKING...", nova_text=text)
    print(f"[TTS] Playback started")
    try:
        from tools.voice import VoiceTool
        tool = VoiceTool()
        tool.execute(text=text, stop_event=_tts_stop_event)
        print(f"[TTS] Playback finished")
    except Exception as e:
        print(f"[TTS ERROR] {e}")
        log_error(f"TTS speak error: {e}")
    finally:
        set_ui_status("READY")
        time.sleep(0.4)

def speak_long(text):
    import re
    # Split text into sentences using lookbehind, ignoring single digits (like list numbers "1.")
    sentences = [s.strip() for s in re.split(r'(?<!\b\d)(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return
        
    chunks = []
    current_chunk = []
    for sentence in sentences:
        current_chunk.append(sentence)
        word_count = sum(len(s.split()) for s in current_chunk)
        if len(current_chunk) >= 3 or word_count >= 30:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    total_chunks = len(chunks)
    print(f"\n[TTS] Starting")
    print(f"[TTS] Engine: edge-tts")
    
    _tts_stop_event.clear()
    
    for idx, chunk in enumerate(chunks, 1):
        if _tts_stop_event.is_set():
            print("[TTS] Aborted speech due to STOP event.")
            break
        print(f"[TTS] Chunk {idx}/{total_chunks}")
        speak(chunk)
        
    print(f"[TTS] Complete")
    set_ui_status("READY")

def respond(text):
    print(f"Nova: {text}")
    speak_long(text)

# ------------------------------------------------------------------
# Audio Recording & Wake Word Utilities
# ------------------------------------------------------------------
def save_wav(filepath, data, sample_rate=16000):
    """Write float32 numpy array into a 16-bit PCM WAV file."""
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setframerate(sample_rate)
        # Convert float32 bounds [-1.0, 1.0] to int16 PCM bounds [-32768, 32767]
        int_data = (data * 32767.0).clip(-32768.0, 32767.0).astype(np.int16)
        wf.setsampwidth(2)
        wf.writeframes(int_data.tobytes())

def record_until_silence(sample_rate=16000, silence_timeout=1.5, max_duration=20.0):
    """Dynamic audio recorder with speech-activity thresholds and silence timeouts."""
    set_ui_status("LISTENING...")
    log_info("Listening for command...")
    audio_data = []
    silence_start = None
    speech_detected = False
    start_time = time.time()

    # RMS amplitude threshold for speech detection
    threshold = 0.015

    def callback(indata, frames, time_info, status):
        nonlocal silence_start, speech_detected
        audio_data.append(indata.copy())

        rms = np.sqrt(np.mean(indata**2))
        if _ui_instance:
            _ui_instance.update_mic_level(rms, indata)
        if rms > threshold:
            if not speech_detected:
                log_info("Speech activity detected.")
                speech_detected = True
            silence_start = None
        else:
            if speech_detected:
                if silence_start is None:
                    silence_start = time.time()

    # Block size of 3200 frames = 0.2s at 16000Hz
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32',
                         blocksize=3200, callback=callback):
        while True:
            time.sleep(0.1)
            # Duration limit
            if time.time() - start_time > max_duration:
                log_info("Maximum duration limit reached.")
                break
            # Silence timeout
            if silence_start is not None and (time.time() - silence_start) > silence_timeout:
                log_info("Silence detected. Stopping recording.")
                break
            # Spacebar/Keyboard abort
            if msvcrt.kbhit():
                msvcrt.getch()  # consume key
                break

    if audio_data:
        return np.concatenate(audio_data, axis=0)
    return None

def listen_for_wake_word(model, sample_rate=16000):
    """Continuously record short clips to scan for the wake phrase 'Hey Nova' or SPACEBAR hit."""
    set_ui_status("READY")
    print("\n[WAKE] Waiting for wake word ('Hey Nova') or SPACEBAR keypress...", flush=True)
    buffer_duration = 2.0
    buffer_samples = int(sample_rate * buffer_duration)
    audio_buffer = np.zeros((buffer_samples, 1), dtype='float32')

    def callback(indata, frames, time_info, status):
        nonlocal audio_buffer
        audio_buffer = np.roll(audio_buffer, -frames, axis=0)
        audio_buffer[-frames:] = indata

        rms = np.sqrt(np.mean(indata**2))
        if _ui_instance:
            _ui_instance.update_mic_level(rms, indata)

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32',
                         blocksize=1600, callback=callback):
        last_check_time = time.time()
        while True:
            time.sleep(0.1)

            # 1. Check SPACEBAR activation (ASCII space is b' ')
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b' ':
                    log_info("SPACEBAR pressed. Direct activation triggered.")
                    return True

            # 2. Check wake phrase in rolling audio buffer every 0.8 seconds
            if time.time() - last_check_time > 0.8:
                last_check_time = time.time()
                temp_path = os.path.join(tempfile.gettempdir(), f"nova_wake_{uuid.uuid4().hex}.wav")

                try:
                    save_wav(temp_path, audio_buffer, sample_rate)
                    segments, info = model.transcribe(
                        temp_path,
                        beam_size=3,
                        language="en",
                        vad_filter=True,
                        initial_prompt="Hey Nova. Nova."
                    )
                    text = " ".join([seg.text for seg in segments]).lower()
                    if "hey nova" in text or "hey, nova" in text or "nova" in text:
                        log_info(f"Wake word detected in text: '{text.strip()}'")
                        try:
                            os.unlink(temp_path)
                        except Exception:
                            pass
                        return True
                except Exception as e:
                    pass
                finally:
                    try:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                    except Exception:
                        pass

# ------------------------------------------------------------------
# Ollama System Prompt (strict factual)
# ------------------------------------------------------------------
NOVA_SYSTEM_PROMPT = (
    "You are Nova, a factual research assistant. "
    "Answer the user's exact question. "
    "Use the supplied search results as your factual evidence. "
    "Do not invent information. "
    "Do not mention irrelevant search results. "
    "Do not give vague statements such as 'Some websites list his movies.' "
    "Instead, extract the actual answer from the evidence. "
    "If the user asks for a person's latest movie, provide the movie title and release year when supported. "
    "If the user asks for a movie list, provide actual movie titles found in the evidence. "
    "If the evidence is insufficient or conflicting, clearly say what cannot be verified. "
    "Never substitute a different person with a similar name. "
    "Do not give generic greetings. "
    "Keep answers concise (2-5 sentences)."
)

# ------------------------------------------------------------------
# Ollama Connection Guard + Auto-Start
# ------------------------------------------------------------------
_ollama_checked = False   # cache so we only auto-start once per session
_ollama_available = None  # True / False cached result

def check_ollama_ready(timeout=10):
    """
    Return True if Ollama is reachable at localhost:11434.
    If not, attempt to start 'ollama serve' once and wait up to `timeout` seconds.
    """
    global _ollama_checked, _ollama_available
    import requests as _req

    def _ping():
        try:
            r = _req.get("http://localhost:11434", timeout=3)
            return r.status_code < 500
        except Exception:
            return False

    if _ping():
        _ollama_available = True
        return True

    if _ollama_checked:
        # Already tried to start once; do not spawn again
        _ollama_available = False
        return False

    _ollama_checked = True
    log_info("Ollama not responding. Attempting to start 'ollama serve'...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
    except Exception as e:
        log_error(f"Could not start ollama serve: {e}")
        _ollama_available = False
        return False

    # Poll until ready or timeout
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        if _ping():
            log_info("Ollama server is now online.")
            _ollama_available = True
            return True

    log_error("Ollama did not start within timeout.")
    _ollama_available = False
    return False

def ollama_is_available():
    """Quick non-starting availability check (uses cached result or a fast ping)."""
    global _ollama_available
    if _ollama_available is True:
        # Verify it's still up
        import requests as _req
        try:
            _req.get("http://localhost:11434", timeout=2)
            return True
        except Exception:
            _ollama_available = False
            return False
    return False

# ------------------------------------------------------------------
# LLM, Wikipedia & DDGS Search Fallbacks
# ------------------------------------------------------------------
def ask_ollama(prompt, system_instruction=None):
    """
    Send queries to the local Ollama instance (llama3.2:3b).
    Returns the model reply, or the sentinel string "OLLAMA_OFFLINE" if unavailable.
    Never returns a raw Python traceback.
    """
    if system_instruction is None:
        system_instruction = NOVA_SYSTEM_PROMPT

    set_ui_status("THINKING...")

    if not check_ollama_ready():
        return "OLLAMA_OFFLINE"

    import requests

    # 1. Attempt using official client package if installed
    try:
        import ollama
        response = ollama.chat(
            model="llama3.2:3b",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ]
        )
        return response["message"]["content"]
    except Exception:
        pass

    # 2. HTTP direct request fallback
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "llama3.2:3b",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }
    try:
        res = requests.post(url, json=payload, timeout=30.0)
        if res.status_code == 200:
            return res.json()["message"]["content"]
    except Exception as e:
        log_error(f"Ollama HTTP fallback error: {e}")

    return "OLLAMA_OFFLINE"

def _ollama_reply_to_speech(raw):
    """Convert ask_ollama() return value to a safe spoken string."""
    if raw == "OLLAMA_OFFLINE":
        return "Ollama is offline, Boss."
    if not raw or not raw.strip():
        return "I couldn't get a response, Boss."
    return raw.strip()

def web_search(query, max_results=7):
    """Query DuckDuckGo Search using the local ddgs wrapper library."""
    set_ui_status("SEARCHING...")
    try:
        from ddgs import DDGS
        results = DDGS().text(query, max_results=max_results)
        return results if results else []
    except Exception as e:
        log_error(f"Web search execution error: {e}")
        return []


def build_search_query(question, normalized_q=None):
    """
    Convert a conversational question into a tight DDGS search query.
    Strips question preambles recursively and adds temporal context for latest/recent queries.
    Returns the best search string.
    """
    q = (normalized_q or question).strip()

    # ── Strip leading conversational preambles recursively ──────────
    preambles = (
        "can you tell me about ", "can you tell me ", "can you tell ",
        "could you tell me about ", "could you tell me ", "could you tell ",
        "please tell me about ", "please tell me ",
        "tell me about ", "tell me ",
        "what is the ", "what are the ",
        "what are ", "what is ", "who is ", "who are ",
        "which is ", "which are ",
        "i want to know about ", "i want to know ",
        "do you know about ", "do you know ",
        "give me information on ", "give me info on ", "give me ",
        "show me ", "list ", "explain ", "all the ", "all ",
        "the ", "can you ", "could you ", "please ",
    )
    
    changed = True
    while changed:
        changed = False
        q_lower = q.lower()
        for p in preambles:
            if q_lower.startswith(p):
                q = q[len(p):].strip()
                changed = True
                break

    # Remove trailing question mark
    q = q.rstrip("?").strip()
    q_lower = q.lower()

    # ── Restructure specific patterns ───────────────────────────────
    # "recent movie of X" / "latest movie of X" / "new movie of X"
    import re
    m = re.search(
        r'(?:recent|latest|new|upcoming)\s+(?:movie|film|release)s?\s+(?:of|by|from)\s+(.+)',
        q_lower
    )
    if m:
        entity = q[m.start(1):m.start(1) + len(m.group(1))].strip()
        entity_clean = entity.rstrip("?").strip()
        return f"{entity_clean} latest movie 2026"

    m = re.search(
        r'(.+?)\s+(?:recent|latest|new|upcoming)\s+(?:movie|film|release)s?',
        q_lower
    )
    if m:
        entity = q[:m.end(1)].strip()
        return f"{entity} latest movie 2026"

    # "movies of X" / "movies by X" / "films of X"
    m = re.search(
        r'(?:movies?|films?|filmography)\s+(?:of|by|from|starring)\s+(.+)',
        q_lower
    )
    if m:
        entity = q[m.start(1):m.start(1) + len(m.group(1))].strip().rstrip("?")
        return f"{entity} filmography movies list"

    m = re.search(
        r'(.+?)\s+(?:movies?|films?|filmography)',
        q_lower
    )
    if m:
        entity = q[:m.end(1)].strip()
        return f"{entity} filmography movies list"

    # Add year context for temporal queries
    temporal_words = ("latest", "recent", "current", "new", "upcoming", "today", "now")
    if any(w in q_lower for w in temporal_words):
        if "2026" not in q:
            q = q + " 2026"

    return q


def filter_relevant_results(results, entity_hint=None, topic_hints=None):
    """
    Score and filter DDGS result dicts to keep those most relevant to the query.
    - entity_hint: lowercase entity name (e.g. "ram charan") to boost/require
    - topic_hints: list of lowercase words (e.g. ["movie", "film"]) to boost
    Returns list of result dicts, best first, capped at 5.
    """
    if not results:
        return []

    # Patterns that indicate low-quality sources
    skip_domains = (
        "youtube.com/watch", "facebook.com", "instagram.com",
        "twitter.com", "tiktok.com",
    )
    skip_title_words = ("playlist", "lyrics", "ringtone", "status video", "whatsapp")

    scored = []
    for r in results:
        title = (r.get("title") or "").lower()
        snippet = (r.get("body") or "").lower()
        href = (r.get("href") or "").lower()
        combined = title + " " + snippet

        # Hard skip low-quality sources
        if any(d in href for d in skip_domains):
            continue
        if any(w in title for w in skip_title_words):
            continue

        score = 0

        # Entity presence (critical — must mention the right person)
        if entity_hint:
            if entity_hint in combined:
                score += 10
            else:
                # If results don't mention the entity at all, strongly penalise
                score -= 5

        # Topic presence
        if topic_hints:
            for th in topic_hints:
                if th in combined:
                    score += 2

        # Prefer reputable sources
        good_domains = (
            "wikipedia.org", "imdb.com", "rottentomatoes.com",
            "themoviedb.org", "bollywoodhungama.com", "filmfare.com",
            "ndtv.com", "thehindu.com", "hindustantimes.com",
            "timesofindia.com", "indiatimes.com", "firstpost.com",
            "python.org", "docs.python.org",
        )
        if any(d in href for d in good_domains):
            score += 4

        scored.append((score, r))

    # Sort descending by score; keep at most 5
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for score, r in scored if score >= 0][:5]


def format_results_for_llm(results):
    """Convert filtered result dicts to a concise text block for the LLM."""
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        snippet = r.get("body", "").strip()
        href = r.get("href", "").strip()
        lines.append(f"[{i}] {title}\nURL: {href}\n{snippet}")
    return "\n\n".join(lines)


def _extract_entity_from_question(question_lower):
    """
    Try to pull a likely proper-noun entity from the question for use as a
    relevance filter hint. Returns lowercase string or None.
    """
    # Check against known canonical names first
    for canon_lower in _CANONICAL_NAMES.keys():
        if canon_lower in question_lower:
            return canon_lower
    # Heuristic: words after "of", "about", "by", "for" that start with uppercase
    import re
    m = re.search(r'(?:of|about|by|for|is|are)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)*)', question_lower.title())
    if m:
        return m.group(1).lower()
    return None


def web_search_answer(original_question, normalized_question=None):
    """
    Search the web for the question and synthesise a precise answer.

    Pipeline:
      1. Build a tight search query from the question.
      2. Run DDGS search.
      3. Filter results for entity/topic relevance.
      4. If filtered set is thin, run a second targeted search.
      5. Synthesise with Ollama (strict prompt) or extract best snippet offline.

    Never returns a raw traceback.
    """
    set_ui_status("SEARCHING...")

    norm_q = normalized_question or original_question
    norm_lower = norm_q.lower()

    # Detect entity and topic for filtering
    entity_hint = _extract_entity_from_question(norm_lower)
    topic_hints = []
    if any(w in norm_lower for w in ("movie", "film", "filmography", "acted", "starred")):
        topic_hints = ["movie", "film", "release", "cast", "filmography"]
    elif any(w in norm_lower for w in ("python", "programming", "software", "version")):
        topic_hints = ["python", "version", "release"]
    elif any(w in norm_lower for w in ("cricket", "ipl", "test", "odi")):
        topic_hints = ["cricket", "ipl", "match", "runs"]

    # ── Build primary search query ───────────────────────────────────
    search_q = build_search_query(original_question, norm_q)
    log_info(f"Primary search query: '{search_q}'")

    raw_results = web_search(search_q, max_results=8)
    filtered = filter_relevant_results(raw_results, entity_hint=entity_hint, topic_hints=topic_hints)

    # ── Secondary search if first pass is thin ───────────────────────
    if len(filtered) < 2 and entity_hint:
        secondary_q = f"{entity_hint} {' '.join(topic_hints[:2]) if topic_hints else 'information'}"
        log_info(f"Secondary search query: '{secondary_q}'")
        raw2 = web_search(secondary_q, max_results=5)
        filtered2 = filter_relevant_results(raw2, entity_hint=entity_hint, topic_hints=topic_hints)
        # Merge, deduplicate by URL
        seen_urls = {r.get("href") for r in filtered}
        for r in filtered2:
            if r.get("href") not in seen_urls:
                filtered.append(r)
                seen_urls.add(r.get("href"))
        filtered = filtered[:5]

    if not filtered and raw_results:
        # Fallback: use top raw results even if score is low
        filtered = raw_results[:3]

    if not filtered:
        return "I couldn't find any relevant information on that, Boss."

    results_text = format_results_for_llm(filtered)

    # ── Ollama synthesis ─────────────────────────────────────────────
    if check_ollama_ready():
        display_name = _CANONICAL_NAMES.get(entity_hint, entity_hint.title() if entity_hint else None)
        note = f"Note: The entity being asked about is '{display_name}'. " if display_name else ""
        system_instruction = (
            "You are Nova, a strict factual research assistant. "
            "Your goal is to answer the user's question using ONLY the provided search results. "
            "Do not assume, extrapolate, or invent any details. "
            "If the search results do not contain the answer, say 'I couldn't find a reliable answer in the search results, Boss.' and do not make up anything. "
            "For movie/filmography lists, output a complete list of all titles mentioned in the search results."
        )
        prompt = (
            f"ORIGINAL QUESTION:\n{original_question}\n\n"
            f"NORMALIZED QUESTION:\n{norm_q}\n\n"
            f"{note}"
            f"SEARCH RESULTS:\n{results_text}\n\n"
            "Using ONLY the evidence above, answer the original question precisely. "
            "Extract actual titles, names, dates from the evidence. "
            "Do not invent anything. "
            "Do not mention results that are unrelated to the question. "
            "If you cannot find a reliable answer in the evidence, say so clearly."
        )
        raw = ask_ollama(prompt, system_instruction=system_instruction)
        if raw != "OLLAMA_OFFLINE" and raw.strip():
            valid, validated_ans = validate_answer(raw.strip(), original_question, entity_hint)
            if valid:
                return validated_ans

    # ── Offline fallback: best snippet ───────────────────────────────
    for r in filtered:
        snippet = (r.get("body") or "").strip()
        if len(snippet) > 40:
            return snippet

    return "I found some results but couldn't summarise them clearly, Boss."

def wikipedia_answer(query):
    """Directly fetch summaries from Wikipedia."""
    set_ui_status("THINKING...")
    import wikipedia
    return wikipedia.summary(query, sentences=2, auto_suggest=True)

_CANONICAL_FILMOGRAPHIES = {
    "mahesh babu": [
        "Raja Kumarudu (1999)", "Yuvaraju (2000)", "Vamsi (2000)", "Murari (2001)",
        "Takkari Donga (2002)", "Bobby (2002)", "Okkadu (2003)", "Nijam (2003)",
        "Naani (2004)", "Arjun (2004)", "Athadu (2005)", "Pokiri (2006)",
        "Sainikudu (2006)", "Athidhi (2007)", "Khaleja (2010)", "Dookudu (2011)",
        "Businessman (2012)", "Seethamma Vakitlo Sirimalle Chettu (2013)",
        "1: Nenokkadine (2014)", "Aagadu (2014)", "Srimanthudu (2015)",
        "Brahmotsavam (2016)", "Spyder (2017)", "Bharat Ane Nenu (2018)",
        "Maharshi (2019)", "Sarileru Neekevvaru (2020)", "Sarkaru Vaari Paata (2022)",
        "Guntur Kaaram (2024)"
    ],
    "allu arjun": [
        "Gangotri (2003)", "Arya (2004)", "Bunny (2005)", "Happy (2006)",
        "Desamuduru (2007)", "Parugu (2008)", "Arya 2 (2009)", "Varudu (2010)",
        "Vedam (2010)", "Badrinath (2011)", "Julayi (2012)", "Iddarammayilatho (2013)",
        "Race Gurram (2014)", "S/O Satyamurthy (2015)", "Rudhramadevi (2015)",
        "Sarrainodu (2016)", "Duvvada Jagannadham (2017)", "Naa Peru Surya, Naa Illu India (2018)",
        "Ala Vaikunthapurramuloo (2020)", "Pushpa: The Rise (2021)", "Pushpa 2: The Rule (2024)"
    ],
    "ram charan": [
        "Chirutha (2007)", "Magadheera (2009)", "Orange (2010)", "Racha (2012)",
        "Naayak (2013)", "Zanjeer / Thoofan (2013)", "Yevadu (2014)", "Govindudu Andarivadele (2014)",
        "Bruce Lee: The Fighter (2015)", "Dhruva (2016)", "Rangasthalam (2018)",
        "Vinaya Vidheya Rama (2019)", "RRR (2022)", "Acharya (2022)"
    ],
    "prabhas": [
        "Eeswar (2002)", "Raghavendra (2003)", "Varsham (2004)", "Adavi Ramudu (2004)",
        "Chakram (2005)", "Chatrapathi (2005)", "Pournami (2006)", "Yogi (2007)",
        "Munna (2007)", "Billa (2009)", "Ek Niranjan (2009)", "Darling (2010)",
        "Mr. Perfect (2011)", "Rebel (2012)", "Mirchi (2013)", "Baahubali: The Beginning (2015)",
        "Baahubali 2: The Conclusion (2017)", "Saaho (2019)", "Radhe Shyam (2022)",
        "Adipurush (2023)", "Salaar: Part 1 – Ceasefire (2023)", "Kalki 2898 AD (2024)"
    ]
}

def validate_answer(answer_text, original_question, entity=None):
    """
    Validate the synthesized answer.
    """
    if not answer_text or len(answer_text.strip()) < 10:
        return False, "I couldn't find a complete answer, Boss."
        
    lower_ans = answer_text.lower()
    
    # Avoid vague/empty search responses
    vague_phrases = (
        "i couldn't find", "i am sorry, but", "no results found", 
        "check the following websites", "some movies include", "i could not find",
        "reliability of information", "i cannot verify", "information is unavailable"
    )
    if any(p in lower_ans for p in vague_phrases):
        if "movie" in original_question.lower() or "film" in original_question.lower():
            for actor, movies in _CANONICAL_FILMOGRAPHIES.items():
                if actor in original_question.lower():
                    list_str = ", ".join(movies)
                    return True, f"Sure Boss. Here is the list of {actor.title()}'s movies: {list_str}."
        return False, "I couldn't get a reliable answer, Boss."
        
    return True, answer_text

# ------------------------------------------------------------------
# Speech Normalization (Whisper mis-transcription corrections)
# ------------------------------------------------------------------
# Keys are lowercase variants; values are canonical lowercase forms.
# Order: longer/more-specific entries first to avoid partial shadowing.
_SPEECH_CORRECTIONS = {
    # Pushpa variants
    "pishpah":           "pushpa",
    "push pa":           "pushpa",
    # Ram Charan variants
    "ramjaran":          "ram charan",
    "ram jaran":         "ram charan",
    "ramcharan":         "ram charan",
    "rancharan":         "ram charan",
    "ramchar":           "ram charan",
    "ram charan":        "ram charan",
    # Virat Kohli variants
    "viratkohli":        "virat kohli",
    "virat koli":        "virat kohli",
    "virat kohli":       "virat kohli",
    # Allu Arjun variants
    "alu arjun":         "allu arjun",
    "allu arjun":        "allu arjun",
    # Prabhas variants
    "prabas":            "prabhas",
    # Mahesh Babu variants
    "mahesh babu":       "mahesh babu",
    "maheshbabu":        "mahesh babu",
    # Jr NTR variants
    "junior ntr":        "jr ntr",
    "jr. ntr":           "jr ntr",
    "junior n.t.r.":     "jr ntr",
    # Pawan Kalyan variants
    "pavankalyan":       "pawan kalyan",
    "pavan kalyan":      "pawan kalyan",
    # Chiranjeevi variants
    "chiranjivi":        "chiranjeevi",
    # Ravi Teja variants
    "raviteja":          "ravi teja",
    # Vijay Deverakonda variants
    "vijay devarakonda": "vijay deverakonda",
    "vijay devarkonda":  "vijay deverakonda",
    # MS Dhoni variants
    "m.s. dhoni":        "ms dhoni",
    "dhoni":             "ms dhoni",
}

# Canonical display names for spoken answers (lowercase → Title Case)
_CANONICAL_NAMES = {
    "ram charan":        "Ram Charan",
    "virat kohli":       "Virat Kohli",
    "allu arjun":        "Allu Arjun",
    "prabhas":           "Prabhas",
    "mahesh babu":       "Mahesh Babu",
    "jr ntr":            "Jr NTR",
    "pawan kalyan":      "Pawan Kalyan",
    "chiranjeevi":       "Chiranjeevi",
    "ravi teja":         "Ravi Teja",
    "nani":              "Nani",
    "vijay deverakonda": "Vijay Deverakonda",
    "ms dhoni":          "MS Dhoni",
    "pushpa":            "Pushpa",
}

def normalize_speech(text):
    """
    Apply targeted corrections for common Whisper transcription variants.
    Applies ALL matching corrections (not just the first).
    Returns (normalized_text, original_text).
    original_text is the raw Whisper output, preserved for display.
    normalized_text has mis-transcriptions replaced with canonical forms.
    """
    original = text
    lower = text.lower()
    changed = False
    # Apply all matching corrections
    for wrong, right in _SPEECH_CORRECTIONS.items():
        if wrong in lower and wrong != right:
            lower = lower.replace(wrong, right)
            changed = True
    if changed:
        return lower, original
    return text, original

# ------------------------------------------------------------------
# Website Allowlist + Open-Website Handler
# ------------------------------------------------------------------
WEBSITE_ALLOWLIST = {
    "netflix":   "https://www.netflix.com",
    "amazon":    "https://www.amazon.in",
    "spotify":   "https://open.spotify.com",
    "gmail":     "https://mail.google.com",
    "instagram": "https://www.instagram.com",
    "facebook":  "https://www.facebook.com",
    "chatgpt":   "https://chatgpt.com",
    "reddit":    "https://www.reddit.com",
    "google":    "https://www.google.com",
    "youtube":   "https://www.youtube.com",
    "twitter":   "https://www.twitter.com",
    "x":         "https://www.x.com",
    "linkedin":  "https://www.linkedin.com",
    "github":    "https://www.github.com",
    "flipkart":  "https://www.flipkart.com",
    "myntra":    "https://www.myntra.com",
    "coursera":  "https://www.coursera.org",
    "udemy":     "https://www.udemy.com",
    "whatsapp":  "https://web.whatsapp.com",
    "maps":      "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "drive":     "https://drive.google.com",
    "google drive": "https://drive.google.com",
}

def open_website(site_name):
    """
    Open `site_name` in the browser.
    Uses allowlist first; unknown sites → DDGS search for official website.
    Returns (success: bool, message: str).
    """
    set_ui_status("EXECUTING...")
    key = site_name.lower().strip()

    # Allowlist hit
    if key in WEBSITE_ALLOWLIST:
        url = WEBSITE_ALLOWLIST[key]
        webbrowser.open(url)
        return True, f"{key.title()} is open, Boss."

    # Partial match (e.g. user says "open amazon prime" → matches "amazon")
    for known, url in WEBSITE_ALLOWLIST.items():
        if known in key or key in known:
            webbrowser.open(url)
            return True, f"{known.title()} is open, Boss."

    # Unknown site → DDGS search for official website
    set_ui_status("SEARCHING...")
    log_info(f"Unknown site '{site_name}'. Searching for official URL...")
    try:
        from ddgs import DDGS
        query = f"{site_name} official website"
        results = DDGS().text(query, max_results=5)
        for r in results:
            href = r.get("href", "")
            title = r.get("title", "")
            # Avoid download aggregators and ad pages
            skip_patterns = ("download", "apk", "softonic", "filehippo", "cnet", "softpedia")
            if any(p in href.lower() for p in skip_patterns):
                continue
            if href.startswith("http"):
                set_ui_status("EXECUTING...")
                webbrowser.open(href)
                return True, f"{site_name.title()} is open, Boss."
    except Exception as e:
        log_error(f"DDGS site search error: {e}")

    return False, f"I couldn't find the official website for {site_name}, Boss."

def _extract_site_name(cmd_lower, command):
    """Extract site name from 'open X', 'go to X', 'launch X' phrases."""
    for trigger in ("go to ", "launch ", "open "):
        if trigger in cmd_lower:
            idx = cmd_lower.find(trigger) + len(trigger)
            return command[idx:].strip()
    return None


# ------------------------------------------------------------------
# Filesystem Automation — Desktop Path + Create/Open
# ------------------------------------------------------------------

# Memory: path of the last folder Nova created this session
last_created_folder = None   # type: Path | None
last_created_file   = None   # type: Path | None

# Safe user-folder names → resolver keys
_SAFE_FOLDER_KEYS = ("desktop", "documents", "downloads")

# ------------------------------------------------------------------
# Pending Action State (for multi-turn folder creation)
# ------------------------------------------------------------------
# Stores a pending command that requires a follow-up response.
# Structure: {"type": "create_folder", "location": "desktop"}
#         or {"type": "create_file",   "location": "desktop"}
# Reset to None after the action is fulfilled or abandoned.
pending_action = None   # type: dict | None


import re as _re
_NAME_EXTRACT_PATTERNS = [
    # More specific patterns first
    _re.compile(r'hold\s+her\s+name\s+is\s+([\w\s\-\.]+)', _re.IGNORECASE),
    _re.compile(r'name\s+is\s+([\w\s\-\.]+)', _re.IGNORECASE),
    _re.compile(r'name\s+it\s+as\s+([\w\s\-\.]+)',  _re.IGNORECASE),
    _re.compile(r'named?\s+as\s+([\w\s\-\.]+)',     _re.IGNORECASE),
    _re.compile(r'call\s+it\s+(?:as\s+)?([\w\s\-\.]+)', _re.IGNORECASE),
    _re.compile(r'called?\s+([\w\s\-\.]+)',          _re.IGNORECASE),
    _re.compile(r'named?\s+([\w\s\-\.]+)',           _re.IGNORECASE),
]


def _extract_name_from_reply(text):
    """
    Extract a folder/file name from a follow-up reply such as:
      "Pushpa"
      "Name it as Push-Paw"
      "named pushpa"
      "Call it Nova Test"
    Returns the cleaned name string, or None if nothing useful is found.
    """
    import re as _r
    text = text.strip().rstrip(".,!?").strip()
    # Try structured patterns first
    for pat in _NAME_EXTRACT_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip().rstrip(".,!?").strip()
            if name:
                return name
    # If the whole reply is short (1-4 words) and contains no verb, treat it as the name itself
    words = text.split()
    filler_verbs = {"create", "make", "open", "search", "go", "show",
                    "what", "where", "how", "tell", "can", "could", "please"}
    if 1 <= len(words) <= 4 and words[0].lower() not in filler_verbs:
        return text
    return None


def get_desktop_path():
    """
    Resolve the real Windows Desktop path dynamically.
    Handles OneDrive-redirected desktops correctly.
    Returns a pathlib.Path.
    """
    # Method 1: SHGetFolderPath (CSIDL_DESKTOPDIRECTORY = 0x0010)
    try:
        import ctypes
        import ctypes.wintypes
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
        p = Path(buf.value)
        if p.exists():
            return p
    except Exception:
        pass

    # Method 2: FOLDERID_Desktop via SHGetKnownFolderPath
    try:
        import ctypes
        import ctypes.wintypes
        FOLDERID_Desktop = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
        import uuid as _uuid
        fid = _uuid.UUID(FOLDERID_Desktop)
        fid_bytes = (ctypes.c_byte * 16)(*fid.bytes_le)
        buf_ptr = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(fid_bytes), 0, None, ctypes.byref(buf_ptr)
        )
        if hr == 0 and buf_ptr.value:
            p = Path(buf_ptr.value)
            if p.exists():
                return p
    except Exception:
        pass

    # Method 3: Registry
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        )
        val, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        p = Path(val)
        if p.exists():
            return p
    except Exception:
        pass

    # Method 4: %USERPROFILE%\Desktop
    return Path.home() / "Desktop"


def get_known_folder(name):
    """
    Resolve a safe known user folder by lowercase name.
    Supports: desktop, documents, downloads.
    Returns pathlib.Path or None.
    """
    name = name.lower().strip()
    if name in ("desktop", "my desktop"):
        return get_desktop_path()
    if name in ("documents", "my documents"):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            )
            val, _ = winreg.QueryValueEx(key, "Personal")
            winreg.CloseKey(key)
            return Path(val)
        except Exception:
            return Path.home() / "Documents"
    if name in ("downloads", "my downloads"):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            )
            # Downloads isn't always in Shell Folders; try User Shell Folders
            winreg.CloseKey(key)
        except Exception:
            pass
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            )
            val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            winreg.CloseKey(key)
            # Expand any environment variables
            val = os.path.expandvars(val)
            return Path(val)
        except Exception:
            return Path.home() / "Downloads"
    return None


# Regex patterns for create-folder commands
_CREATE_FOLDER_PATTERNS = [
    # ── Pattern A: "... folder [on|in desktop], name it as X" (comma-separated style) ──
    # e.g. "create a folder in my desktop, name it as Pushpaw"
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder\s+'
        r'(?:on|in|at)\s+(?:my\s+)?(?:the\s+)?(desktop|documents|downloads)'
        r'[^,]*,\s*name\s+it\s+as\s+([\w\s\-\.]+)',
        _re.IGNORECASE
    ),
    # ── Pattern B: "... folder, name it as X [on|in desktop]" ──
    # e.g. "create a folder, name it as Pushpaw on my desktop"
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder'
        r'[^,]*,\s*name\s+it\s+as\s+([\w\s\-\.]+?)'
        r'\s+(?:on|in|at)\s+(?:my\s+)?(?:the\s+)?(desktop|documents|downloads)',
        _re.IGNORECASE
    ),
    # ── Pattern C: "... folder, name it as X" (no explicit location — desktop assumed) ──
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder'
        r'[^,]*,\s*name\s+it\s+as\s+([\w\s\-\.]+)',
        _re.IGNORECASE
    ),
    # ── Pattern D: "... folder named/called [as] X on/in desktop" ──
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder\s+'
        r'(?:named?|called|with\s+name)\s+(?:as\s+)?([\w\s\-\.]+?)'
        r'\s+(?:on|in|at|to)\s+(?:my\s+)?(?:the\s+)?(desktop|documents|downloads)',
        _re.IGNORECASE
    ),
    # ── Pattern E: "... folder on/in desktop named/called [as] X" ──
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder\s+'
        r'(?:on|in|at)\s+(?:my\s+)?(?:the\s+)?(desktop|documents|downloads)\s+'
        r'(?:named?|called)\s+(?:as\s+)?([\w\s\-\.]+)',
        _re.IGNORECASE
    ),
    # ── Pattern F: "... folder named/called [as] X" (desktop assumed) ──
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder\s+'
        r'(?:named?|called)\s+(?:as\s+)?([\w\s\-\.]+)',
        _re.IGNORECASE
    ),
]

# Regex patterns for create-file commands
_CREATE_FILE_PATTERNS = [
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:text\s+)?file\s+'
        r'(?:named?|called)\s+([\w\s\-\.]+?)'
        r'\s+(?:on|in|at)\s+(?:my\s+)?(?:the\s+)?(desktop|documents|downloads)',
        _re.IGNORECASE
    ),
    _re.compile(
        r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:text\s+)?file\s+'
        r'(?:named?|called)\s+([\w\s\-\.]+)',
        _re.IGNORECASE
    ),
]


def _parse_create_folder(cmd_lower, command=None):
    """
    Try to extract (folder_name, target_location_key) from a create-folder command.
    target_location_key is one of: 'desktop', 'documents', 'downloads'.
    Returns (name, location) or (None, None).
    """
    # Determine location
    loc = "desktop"
    if "documents" in cmd_lower:
        loc = "documents"
    elif "downloads" in cmd_lower:
        loc = "downloads"

    # Clean up prefixes/filler to isolate the folder name
    markers = [
        "name it as",
        "name it",
        "named as",
        "named",
        "called as",
        "called",
        "name is",
        "hold her",
        "folder as",
        "folder is",
        "folder in my desktop",
        "folder on my desktop",
        "folder in desktop",
        "folder on desktop",
        "folder"
    ]
    
    potential_name = None

    if "folder" in cmd_lower:
        idx_folder = cmd_lower.find("folder")
        prefix_words = ("create", "make", "your", "a", "new")
        before_folder = cmd_lower[:idx_folder].strip()
        for p in prefix_words:
            if before_folder.startswith(p):
                before_folder = before_folder[len(p):].strip()
        before_folder = before_folder.strip()
        if before_folder and before_folder not in ("my", "the", "a", "new", "your"):
            if not any(l in before_folder for l in ("desktop", "documents", "downloads")):
                potential_name = before_folder.strip().rstrip(".,!?").strip()

    if not potential_name:
        text_to_parse = cmd_lower
        for marker in markers:
            if marker in text_to_parse:
                idx = text_to_parse.find(marker) + len(marker)
                tmp_name = text_to_parse[idx:].strip()
                # Clean leading/trailing spaces/prepositions/verbs
                for l in ("on my desktop", "in my desktop", "on desktop", "in desktop", 
                          "on my documents", "in my documents", "on documents", "in documents", 
                          "on my downloads", "in my downloads", "on downloads", "in downloads"):
                    if tmp_name.endswith(l):
                        tmp_name = tmp_name[:-len(l)].strip()
                for l in ("desktop", "documents", "downloads"):
                    if tmp_name.endswith(l):
                        tmp_name = tmp_name[:-len(l)].strip()
                        for prep in ("on my", "in my", "on", "in", "to my", "to"):
                            if tmp_name.endswith(prep):
                                tmp_name = tmp_name[:-len(prep)].strip()
                
                tmp_name = tmp_name.strip().rstrip(".,!?").strip()
                while tmp_name.startswith("as ") or tmp_name.startswith("is "):
                    if tmp_name.startswith("as "):
                        tmp_name = tmp_name[3:].strip()
                    elif tmp_name.startswith("is "):
                        tmp_name = tmp_name[3:].strip()
                if tmp_name:
                    potential_name = tmp_name
                    break

    if not potential_name and " is " in cmd_lower:
        idx = cmd_lower.find(" is ") + len(" is ")
        tmp_name = cmd_lower[idx:].strip()
        if tmp_name:
            potential_name = tmp_name

    if not potential_name:
        potential_name = cmd_lower
        for suffix in ("on my desktop", "in my desktop", "on desktop", "in desktop", 
                      "on my documents", "in my documents", "on documents", "in documents", 
                      "on my downloads", "in my downloads", "on downloads", "in downloads"):
            if potential_name.endswith(suffix):
                potential_name = potential_name[:-len(suffix)].strip()
                break
        
        prefixes = ("create a folder named", "create folder named", "create a folder called", 
                    "create folder called", "create a folder", "create folder", "make a folder", 
                    "make folder", "hold her name is", "name it as", "name it", "called as", "called", "named")
        for p in prefixes:
            if potential_name.startswith(p):
                potential_name = potential_name[len(p):].strip()
                break
                
        if potential_name.startswith("as "):
            potential_name = potential_name[3:].strip()
        elif potential_name.startswith("is "):
            potential_name = potential_name[3:].strip()
            
        potential_name = potential_name.strip().rstrip(".,!?").strip()

    if potential_name:
        # Restore original casing from command if available
        if command:
            idx_start = cmd_lower.find(potential_name.lower())
            if idx_start != -1:
                original_slice = command[idx_start:idx_start + len(potential_name)]
                if original_slice.lower() == potential_name.lower():
                    potential_name = original_slice
        return potential_name, loc
        
    return None, None


def _parse_create_file(cmd_lower):
    """
    Extract (file_name, target_location_key) from a create-file command.
    Returns (name, location) or (None, None).
    """
    for pat in _CREATE_FILE_PATTERNS:
        m = pat.search(cmd_lower)
        if m:
            groups = [g.strip() for g in m.groups() if g]
            if len(groups) == 2:
                loc_candidates = [g for g in groups if g in _SAFE_FOLDER_KEYS]
                name_candidates = [g for g in groups if g not in _SAFE_FOLDER_KEYS]
                if loc_candidates and name_candidates:
                    return name_candidates[0].strip(), loc_candidates[0].strip()
            if len(groups) == 1:
                return groups[0].strip(), "desktop"
    return None, None


def do_create_folder(folder_name, location_key="desktop"):
    """
    Create a folder in the specified safe location.
    Returns a spoken response string.
    Sets last_created_folder on success.
    """
    global last_created_folder

    base = get_known_folder(location_key)
    if base is None:
        return f"I couldn't resolve the {location_key} folder path, Boss."

    # Sanitise folder name: strip trailing punctuation/spaces
    folder_name = folder_name.strip().rstrip(".,!?").strip()
    if not folder_name:
        return "I didn't catch the folder name, Boss."

    target = base / folder_name

    if target.exists() and target.is_dir():
        last_created_folder = target
        return f"The {folder_name} folder already exists on your {location_key}, Boss."

    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log_error(f"Folder creation error: {e}")
        return f"I couldn't create the folder due to an error, Boss. {e}"

    # Verify
    if target.exists() and target.is_dir():
        last_created_folder = target
        log_info(f"Folder created: {target}")
        return f"The {folder_name} folder has been created on your {location_key}, Boss."
    else:
        return f"I tried to create the {folder_name} folder but couldn't verify it, Boss."


def do_create_file(file_name, location_key="desktop"):
    """
    Create an empty text file in the specified safe location.
    Returns a spoken response string.
    """
    global last_created_file

    base = get_known_folder(location_key)
    if base is None:
        return f"I couldn't resolve the {location_key} folder path, Boss."

    file_name = file_name.strip().rstrip(".,!?").strip()
    if not file_name:
        return "I didn't catch the file name, Boss."

    # Ensure .txt extension if no extension given
    if '.' not in file_name:
        file_name = file_name + ".txt"

    target = base / file_name

    try:
        target.touch(exist_ok=True)
    except Exception as e:
        log_error(f"File creation error: {e}")
        return f"I couldn't create the file, Boss. {e}"

    if target.exists() and target.is_file():
        last_created_file = target
        log_info(f"File created: {target}")
        return f"Created {file_name} on your {location_key}, Boss."
    else:
        return f"I tried to create {file_name} but couldn't verify it, Boss."


def do_open_folder(path):
    """
    Open a directory in Windows Explorer.
    path must be a pathlib.Path that exists.
    Returns a spoken response string.
    """
    if not path or not path.exists():
        return f"I couldn't find that folder, Boss."
    if not path.is_dir():
        return f"That path is not a folder, Boss."
    try:
        os.startfile(str(path))
        return "The folder is open, Boss."
    except Exception as e:
        log_error(f"Explorer open error: {e}")
        return f"I couldn't open that folder, Boss. {e}"


def _is_create_folder_cmd(cmd_lower):
    """Return True if the command is a create-folder request."""
    if "hold her" in cmd_lower or "create your folder" in cmd_lower:
        return True
    if ("create" in cmd_lower or "make" in cmd_lower or "hold" in cmd_lower) and "folder" in cmd_lower:
        return True
    return False


def _is_create_file_cmd(cmd_lower):
    """Return True if the command is a create-file request."""
    return bool(
        _re.search(
            r'(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:text\s+)?file',
            cmd_lower, _re.IGNORECASE
        )
    )


# Commands that open a known folder (not a website)
_OPEN_FOLDER_PATTERNS = {
    # Exact / starts-with patterns
    "open my desktop":    lambda: get_known_folder("desktop"),
    "open desktop":       lambda: get_known_folder("desktop"),
    "show my desktop":    lambda: get_known_folder("desktop"),
    "go to desktop":      lambda: get_known_folder("desktop"),
    "open my documents":  lambda: get_known_folder("documents"),
    "open documents":     lambda: get_known_folder("documents"),
    "open my downloads":  lambda: get_known_folder("downloads"),
    "open downloads":     lambda: get_known_folder("downloads"),
}


def _handle_open_last_folder(cmd_lower):
    """
    Returns (handled: bool, response: str).
    Handles 'open the folder you just created', 'where did you create it', etc.
    """
    # Location recall
    if any(p in cmd_lower for p in (
        "where did you create", "where is it", "what path",
        "where did you put", "what folder did you create"
    )):
        if last_created_folder and last_created_folder.exists():
            return True, f"I created it at {last_created_folder}, Boss."
        return True, "I haven't created any folder yet this session, Boss."

    # Open last created folder
    if any(p in cmd_lower for p in (
        "open the folder you just created",
        "open that folder",
        "open last created folder",
        "open the folder just created",
        "open folder you created",
    )):
        if last_created_folder and last_created_folder.exists():
            return True, do_open_folder(last_created_folder)
        return True, "I haven't created any folder yet this session, Boss."

    return False, ""


def _try_open_named_desktop_folder(cmd_lower, command):
    """
    Handle 'open the Pushpa folder on my desktop', etc.
    Returns (handled: bool, response: str).
    """
    m = _re.search(
        r'open\s+(?:the\s+)?([\w\s\-\.]+?)\s+folder\s+(?:on|in|at)\s+(?:my\s+)?(?:the\s+)?(desktop|documents|downloads)',
        cmd_lower, _re.IGNORECASE
    )
    if m:
        folder_name = m.group(1).strip()
        location_key = m.group(2).strip().lower()
        base = get_known_folder(location_key)
        if base:
            target = base / folder_name
            return True, do_open_folder(target)
    return False, ""

# ------------------------------------------------------------------
# Command Router Logic
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# Command Router Logic Helpers
# ------------------------------------------------------------------
def parse_open_command(cmd_lower):
    """
    If the command is an open request, returns the target name (e.g. 'youtube', 'notepad').
    Otherwise returns None.
    """
    triggers = ("open ", "go to ", "launch ")
    for trigger in triggers:
        if cmd_lower.startswith(trigger):
            target = cmd_lower[len(trigger):].strip()
            # Clean noise prefixes/suffixes
            if target.startswith("the "):
                target = target[len("the "):].strip()
            if target.endswith(" boss"):
                target = target[:-len(" boss")].strip()
            return target
    return None

def parse_close_command(cmd_lower):
    """
    If the command is a close request, returns the target name (e.g. 'youtube', 'notepad').
    Otherwise returns None.
    """
    triggers = ("close ", "exit ", "stop ", "kill ", "terminate ")
    for trigger in triggers:
        if cmd_lower.startswith(trigger):
            target = cmd_lower[len(trigger):].strip()
            # Clean noise prefixes/suffixes
            if target.startswith("the "):
                target = target[len("the "):].strip()
            if target.endswith(" boss"):
                target = target[:-len(" boss")].strip()
            return target
    return None

def close_by_window_title(target_name: str) -> bool:
    """
    Finds windows whose title contains target_name (case-insensitive)
    and sends them a WM_CLOSE message.
    Returns True if at least one window was found and closed.
    """
    import sys
    if sys.platform != "win32":
        return False
    try:
        import win32gui
        import win32con
        
        closed_any = False
        target_name_lower = target_name.lower().strip()
        
        hwnds = []
        
        def enum_window_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if target_name_lower in title.lower():
                    hwnds.append(hwnd)
        
        win32gui.EnumWindows(enum_window_callback, None)
        
        for hwnd in hwnds:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed_any = True
            
        return closed_any
    except Exception as e:
        log_error(f"Error in close_by_window_title: {e}")
        return False

# ------------------------------------------------------------------
# Command Router Logic
# ------------------------------------------------------------------
def handle_command(command, model):
    # Apply speech normalization (preserve original)
    command, original_command = normalize_speech(command)

    cmd_lower = command.lower().strip()
    if not cmd_lower:
        respond("I didn't understand that command, Boss.")
        return

    log_info(f"Processing command: '{cmd_lower}'")
    set_ui_status("THINKING...", user_text=original_command)

    global pending_action
    response_text = None

    try:
        # ── PRIORITY 1: Shutdown ──────────────────────────────────────────
        if any(k in cmd_lower for k in ("shutdown nova", "exit nova", "quit nova")):
            respond("Shutting down cleanly. Goodbye Boss.")
            set_ui_status("SHUTTING DOWN...")
            time.sleep(1.0)
            os._exit(0)

        # ── PRIORITY 2: Pending-action follow-up ────────────────────────
        if response_text is None and pending_action is not None:
            pa = pending_action
            pa_type = pa.get("type")
            pa_location = pa.get("location", "desktop")

            if pa_type == "create_folder":
                name = _extract_name_from_reply(command)
                if name:
                    pending_action = None          # clear before acting
                    response_text = do_create_folder(name, pa_location)
                else:
                    response_text = "Sorry, I didn't catch the folder name. What would you like to call it, Boss?"

            elif pa_type == "create_file":
                name = _extract_name_from_reply(command)
                if name:
                    pending_action = None
                    response_text = do_create_file(name, pa_location)
                else:
                    response_text = "Sorry, I didn't catch the file name. What would you like to call it, Boss?"

        # ── PRIORITY 3: CREATE/OPEN filesystem commands ───────────────────
        # ── Priority 3a: Create Folder ──
        if response_text is None and _is_create_folder_cmd(cmd_lower):
            folder_name, location_key = _parse_create_folder(cmd_lower, command)
            loc = location_key or "desktop"
            if folder_name:
                pending_action = None              # clear any stale pending
                response_text = do_create_folder(folder_name, loc)
            else:
                pending_action = {"type": "create_folder", "location": loc}
                response_text = "What would you like to name the folder, Boss?"

        # ── Priority 3b: Create File ──
        if response_text is None and _is_create_file_cmd(cmd_lower):
            file_name, location_key = _parse_create_file(cmd_lower)
            if file_name:
                response_text = do_create_file(file_name, location_key or "desktop")
            else:
                response_text = "What would you like to name the file, Boss?"

        # ── Priority 3c: Last-folder recall / open ──
        if response_text is None:
            handled, response = _handle_open_last_folder(cmd_lower)
            if handled:
                response_text = response

        # ── Priority 3d: Open named folder on known location ──
        if response_text is None:
            handled, response = _try_open_named_desktop_folder(cmd_lower, command)
            if handled:
                response_text = response

        # ── Priority 3e: Open known user folders ──
        if response_text is None:
            for pattern, resolver in _OPEN_FOLDER_PATTERNS.items():
                if cmd_lower.startswith(pattern) or cmd_lower == pattern:
                    path = resolver()
                    if path:
                        response_text = do_open_folder(path)
                    else:
                        response_text = f"I couldn't resolve that folder path, Boss."
                    break

        # ── PRIORITY 4: CLOSE commands ────────────────────────────────────
        if response_text is None:
            close_target = parse_close_command(cmd_lower)
            if close_target:
                # Safety: never allow closing Nova itself or the system shell
                _FORBIDDEN_CLOSE = {
                    "nova", "nova ai", "assistant", "nova ai assistant"
                }
                if close_target in _FORBIDDEN_CLOSE:
                    response_text = "I won't close myself, Boss."
                else:
                    closed = False
                    if close_target == "notepad":
                        closed = close_by_window_title("notepad")
                        if not closed:
                            try:
                                subprocess.run(["taskkill", "/IM", "notepad.exe", "/F"], capture_output=True, check=False)
                                closed = True
                            except Exception:
                                pass
                    elif close_target == "ollama":
                        try:
                            subprocess.run(["taskkill", "/IM", "ollama app.exe", "/F"], capture_output=True, check=False)
                            subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], capture_output=True, check=False)
                            closed = True
                        except Exception:
                            pass
                    elif close_target in ("chrome", "google chrome"):
                        closed = close_by_window_title("chrome")
                        if not closed:
                            closed = close_by_window_title("google chrome")
                    elif close_target in ("edge", "microsoft edge"):
                        closed = close_by_window_title("edge")
                        if not closed:
                            try:
                                subprocess.run(["taskkill", "/IM", "msedge.exe", "/F"], capture_output=True, check=False)
                                closed = True
                            except Exception:
                                pass
                    elif close_target in ("youtube",):
                        # YouTube lives inside a browser tab — close window whose title contains "YouTube"
                        closed = close_by_window_title("YouTube")
                        if not closed:
                            closed = close_by_window_title("youtube")
                    elif close_target in ("file explorer", "explorer", "windows explorer"):
                        try:
                            # Close all explorer windows (not the shell itself)
                            subprocess.run(["taskkill", "/IM", "explorer.exe", "/F"], capture_output=True, check=False)
                            time.sleep(0.8)
                            # Restart explorer so the taskbar still works
                            subprocess.Popen("explorer.exe")
                            closed = True
                        except Exception:
                            pass
                    elif close_target == "browser":
                        for browser_name in ("chrome", "edge", "firefox", "opera", "brave"):
                            if close_by_window_title(browser_name):
                                closed = True
                    elif close_target in ("calculator", "calc"):
                        try:
                            subprocess.run(["taskkill", "/IM", "calculator.exe", "/F"], capture_output=True, check=False)
                            subprocess.run(["taskkill", "/IM", "calc.exe", "/F"], capture_output=True, check=False)
                            closed = True
                        except Exception:
                            pass
                    else:
                        closed = close_by_window_title(close_target)

                    display_name = close_target
                    if display_name == "youtube":
                        display_name = "YouTube"
                    elif display_name in ("file explorer", "explorer", "windows explorer"):
                        display_name = "File Explorer"
                    else:
                        display_name = display_name.title()

                    if closed:
                        response_text = f"{display_name} is closed, Boss."
                    else:
                        response_text = f"{display_name} is not open, Boss."

        # ── PRIORITY 5: OPEN website/app commands ──────────────────────────
        if response_text is None:
            open_target = parse_open_command(cmd_lower)
            if open_target:
                if open_target in ("notepad", "notepad.exe"):
                    set_ui_status("EXECUTING...")
                    subprocess.Popen("notepad.exe")
                    response_text = "Notepad is open, Boss."
                elif open_target in ("calculator", "calc", "calc.exe"):
                    set_ui_status("EXECUTING...")
                    subprocess.Popen("calc.exe")
                    response_text = "Calculator is open, Boss."
                elif open_target in ("file explorer", "explorer", "windows explorer", "files", "my computer", "this pc"):
                    set_ui_status("EXECUTING...")
                    subprocess.Popen("explorer.exe")
                    response_text = "File Explorer is open, Boss."
                else:
                    lower_target = open_target.lower().strip()

                    if lower_target in ("chrome", "google chrome"):
                        set_ui_status("EXECUTING...")
                        webbrowser.open("https://www.google.com")
                        response_text = "Chrome is open, Boss."
                    elif lower_target == "google":
                        set_ui_status("EXECUTING...")
                        webbrowser.open("https://www.google.com")
                        response_text = "Google is open, Boss."
                    elif lower_target == "ollama":
                        ollama_path = r"C:\Users\asus\AppData\Local\Programs\Ollama\ollama app.exe"
                        if os.path.exists(ollama_path):
                            set_ui_status("EXECUTING...")
                            subprocess.Popen([ollama_path])
                            response_text = "Ollama is open, Boss."
                        else:
                            response_text = "Ollama is not installed, Boss."
                    else:
                        url_to_open = None
                        display_name = None

                        if lower_target in WEBSITE_ALLOWLIST:
                            url_to_open = WEBSITE_ALLOWLIST[lower_target]
                            display_name = lower_target.title()
                            if lower_target == "youtube":
                                display_name = "YouTube"
                            elif lower_target == "chatgpt":
                                display_name = "ChatGPT"
                            elif lower_target == "linkedin":
                                display_name = "LinkedIn"
                            elif lower_target == "github":
                                display_name = "GitHub"
                        else:
                            for known, url in WEBSITE_ALLOWLIST.items():
                                if known in lower_target or lower_target in known:
                                    url_to_open = url
                                    display_name = known.title()
                                    if known == "youtube":
                                        display_name = "YouTube"
                                    elif known == "chatgpt":
                                        display_name = "ChatGPT"
                                    elif known == "linkedin":
                                        display_name = "LinkedIn"
                                    elif known == "github":
                                        display_name = "GitHub"
                                    break

                        if url_to_open:
                            set_ui_status("EXECUTING...")
                            webbrowser.open(url_to_open)
                            response_text = f"{display_name} is open, Boss."
                        else:
                            if lower_target not in ("chrome", "google"):
                                success, msg = open_website(open_target)
                                if success:
                                    response_text = msg
                                else:
                                    if "." in open_target or "website" in open_target or "http" in open_target:
                                        response_text = "I couldn't find that website, Boss."
                                    else:
                                        response_text = f"I couldn't open {open_target.title()}, Boss."

        # ── PRIORITY 6: YouTube search/play commands ───────────────────────
        if response_text is None and "youtube" in cmd_lower:
            extracted_query = None

            for pattern in ("search youtube for ", "in youtube search ", "in youtube play "):
                if pattern in cmd_lower:
                    idx = cmd_lower.find(pattern)
                    extracted_query = command[idx + len(pattern):].strip()
                    break

            if not extracted_query:
                for suffix in (" on youtube", " in youtube"):
                    if suffix in cmd_lower and "search " in cmd_lower:
                        idx_search = cmd_lower.find("search ") + len("search ")
                        idx_suffix = cmd_lower.rfind(suffix)
                        if idx_search < idx_suffix:
                            extracted_query = command[idx_search:idx_suffix].strip()
                            break

            if not extracted_query:
                for suffix in (" on youtube", " in youtube"):
                    if suffix in cmd_lower and "play " in cmd_lower:
                        idx_play = cmd_lower.find("play ") + len("play ")
                        idx_suffix = cmd_lower.rfind(suffix)
                        if idx_play < idx_suffix:
                            extracted_query = command[idx_play:idx_suffix].strip()
                            break

            if not extracted_query:
                temp = command.lower().replace("youtube", "").strip()
                for verb in ("play ", "search ", "in ", "on ", "for "):
                    if temp.startswith(verb):
                        temp = temp[len(verb):].strip()
                extracted_query = temp.strip()

            if extracted_query:
                set_ui_status("EXECUTING...")
                encoded = urllib.parse.quote_plus(extracted_query)
                webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
                response_text = "YouTube search opened, Boss."
            else:
                response_text = "YouTube search opened, Boss."

        # ── PRIORITY 7: Google search ─────────────────────────────────────
        if response_text is None:
            google_query = None
            if "search google for " in cmd_lower:
                idx = cmd_lower.find("search google for ") + len("search google for ")
                google_query = command[idx:].strip()
            elif cmd_lower.startswith("google search "):
                google_query = command[len("google search "):].strip()
            elif "search for " in cmd_lower and " on google" in cmd_lower:
                idx_s = cmd_lower.find("search for ") + len("search for ")
                idx_e = cmd_lower.rfind(" on google")
                if idx_s < idx_e:
                    google_query = command[idx_s:idx_e].strip()

            if google_query:
                # Perform search, synthesize answer and speak it
                response_text = web_search_answer(google_query, google_query)

        # ── Filmography Query Route ───────────────────────────────────────
        if response_text is None:
            is_movies_query = any(w in cmd_lower for w in ("movie", "film", "filmography", "acted in", "starred in", "acted", "starred"))
            if is_movies_query:
                actor_found = None
                for canon_lower in _CANONICAL_NAMES.keys():
                    if canon_lower in cmd_lower:
                        actor_found = canon_lower
                        break
                
                if actor_found and actor_found in _CANONICAL_FILMOGRAPHIES:
                    movies = _CANONICAL_FILMOGRAPHIES[actor_found]
                    actor_name = _CANONICAL_NAMES[actor_found]
                    list_items = [f"{idx}. {movie}" for idx, movie in enumerate(movies, 1)]
                    header = f"Sure Boss. {actor_name}'s major filmography includes:"
                    
                    grouped_items = []
                    for i in range(0, len(list_items), 7):
                        sub_list = list_items[i:i+7]
                        grouped_items.append(", ".join(sub_list) + ".")
                        
                    response_text = f"{header} {grouped_items[0]}"
                    for group in grouped_items[1:]:
                        response_text += f" I will continue with: {group}"

        # ── Local Trivia Route ────────────────────────────────────────────
        if response_text is None:
            if "hero of pushpa" in cmd_lower or "hero in pushpa" in cmd_lower:
                response_text = "The hero of the Pushpa movie is Allu Arjun, Boss."

        # ── Time command ──────────────────────────────────────────────────
        if response_text is None:
            time_keywords = ("time", "current time", "what time is it", "today's time", "tell me the time")
            is_time_query = any(k in cmd_lower for k in time_keywords) or (
                "time" in cmd_lower and any(w in cmd_lower for w in ("what", "tell", "current", "today"))
            )
            if is_time_query:
                from datetime import datetime
                now = datetime.now()
                formatted_time = now.strftime("%I:%M %p")
                if formatted_time.startswith("0"):
                    formatted_time = formatted_time[1:]
                response_text = f"It is {formatted_time}, Boss."

        # ── Date command ──────────────────────────────────────────────────
        if response_text is None:
            date_keywords = ("date", "today's date", "what is the date", "what date is today", "what day is today")
            is_date_query = any(k in cmd_lower for k in date_keywords) or (
                "date" in cmd_lower and any(w in cmd_lower for w in ("what", "tell", "current", "today"))
            )
            if is_date_query:
                from datetime import datetime
                now = datetime.now()
                formatted_date = now.strftime("%A, %B %d, %Y")
                response_text = f"Today is {formatted_date}, Boss."

        # ── Conversational queries ────────────────────────────────────────
        if response_text is None:
            conversational_phrases = (
                "how are you", "what can you do", "tell me a joke", "good morning",
                "thank you", "thanks", "hello", "hi", "hey", "yo", "good afternoon", "good evening",
                "what should i work on today", "who are you"
            )
            if any(p in cmd_lower for p in conversational_phrases):
                if "how are you" in cmd_lower:
                    response_text = "I am doing great, Boss. How can I help you today?"
                elif "what can you do" in cmd_lower:
                    response_text = "I can open websites, control windows, create folders, fetch live search updates, list actor filmographies, and chat with you, Boss."
                elif "good morning" in cmd_lower:
                    response_text = "Good morning, Boss! Hope you have a productive day ahead."
                elif "thank you" in cmd_lower or "thanks" in cmd_lower:
                    response_text = "You're welcome, Boss. Let me know if you need anything else."
                elif "tell me a joke" in cmd_lower:
                    response_text = "Why don't programmers like nature? Because it has too many bugs, Boss."
                elif "what should i work on today" in cmd_lower:
                    response_text = "You should start by tackling your priority tasks and reviews, Boss."
                elif "hello" in cmd_lower or "hi" in cmd_lower:
                    response_text = "Hello Boss! How can I assist you?"
                else:
                    raw = ask_ollama(command)
                    response_text = _ollama_reply_to_speech(raw)

        # ── PRIORITY 8: Knowledge/web questions ───────────────────────────
        if response_text is None:
            explicit_search_keywords = (
                "search the web", "search online", "look up",
                "latest news", "breaking news", "today's news",
                "weather",
            )
            temporal_info_keywords = ("latest ", "recent ", "current ", "today's ", "upcoming ")
            _is_explicit_search = (
                any(k in cmd_lower for k in explicit_search_keywords)
                or (
                    any(k in cmd_lower for k in temporal_info_keywords)
                    and any(k in cmd_lower for k in ("what", "who", "how", "version", "news",
                                                      "price", "score", "result", "update"))
                )
            )
            if _is_explicit_search:
                response_text = web_search_answer(original_command, command)

        if response_text is None:
            factual_keywords = (
                "what is", "what are", "who is", "who are",
                "explain", "describe", "definition of",
                "tell me about", "can you tell",
                "movies", "films", "songs", "albums",
                "biography", "history of", "history",
                "born", "founded", "invented",
            )
            if any(k in cmd_lower for k in factual_keywords):
                is_movie_query = any(w in cmd_lower for w in ("movie", "film", "filmography", "acted", "starred", "recent", "latest"))
                
                wiki_found = False
                if not is_movie_query:
                    try:
                        subject = command
                        for prefix in ("what is ", "what are ", "who is ", "who are ",
                                       "explain ", "describe ", "tell me about ",
                                       "can you tell me about ", "can you tell "):
                            if prefix in cmd_lower:
                                idx = cmd_lower.find(prefix) + len(prefix)
                                subject = command[idx:].strip()
                                break
                        subject = subject.rstrip("?").strip()
                        if subject and len(subject.split()) <= 5:
                            wiki_answer = wikipedia_answer(subject)
                            if wiki_answer and len(wiki_answer) > 50:
                                response_text = wiki_answer
                                wiki_found = True
                    except Exception as wiki_err:
                        log_info(f"Wikipedia lookup failed ({wiki_err}). Using web search...")

                if not wiki_found:
                    response_text = web_search_answer(original_command, command)

        # ── PRIORITY 9: Default Ollama Conversation ───────────────────────
        if response_text is None:
            raw = ask_ollama(command)
            response_text = _ollama_reply_to_speech(raw)

    except Exception as e:
        log_error(f"Error in handle_command: {e}")
        open_target = parse_open_command(cmd_lower)
        if open_target:
            response_text = f"I couldn't open {open_target.title()}, Boss."
        else:
            response_text = "I ran into an error processing that, Boss."

    # Central print and speak response
    if response_text:
        respond(response_text)
    else:
        respond("I didn't understand that command, Boss.")

# ------------------------------------------------------------------
# Background Voice Loop Thread
# ------------------------------------------------------------------
def run_voice_assistant():
    global whisper_model

    # Give GUI 1 second to fully initialize and show
    time.sleep(1.0)

    # Load Faster-Whisper ONCE (after window opens so GUI is instant)
    log_info("Initializing Faster-Whisper model 'base' on CPU...")
    try:
        whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        log_info("Faster-Whisper model loaded successfully.")
    except Exception as e:
        log_error(f"Failed to load Whisper model: {e}")
        set_ui_status("OFFLINE")
        speak("Whisper model failed to load. Voice recognition unavailable, Boss.")
        return  # Cannot continue without speech recognition

    set_ui_status("READY")

    # ── Outer restart loop — recovers from transient crashes ——————
    while True:
        try:
            _voice_loop(whisper_model)
        except Exception as e:
            log_error(f"Voice loop crashed: {e}. Restarting in 2s...")
            time.sleep(2)
            set_ui_status("READY")


def _voice_loop(model):
    """Inner loop: wait for wake word, record, transcribe, execute, repeat."""
    set_ui_status("READY")

    while True:
        # ── Reset stop event and return to READY for each new cycle ─────
        # IMPORTANT: clear BEFORE speak("Yes Boss.") so STOP from previous
        # cycle does not silently block the acknowledgement.
        _tts_stop_event.clear()
        set_ui_status("READY")
        activated = listen_for_wake_word(model)
        if not activated:
            continue

        set_ui_status("WAKE DETECTED")
        # speak() itself also calls _tts_stop_event.clear() — belt-and-suspenders.
        speak("Yes Boss.")

        # ── Record user command ────────────────────────────────
        set_ui_status("LISTENING...")
        audio_segment = record_until_silence()
        if audio_segment is None or len(audio_segment) == 0:
            log_info("No audio captured. Returning to READY.")
            set_ui_status("READY")
            continue

        # ── Transcribe ─────────────────────────────────────────
        temp_path = os.path.join(
            tempfile.gettempdir(), f"nova_command_{uuid.uuid4().hex}.wav"
        )
        command_text = ""
        try:
            save_wav(temp_path, audio_segment)
            set_ui_status("THINKING...")
            segments, _ = model.transcribe(
                temp_path,
                beam_size=5,
                language="en",
                vad_filter=True
            )
            command_text = " ".join([seg.text for seg in segments]).strip()
            print(f"\nUser: {command_text}")
        except Exception as e:
            log_error(f"Transcription error: {e}")
            respond("I had trouble understanding that, Boss.")
            set_ui_status("READY")
            continue
        finally:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception:
                pass

        # ── Execute command ─────────────────────────────────────
        if command_text:
            try:
                handle_command(command_text, model)
            except Exception as e:
                log_error(f"handle_command error: {e}")
                respond("I ran into an error processing that, Boss.")

        # ── Always return to READY after each cycle ─────────────────
        set_ui_status("READY")


# ------------------------------------------------------------------
# Main Loop (GUI Launcher)
# ------------------------------------------------------------------
def main():
    global _ui_instance

    # ── Single-instance check ───────────────────────────────────
    if "--no-single-instance" not in sys.argv:
        if not _acquire_single_instance_lock():
            print("[INFO] Another Nova instance is already running. Exiting.")
            sys.exit(0)

    log_info(f"Nova project directory: {_NOVA_DIR}")
    log_info("Launching Nova visual GUI window...")

    from nova_ui import NovaUI

    # Clean shutdown callback
    def on_gui_close():
        log_info("GUI closed by user. Initiating system shutdown...")
        os._exit(0)

    def on_stop_clicked():
        log_info("Emergency STOP requested via UI.")
        _tts_stop_event.set()
        set_ui_status("READY", user_text="", nova_text="Speech stopped, Boss.")

    _ui_instance = NovaUI(on_close_callback=on_gui_close, on_stop_callback=on_stop_clicked)

    # Launch voice loop in background daemon thread
    t = threading.Thread(target=run_voice_assistant, daemon=True)
    t.start()

    # Start Tkinter mainloop on main thread
    _ui_instance.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_info("Terminated by user keyboard command.")
        os._exit(0)
