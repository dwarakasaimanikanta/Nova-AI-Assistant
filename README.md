# 🚀 NOVA AI Assistant 2.0

> **A Modern AI-Powered Personal Assistant with Conversational AI, Voice Interaction, Authentication, Image Tools, Web Search and Document Intelligence.**

---

## 🌐 Live Demo

🚀 **Try NOVA AI Assistant 2.0 Live**:  
🔗 **[https://verceldeploy-eight-kappa.vercel.app](https://verceldeploy-eight-kappa.vercel.app)**

---

## 🌟 What's New in NOVA 2.0?

NOVA originated as a lightweight AI chat utility and has now evolved into **NOVA 2.0** — a comprehensive, production-ready AI Assistant platform with full-stack capabilities, enterprise authentication, and multimodal intelligence:

- 🔐 **Secure Firebase Authentication**: Real Google OAuth Sign-In and Email/Password registration.
- 📧 **Automated Email Verification**: Verification link dispatch ensuring valid, verified accounts before granting access.
- 👤 **User-Specific Accounts & Private Storage**: Complete isolation of chat histories keyed by Firebase UID (`nova_conversations_{uid}`).
- 🎤 **Full Voice Assistant**: Real-time microphone Speech-to-Text (STT) and fluid Text-to-Speech (TTS) audio playback.
- ⚡ **Dual-Engine AI Architecture**: Primary Google Gemini models with instant, zero-latency Groq fallback.
- 🎨 **AI Image Generation & Entity Search**: Photorealistic image synthesis via Pollinations.ai and verified entity image search.
- 📄 **Document Intelligence**: Dynamic styled PDF/DOCX generation and file analysis for PDF, TXT, DOCX, and Markdown.
- 🚀 **Serverless Cloud Deployment**: Production-grade deployment on Vercel with optimized Python backend functions.

---

## 🚀 Features

### 🤖 AI Intelligence
- **Conversational AI**: Multi-turn dialogue with deep context awareness and natural multilingual fluency (English, Telugu, Hindi, Tamil, Kannada).
- **Gemini Integration**: High-accuracy reasoning powered by Google Gemini (`gemini-3.6-flash`, `gemini-3.7-flash`) with optional Google Search grounding.
- **Groq Fallback**: Ultra-fast fallback execution using Groq (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`) whenever rate limits or quota boundaries are reached.

### 🔐 Authentication & Privacy
- **Google Sign-In**: One-click secure sign-in via Google OAuth using Firebase Authentication.
- **Email/Password Authentication**: Dedicated registration and login flows.
- **Email Verification**: Enforced email verification links with status checking and resend capabilities.
- **User-Specific Private Chat History**: Each authenticated user has a private, separate chat history that is never accessible to other users.

### 🎤 Voice Interaction
- **Speech-to-Text (STT)**: Real-time voice capture and speech recognition directly from your microphone.
- **Text-to-Speech (TTS)**: Natural voice synthesis with real-time waveform animations and one-click toggle controls.
- **Voice Assistant**: Hands-free conversation experience with automatic audio response handling.

### 🎨 Creative Tools
- **AI Image Generation**: Text-to-image synthesis with automatic Romanized Telugu and English prompt enhancement.
- **Web & Image Search**: Live factual search grounding via DuckDuckGo and verified celebrity/entity image search via Wikipedia and Wikimedia.

### 📄 Document Tools
- **PDF Generation**: Programmatic compilation of beautifully styled, multi-section PDF documents using ReportLab.
- **PDF Explanation**: Client-side text extraction and AI explanation for uploaded documents (PDF, DOCX, TXT, MD).

### 💬 Chat Management
- **New Chat**: Instantly initialize fresh conversation threads.
- **Chat History**: Organized sidebar with quick access to recent conversations.
- **Rename Chat**: Customize conversation titles for easy organization.
- **Delete Chat**: Delete individual sessions or clear chat history with confirmation dialogs.

---

## 🛠️ Tech Stack

### Frontend
- **HTML5**: Semantic layout and modern web standards.
- **Vanilla CSS3**: Sleek cyberpunk glassmorphism design system, dark mode, responsive mobile drawer, and CSS animations.
- **Vanilla JavaScript (ES6+)**: Client-side state orchestration, Web Speech API, Marked.js markdown rendering, and Highlight.js syntax highlighting.

### Backend & Serverless
- **Python 3.12**: Microservice API architecture optimized for Vercel Serverless Functions.
- **ReportLab**: PDF layout compilation and document styling.
- **python-docx**: Microsoft Word DOCX generation and parsing.
- **python-dotenv**: Environment configuration loading.

### AI & Cloud Services
- **Google Gemini**: Primary large language model and multimodal processing (`google-genai` SDK).
- **Groq**: Ultra-low-latency secondary LLM fallback engine.
- **Firebase Authentication**: User identity management, Google OAuth provider, and email verification.
- **Pollinations.ai**: Generative image creation API.
- **Vercel**: Edge routing, static asset CDN, and serverless execution platform.

---

## 🔐 Security

- **Environment Variable Protection**: All secret API keys (`GEMINI_API_KEY`, `GROQ_API_KEY`) are stored in server-side environment variables and never exposed to the client browser.
- **Strict `.gitignore` Policy**: Secret configuration files (`.env`, `.env.local`, `.vercel/`, private keys) are permanently excluded from version control.
- **Firebase Security Architecture**: User authentication tokens and session lifecycles are managed securely by Firebase Authentication.
- **Cryptographic Data Isolation**: Chat sessions and conversation storage are keyed strictly to the authenticated user's unique UID.

---

## 📦 Installation & Setup

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** (optional, for Vercel CLI)
- API Keys from [Google AI Studio](https://aistudio.google.com/) and [Groq Console](https://console.groq.com/)

### 1. Clone the Repository
```bash
git clone https://github.com/dwarakasaimanikanta/Nova-AI-Assistant.git
cd Nova-AI-Assistant
```

### 2. Configure Environment Variables
Copy the template configuration files:
```bash
cp .env.example .env
cp vercel_deploy/.env.example vercel_deploy/.env
```

Open `.env` and fill in your API credentials:
```env
PRIMARY_PROVIDER=gemini
PRIMARY_MODEL=gemini-3.6-flash
GEMINI_API_KEY=your_gemini_api_key_here

FALLBACK_PROVIDER=groq
FALLBACK_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Install Dependencies
```bash
pip install -r vercel_deploy/requirements.txt
```

### 4. Run the Application Locally
```bash
cd vercel_deploy
python server.py
```
Open `http://localhost:8000` in your web browser.

---

## ⚠️ Environment Variables

| Variable | Requirement | Purpose |
| :--- | :---: | :--- |
| `GEMINI_API_KEY` | **Required** | Primary AI conversation & vision processing |
| `GROQ_API_KEY` | **Recommended** | High-speed fallback when Gemini limits are reached |
| `OPENROUTER_API_KEY` | Optional | Multi-model fallback provider |
| `OPENAI_API_KEY` | Optional | OpenAI API fallback key |
| `SERPER_API_KEY` | Optional | Dedicated Google Search API key |

---

## 🔮 Future Roadmap

> [!NOTE]
> The following features are planned for future releases of NOVA:

- 💳 **NOVA Free & Pro Tier Plans**: Tiered access with flexible usage limits.
- ⭐ **Advanced Premium AI Capabilities**: Extended context windows and specialized domain models.
- 📊 **Usage Management & Analytics**: User dashboards for token and query tracking.
- 💰 **Payment Gateway Integration**: Seamless subscription processing.
- 🧠 **Cross-Device Cloud Sync**: Cloud database synchronization across multiple devices.
- 🎯 **Advanced Personalization**: Custom agent personalities, memory tuning, and custom skill integrations.

---

## 📸 Screenshots

*(Add your screenshots here)*

| Chat Interface | Firebase Authentication |
| :---: | :---: |
| `![NOVA Chat](screenshots/chat_interface.png)` | `![NOVA Auth](screenshots/auth_modal.png)` |

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).
