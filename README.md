# NOVA AI Assistant

A modern, full-stack AI-powered personal assistant featuring conversational AI, multi-provider failover, voice interaction, real-time web search grounding, image generation, document synthesis, and secure Firebase authentication.

🌐 **Live Web App**: [https://verceldeploy-eight-kappa.vercel.app](https://verceldeploy-eight-kappa.vercel.app)

---

## 🚀 Features

- **Conversational AI**: Context-aware natural language conversations with support for multilingual queries (English, Telugu, Hindi, Tamil, Kannada).
- **Google Gemini Integration**: Primary engine utilizing Google Gemini models (`gemini-3.6-flash`, `gemini-3.7-flash`) with Google Search grounding.
- **Groq Ultra-Fast Fallback**: Automatic instant failover to Groq (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`) when rate limits or quota boundaries are encountered.
- **Google Sign-In**: One-click secure authentication with Google OAuth via real Firebase Authentication.
- **Email & Password Authentication**: Full account registration and login flow.
- **Email Verification**: Automated email verification link dispatch with verification enforcement before granting assistant access.
- **Private User-Based Chat History**: Chat histories and sessions are strictly scoped to the user's Firebase UID (`nova_conversations_{uid}`), ensuring complete data privacy across accounts.
- **Voice Assistant (STT & TTS)**:
  - **Speech-to-Text**: Real-time microphone voice input directly transcribing user speech.
  - **Text-to-Speech**: Natural, animated voice response synthesis with toggleable controls.
- **AI Image Generation**: Photorealistic text-to-image synthesis with intelligent Romanized Telugu/English prompt enhancement powered by Pollinations.ai.
- **Web & Entity Search**: Real-time factual web grounding via DuckDuckGo and high-confidence celebrity/entity image search via Wikipedia & Wikimedia.
- **PDF & Document Generation**: On-the-fly generation and compilation of styled PDF (ReportLab) and DOCX (python-docx) files.
- **PDF & File Explanation**: Client-side document text extraction and AI explanation for PDF, TXT, DOCX, and Markdown files.
- **Chat Management**: Session pinning, renaming, individual chat deletion, search filtering, and conversation export.
- **Responsive Cyberpunk UI**: Sleek dark-mode glassmorphism interface with custom neon animations, soundwave visualizers, and mobile optimization.

---

## 🛠️ Tech Stack

### Frontend
- **HTML5 & Semantic Elements**
- **Modern Vanilla CSS3**: Custom design tokens, glassmorphic backdrop filters, cyber-neon lighting, responsive grid layouts
- **Vanilla JavaScript (ES6+)**: DOM state controllers, Web Speech API, Marked.js, Highlight.js
- **Firebase Web SDK (v10)**: Real-time authentication client

### Backend & Serverless
- **Python 3.12**: Microservice architecture designed for Vercel Serverless Functions
- **Google GenAI SDK (`google-genai`)**: Gemini API integration and multimodal processing
- **ReportLab**: Programmatic PDF document layout engine
- **python-docx**: DOCX file parser and generator
- **python-dotenv**: Environment configuration manager

### Cloud & AI Infrastructure
- **Hosting**: Vercel Serverless Platform
- **Authentication**: Firebase Authentication
- **AI Providers**: Google AI Studio (Gemini), Groq Cloud
- **Image Generation**: Pollinations.ai

---

## 🔐 Authentication & Security

- **Google OAuth**: Fast and secure Google sign-in with automatic identity verification.
- **Email Verification**: Protects against spam registrations by requiring verification links before unlocking assistant features.
- **Session Persistence**: Secure Firebase local session management (`Auth.Persistence.LOCAL`).
- **Data Isolation**: Each user's conversations and settings are isolated per Firebase UID in storage.
- **Zero Password Storage**: Passwords are handled exclusively by Firebase identity servers and never touch local application storage.

---

## 🌐 Live Demo

Experience NOVA live in your browser:
🔗 **[https://verceldeploy-eight-kappa.vercel.app](https://verceldeploy-eight-kappa.vercel.app)**

---

## 📦 Installation & Local Setup

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** (for Vercel CLI deployment)
- API Keys for **Google Gemini** and/or **Groq**

### 1. Clone the Repository
```bash
git clone https://github.com/dwarakasaimanikanta/Nova-AI-Assistant.git
cd Nova-AI-Assistant
```

### 2. Set Up Environment Variables
Create a `.env` file in the root and in `vercel_deploy/`:
```bash
cp .env.example .env
cp vercel_deploy/.env.example vercel_deploy/.env
```

Edit `.env` and add your API keys:
```env
PRIMARY_PROVIDER=gemini
PRIMARY_MODEL=gemini-3.6-flash
GEMINI_API_KEY=your_actual_gemini_api_key_here
FALLBACK_PROVIDER=groq
GROQ_API_KEY=your_actual_groq_api_key_here
```

### 3. Install Backend Dependencies
```bash
pip install -r vercel_deploy/requirements.txt
```

### 4. Run Locally
You can run the local server from the `vercel_deploy` directory:
```bash
cd vercel_deploy
python server.py
```
Open your browser and navigate to `http://localhost:8000`.

---

## ⚠️ Environment Variables

| Variable | Required | Description |
| :--- | :---: | :--- |
| `GEMINI_API_KEY` | **Yes** (Primary) | API key from [Google AI Studio](https://aistudio.google.com/) |
| `GROQ_API_KEY` | **Recommended** | API key from [Groq Console](https://console.groq.com/) for zero-latency failover |
| `OPENROUTER_API_KEY` | Optional | Secondary multi-model fallback key |
| `OPENAI_API_KEY` | Optional | OpenAI key if using GPT-4o as fallback |
| `SERPER_API_KEY` | Optional | Serper.dev Google Search key |

---

## 📸 Screenshots

*(Add your screenshots here)*

| Main Chat Interface | Glassmorphic Authentication |
| :---: | :---: |
| `![NOVA Interface](screenshots/chat_preview.png)` | `![NOVA Auth](screenshots/auth_preview.png)` |

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).
