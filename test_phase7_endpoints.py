import urllib.request
import json
import base64
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_URL = "http://localhost:3001"

print("=" * 90)
print("PHASE 7: 10 EXACT END-TO-END TARGETED TESTS")
print("=" * 90)

tests = [
    ("TEST 1", "Weather in Bangalore today", "/api/live_info", {"query": "Weather in Bangalore today"}),
    ("TEST 2", "Latest technology news today", "/api/live_info", {"query": "Latest technology news today"}),
    ("TEST 3", "USD to INR today", "/api/live_info", {"query": "USD to INR today"}),
    ("TEST 4", "100 USD to INR", "/api/live_info", {"query": "100 USD to INR"}),
    ("TEST 5", "Latest cricket news today", "/api/live_info", {"query": "Latest cricket news today"}),
    ("TEST 6", "Create a Python learning roadmap PDF", "/api/generate_document", {"prompt": "Create a Python learning roadmap PDF"}),
    ("TEST 7", "Create Python notes DOCX", "/api/generate_document", {"prompt": "Create Python notes DOCX"}),
    ("TEST 8", "Generate a beautiful sunset image", "/api/generate_image", {"prompt": "Generate a beautiful sunset image"}),
    ("TEST 9", "Allu Arjun images", "/api/search_images", {"query": "Allu Arjun images"}),
    ("TEST 10", "What is Python?", "/api/chat", {"message": "What is Python?", "language": "en", "search_mode": "ai"})
]

results = []

for tid, query, endpoint, payload in tests:
    print(f"\n--- {tid}: \"{query}\" ---")
    print(f"  Endpoint: {endpoint}")
    try:
        req = urllib.request.Request(
            f"{BASE_URL}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status = resp.status
            print(f"  API Status: HTTP {status}")
            
            # Validation logic per test
            passed = False
            ui_desc = ""
            if tid == "TEST 1":
                passed = data.get("success") and data.get("category") == "weather" and data.get("temperature_c") is not None
                ui_desc = f"Weather card with {data.get('location')}, Temp: {data.get('temperature_c')}°C ({data.get('temperature_f')}°F), Condition: {data.get('condition')}"
            elif tid == "TEST 2":
                passed = data.get("success") and (data.get("category") == "news" or len(data.get("articles", [])) > 0)
                ui_desc = f"News card with {len(data.get('articles', []))} headlines and source links"
            elif tid == "TEST 3":
                passed = data.get("success") and data.get("rate") is not None
                ui_desc = f"Currency card with 1 USD = ₹{data.get('rate')} INR"
            elif tid == "TEST 4":
                passed = data.get("success") and data.get("converted_value") is not None and data.get("amount") == 100.0
                ui_desc = f"Currency conversion card with 100 USD = ₹{data.get('converted_value'):,.2f} INR (Rate: ₹{data.get('rate'):.2f})"
            elif tid == "TEST 5":
                passed = data.get("success") and (len(data.get("articles", [])) > 0 or len(data.get("summary", "")) > 10)
                ui_desc = f"Cricket card with {len(data.get('articles', []))} match updates / news articles"
            elif tid == "TEST 6":
                is_pdf = data.get("format") == "pdf" and data.get("base64_data") and base64.b64decode(data["base64_data"])[:4] == b'%PDF'
                passed = data.get("success") and is_pdf
                ui_desc = f"Document card '{data.get('title')}' with working Download PDF button ({len(data.get('base64_data', ''))} b64 chars)"
            elif tid == "TEST 7":
                is_docx = data.get("format") == "docx" and data.get("base64_data") and base64.b64decode(data["base64_data"])[:2] == b'PK'
                passed = data.get("success") and is_docx
                ui_desc = f"Document card '{data.get('title')}' with working Download DOCX button ({len(data.get('base64_data', ''))} b64 chars)"
            elif tid == "TEST 8":
                passed = data.get("success") and (data.get("image") or data.get("image_b64"))
                ui_desc = f"AI Generated Image card from {data.get('provider')} ({data.get('model')})"
            elif tid == "TEST 9":
                passed = data.get("success") == True and len(data.get("images", [])) > 0 and all("allu arjun" in img["title"].lower() for img in data.get("images", []))
                ui_desc = f"Real Web Image Gallery with {len(data.get('images', []))} verified Allu Arjun photos"
            elif tid == "TEST 10":
                passed = bool(data.get("response")) and not data.get("is_error")
                ui_desc = f"Conversational AI response from {data.get('provider')} ({len(data.get('response', ''))} chars)"

            result_str = "PASS" if passed else "FAIL"
            print(f"  Result: [{result_str}] {ui_desc}")
            results.append({"tid": tid, "query": query, "endpoint": endpoint, "status": result_str, "ui_desc": ui_desc})
    except Exception as e:
        print(f"  Result: [FAIL] Exception: {e}")
        results.append({"tid": tid, "query": query, "endpoint": endpoint, "status": "FAIL", "ui_desc": str(e)})

print("\n" + "=" * 90)
passed_count = sum(1 for r in results if r["status"] == "PASS")
print(f"PHASE 7 SUMMARY: {passed_count}/10 TESTS PASSED")
print("=" * 90)
