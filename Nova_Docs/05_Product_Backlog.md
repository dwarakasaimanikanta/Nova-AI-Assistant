# 📋 Nova AI Assistant: Master Product Backlog

This document serves as the master product backlog and execution roadmap for the Nova AI Assistant project.

---

## 1. Release Roadmap

- **v0.1: Foundation & Command Core (Complete)**: Basic voice pipelines (wake word, bilingual, continuous chat), offline calculator/system skills, and CLI shells.
- **v0.5: OS & Device Bridge (Complete)**: Android phone integration via ADB (calling, texting, WhatsApp, Wi-Fi reconnection), browser tools, and the Contact Name Correction layer.
- **v0.8: Core Extension (Months 4–5)**: Short-term memory context logic, SQLite database long-term memory, vision tools, and security sandbox integrations.
- **v1.0: Autonomous Assistant (Months 6–7)**: Multi-agent coordination pipelines, personal services sync, production GUI dashboard, and full release verification.

---

## 2. Backlog Epics, Features, and Tasks

### Epic 1: Voice & Language Pipelines (v0.1)

#### Feature 1.1: Wake Word Detection
- **Task 1.1.1**: Set up background microphone capturing thread. (Priority: `Critical` | Duration: 2 days | Dependency: None)
- **Task 1.1.2**: Implement fuzzy wake-word matching logic with rapidfuzz/difflib at $\ge 80\%$ similarity score. (Priority: `Critical` | Duration: 2 days | Dependency: Task 1.1.1)

#### Feature 1.2: Continuous Conversation Loop
- **Task 1.2.1**: Implement `WAITING` state to execute multiple commands without repeating the wake word. (Priority: `Critical` | Duration: 3 days | Dependency: Task 1.1.2)
- **Task 1.2.2**: Integrate 20-second silence timeout returning to `WAKING` standby. (Priority: `High` | Duration: 1 day | Dependency: Task 1.2.1)
- **Task 1.2.3**: Intercept exit keywords (`bye`, `goodbye`, `సరే`, `బై`) to exit conversation mode. (Priority: `Critical` | Duration: 1 day | Dependency: Task 1.2.1)

#### Feature 1.3: Bilingual Voice Engine
- **Task 1.3.1**: Enable Whisper automatic language detection. (Priority: `High` | Duration: 2 days | Dependency: Task 1.1.1)
- **Task 1.3.2**: Swappable Telugu/English TTS engine responding to voice commands. (Priority: `High` | Duration: 2 days | Dependency: Task 1.3.1)

---

### Epic 2: System & Device Bridge (v0.5)

#### Feature 2.1: Android ADB Control
- **Task 2.1.1**: Integrate ADB wrapper subprocess executions. (Priority: `Critical` | Duration: 3 days | Dependency: None)
- **Task 2.1.2**: Auto-connect to Wi-Fi ADB devices on startup using `data/android_config.json`. (Priority: `High` | Duration: 2 days | Dependency: Task 2.1.1)
- **Task 2.1.3**: Map Call, SMS, and WhatsApp voice tasks to targeted ADB subprocess events. (Priority: `Critical` | Duration: 3 days | Dependency: Task 2.1.1)

#### Feature 2.2: Contact Name Correction Layer
- **Task 2.2.1**: Load contact data from `data/contacts.json`. (Priority: `Critical` | Duration: 1 day | Dependency: None)
- **Task 2.2.2**: Implement phonetic fuzzy corrections (e.g. *Emma -> Amma*, *Ravy -> Ravi*) matching $\ge 80\%$ before planning execution. (Priority: `Critical` | Duration: 3 days | Dependency: Task 2.2.1)
- **Task 2.2.3**: Strip and rebuild Telugu suffixes (e.g. `కి`, `కు`) around translated names. (Priority: `High` | Duration: 2 days | Dependency: Task 2.2.2)

---

### Epic 3: Vector Memory & Profiles (v0.8)

#### Feature 3.1: Long-Term Memory
- **Task 3.1.1**: Set up SQLite schema with keys, values, and embeddings columns. (Priority: `High` | Duration: 2 days | Dependency: None)
- **Task 3.1.2**: Implement semantic search query matching functions. (Priority: `High` | Duration: 3 days | Dependency: Task 3.1.1)
- **Task 3.1.3**: Expose `memory` tool options (`store_fact`, `get_fact`, `list_facts`) to the router. (Priority: `Medium` | Duration: 2 days | Dependency: Task 3.1.2)

---

### Epic 4: Multimodal Vision & Tools (v0.8)

#### Feature 4.1: Screen Interaction
- **Task 4.1.1**: Create `capture_screenshot` system tool utility. (Priority: `Medium` | Duration: 2 days | Dependency: None)
- **Task 4.1.2**: Enable Gemini multimodal vision API queries to explain active screens. (Priority: `Medium` | Duration: 4 days | Dependency: Task 4.1.1)

---

### Epic 5: Personal Services & Multi-Agent Coordination (v1.0)

#### Feature 5.1: Agentic Orchestration
- **Task 5.1.1**: Establish coordinator event loop mapping tasks to sub-planners. (Priority: `Low` | Duration: 5 days | Dependency: None)
- **Task 5.1.2**: Integrate virtual execution sandboxes for high-risk system commands. (Priority: `Medium` | Duration: 4 days | Dependency: Task 5.1.1)

---

## 3. Milestones

1. **Milestone 1: Voice & Command Foundation (Reached v0.1)**: Wake word, continuous Telugu loop, offline skills running.
2. **Milestone 2: ADB Automation (Reached v0.5)**: Auto-ADB Wi-Fi reconnects, phone calling, texting, contact correction working.
3. **Milestone 3: Semantic Database (Target Month 4)**: Vector memory and semantic profile updates operational.
4. **Milestone 4: Vision & Multimodality (Target Month 5)**: Visual screens inspections and GUI overlay active.
5. **Milestone 5: Production Release (Target Month 7 - v1.0)**: Multi-agent coordination, installer packages, stable release.

---

PROJECT MODE:
IMPLEMENTATION
