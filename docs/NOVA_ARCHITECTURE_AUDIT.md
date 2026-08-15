# NOVA Architecture Audit

This document reviews the current architecture of the Nova AI Assistant, highlighting critical issues, duplication, race conditions, unsafe routing, language state bugs, and lack of deterministic verification.

## Current Architecture & Execution Flow

At present, user commands follow this sequence:
1. **Microphone Capture:** Active recording occurs in the background thread.
2. **VAD & Silence Detection:** Once silence is detected, audio is written to a temporary WAV file.
3. **Wake Word Detection:** The WAV is transcribed. If wake word checks pass, the state transitions to `WAKE_DETECTED`.
4. **Language Selection:** The system prompts the user in the selected language. It transcribes the next input and tries to match a language name.
5. **Command Execution:**
   - Pre-checks (Personality, Stop, Language Switches) are executed directly in `ExecutiveAgent`.
   - Conversational/Knowledge queries fall back to `NovaEngine.handle_input`, which triggers `AgentPlanner`.
   - `AgentPlanner` exposes all registered tools to the LLM (Gemini) and lets it choose arbitrary tool calls.
6. **TTS Response:** Synthesizes speech and plays it back.

---

## Root Causes of Unreliability

### 1. Arbitrary LLM Tool Selection (Lack of Brain Layer)
- **Problem:** When an input falls into `CONVERSATION`, `KNOWLEDGE`, or `CODING` intent, the system passes all tools to the LLM. The LLM can choose to invoke desktop automation, launch processes, delete files, or open search queries non-deterministically.
- **Root Cause:** The system lacks a structured "Brain" layer that converts natural language into a strictly defined `ActionPlan` before tools are even invoked.

### 2. Duplicated Logic & Splintered Routing
- **Problem:** Routing is scattered across `ConversationEngine`, `ExecutiveAgent` fast paths, `NovaEngine.handle_input`, and `AgentPlanner`.
- **Root Cause:** Intent routing is not centralized. Pre-checks and fast-path heuristics are hardcoded in multiple places, making it impossible to guarantee deterministic ordering (e.g. Stop, Language switches, Project Creation, and App Control).

### 3. Language State Loss
- **Problem:** Language states can be overwritten or lost between turns, especially if a background process or an LLM call does not preserve the session configuration.
- **Root Cause:** The `LanguageSession` is used but sometimes bypassed or overridden. Additionally, Whisper auto-detection on short command utterances can randomly select Hindi or English even when Telugu is locked. We must lock Whisper's decoding language parameters based on `LanguageSession`.

### 4. Audio Capture / TTS Race Conditions (Self-Capture)
- **Problem:** If Nova's own TTS output is playing, background audio capture can capture the spoken words, causing Nova to respond to its own voice or trigger wake phrase detections.
- **Root Cause:** Lack of absolute locking of microphone streams during TTS playback, combined with stale audio queue buffering where trailing audio blocks are not properly drained.

### 5. False Wake Word Triggers
- **Problem:** Phrases like "Hello Nova" are loosely accepted. Whisper's phonetic variants list is too permissive.
- **Root Cause:** The wake detector allows too many fuzzy matches and automatic conversion aliases.

### 6. Unverified Actions & Guessing
- **Problem:** The system reports actions (e.g. closing an application, opening a URL, creating a folder) as successful without checking the actual state of the OS or the browser.
- **Root Cause:** Lack of a real-world verification contract in tools. Tools return `SUCCESS` solely if no python exception is thrown, rather than checking if a process exists, if a file exists on disk, or if the current active tab URL matches.
