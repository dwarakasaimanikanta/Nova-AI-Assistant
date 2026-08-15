import os
import json
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Return status check metadata for Vercel deployment verification."""
        has_api_key = bool(os.environ.get("GEMINI_API_KEY"))
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        # Enable CORS
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        response_data = {
            "status": "online",
            "assistant": "NOVA AI Assistant",
            "environment": "Vercel Serverless",
            "llm_provider": "Google Gemini",
            "api_key_configured": has_api_key,
            "capabilities": {
                "conversational_ai": True,
                "code_generation": True,
                "multilingual_support": True,
                "desktop_automation": False,
                "local_voice_recording": False
            }
        }
        self.wfile.write(json.dumps(response_data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
