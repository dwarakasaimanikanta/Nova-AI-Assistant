import os
import json
from http.server import BaseHTTPRequestHandler
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini API Key
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# Web deployment system instructions to preserve persona and handle desktop limitation
SYSTEM_INSTRUCTION = (
    "You are NOVA (Neural Online Virtual Assistant), a premium, state-of-the-art AI assistant. "
    "You speak in a polite, helpful, intelligent, and highly professional manner. You can converse "
    "fluent in English, Telugu, Hindi, Tamil, and Kannada.\n\n"
    "IMPORTANT NOTE: Since this is the WEB DEPLOYMENT of NOVA hosted on Vercel, local desktop operations "
    "(such as launching VS Code, Paint, Notepad, opening local folder paths, executing local command line commands in terminal, "
    "or PortAudio/SAPI local device speech) are unavailable in this environment. If the user asks for desktop-only commands, "
    "explain politely that those capabilities require the local desktop version of NOVA, but you are fully capable of "
    "generating code, answering questions, writing documents, performing analysis, and providing general conversational support."
)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Receive conversation history and message, query Gemini, and return response."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        # Enable CORS
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
        except Exception:
            self.wfile.write(json.dumps({"error": "Invalid JSON payload."}).encode('utf-8'))
            return

        message = data.get("message", "").strip()
        history = data.get("history", [])
        language = data.get("language", "en")

        if not message:
            self.wfile.write(json.dumps({"error": "Message is required."}).encode('utf-8'))
            return

        if not os.environ.get("GEMINI_API_KEY"):
            self.wfile.write(json.dumps({"error": "Gemini API key is not configured on the Vercel server. Please set GEMINI_API_KEY."}).encode('utf-8'))
            return

        try:
            # Format history for google-generativeai
            formatted_history = []
            for msg in history:
                role = "model" if msg.get("role") == "assistant" else "user"
                content = msg.get("content", "").strip()
                if content:
                    formatted_history.append({
                        "role": role,
                        "parts": [content]
                    })

            # Configure GenerativeModel
            model = genai.GenerativeModel(
                model_name="gemini-3.5-flash-lite",
                system_instruction=SYSTEM_INSTRUCTION
            )

            # Start chat with existing history
            chat_session = model.start_chat(history=formatted_history)
            response = chat_session.send_message(message)

            response_data = {
                "response": response.text,
                "language": language
            }
            self.wfile.write(json.dumps(response_data).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"error": f"An error occurred while generating response: {str(e)}"}).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
