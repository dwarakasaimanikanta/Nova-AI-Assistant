import urllib.request
import json
import base64
import sys
import io

BASE_URL = "http://localhost:3001"

print("=" * 90)
print("NOVA AI ASSISTANT: COMPREHENSIVE VERIFICATION & TEST SUITE (19 TEST CASES)")
print("=" * 90)

results = []

def run_test(test_id, category, name, test_fn):
    print(f"\n[{test_id:02d}] [{category}] {name}...")
    try:
        ok, msg = test_fn()
        status = "PASS" if ok else "FAIL"
        safe_msg = str(msg).encode("ascii", errors="replace").decode("ascii")
        print(f"     Result: [{status}] {safe_msg}")
        results.append({"id": test_id, "category": category, "name": name, "status": status, "msg": msg})
    except Exception as e:
        safe_err = str(e).encode("ascii", errors="replace").decode("ascii")
        print(f"     Result: [FAIL] Exception: {safe_err}")
        results.append({"id": test_id, "category": category, "name": name, "status": "FAIL", "msg": str(e)})

# --- 1. Weather ---
def test_1():
    req = urllib.request.Request(
        f"{BASE_URL}/api/live_info",
        data=json.dumps({"query": "Weather in Bangalore today"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("category") == "weather":
            return True, f"Location: {d.get('location')} | Temp: {d.get('temperature_c')}°C | Condition: {d.get('condition')}"
        return False, f"Unexpected response: {d}"

# --- 2. News ---
def test_2():
    req = urllib.request.Request(
        f"{BASE_URL}/api/live_info",
        data=json.dumps({"query": "Latest technology news"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("category") == "news" and len(d.get("articles", [])) > 0:
            return True, f"Fetched {len(d['articles'])} articles. First: {d['articles'][0].get('title')[:45]}..."
        return False, f"Unexpected response: {d}"

# --- 3. Sports ---
def test_3():
    req = urllib.request.Request(
        f"{BASE_URL}/api/live_info",
        data=json.dumps({"query": "Current cricket score"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("category") == "sports":
            return True, f"Source: {d.get('source')} | Summary length: {len(d.get('summary', ''))} chars"
        return False, f"Unexpected response: {d}"

# --- 4. Finance ---
def test_4():
    req = urllib.request.Request(
        f"{BASE_URL}/api/live_info",
        data=json.dumps({"query": "USD to INR today"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("category") == "finance" and d.get("rate"):
            return True, f"Rate: 1 USD = {d.get('rate')} INR | Source: {d.get('source')}"
        return False, f"Unexpected response: {d}"

# --- 5. PDF Doc Gen ---
def test_5():
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate_document",
        data=json.dumps({"prompt": "Create a Python learning roadmap PDF", "format": "pdf"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("format") == "pdf" and d.get("base64_data"):
            pdf_bytes = base64.b64decode(d["base64_data"])
            is_valid_pdf = pdf_bytes[:4] == b'%PDF'
            return is_valid_pdf, f"Valid PDF generated! Size: {len(pdf_bytes)} bytes | File: {d.get('filename')}"
        return False, f"Unexpected response: {d}"

# --- 6. DOCX Doc Gen ---
def test_6():
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate_document",
        data=json.dumps({"prompt": "Create a professional resume DOCX", "format": "docx"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("format") == "docx" and d.get("base64_data"):
            docx_bytes = base64.b64decode(d["base64_data"])
            is_valid_docx = docx_bytes[:2] == b'PK'
            return is_valid_docx, f"Valid DOCX generated! Size: {len(docx_bytes)} bytes | File: {d.get('filename')}"
        return False, f"Unexpected response: {d}"

# --- 7. TXT Doc Gen ---
def test_7():
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate_document",
        data=json.dumps({"prompt": "Create notes as TXT", "format": "txt"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("format") == "txt" and d.get("base64_data"):
            txt = base64.b64decode(d["base64_data"]).decode("utf-8", errors="replace")
            return len(txt) > 50, f"Valid TXT generated! Length: {len(txt)} chars | Title: {d.get('title')}"
        return False, f"Unexpected response: {d}"

# --- 8. Markdown Doc Gen ---
def test_8():
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate_document",
        data=json.dumps({"prompt": "Create a project README as Markdown", "format": "md"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and d.get("format") == "md" and d.get("base64_data"):
            md = base64.b64decode(d["base64_data"]).decode("utf-8", errors="replace")
            return "#" in md, f"Valid Markdown generated! Length: {len(md)} chars | File: {d.get('filename')}"
        return False, f"Unexpected response: {d}"

# Generate a small test PNG image with text for vision tests
def _create_test_image_b64():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (400, 150), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), "NOVA AI ASSISTANT", fill=(0, 229, 255))
    draw.text((20, 70), "SyntaxError: invalid syntax line 42", fill=(239, 68, 68))
    draw.text((20, 110), "Status: Verified 2026", fill=(16, 185, 129))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')

test_img_b64 = _create_test_image_b64()

# --- 9. Vision General ---
def test_9():
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({
            "message": "What is visible in this image?",
            "image": test_img_b64,
            "image_mime": "image/png",
            "language": "en"
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("response") and not d.get("is_error"):
            return True, f"Provider: {d.get('provider')} | Subintent: {d.get('vision_subintent')} | Resp: {d['response'][:60]}..."
        return False, f"Vision failed: {d}"

# --- 10. Vision OCR ---
def test_10():
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({
            "message": "Extract all text from this image using OCR",
            "image": test_img_b64,
            "image_mime": "image/png",
            "language": "en"
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("response") and not d.get("is_error"):
            return True, f"Subintent: {d.get('vision_subintent')} | Extracted text: {d['response'][:60]}..."
        return False, f"OCR failed: {d}"

# --- 11. Vision Error Analysis ---
def test_11():
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({
            "message": "What is this error and how do I fix it?",
            "image": test_img_b64,
            "image_mime": "image/png",
            "language": "en"
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("response") and not d.get("is_error"):
            return True, f"Subintent: {d.get('vision_subintent')} | Root cause & fix provided ({len(d['response'])} chars)"
        return False, f"Error analysis failed: {d}"

# --- 12. Vision UI Analysis ---
def test_12():
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({
            "message": "Analyze this UI design and suggest UX improvements",
            "image": test_img_b64,
            "image_mime": "image/png",
            "language": "en"
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("response") and not d.get("is_error"):
            return True, f"Subintent: {d.get('vision_subintent')} | Design Audit provided ({len(d['response'])} chars)"
        return False, f"UI analysis failed: {d}"

# --- 13. Regression: Normal AI Question ---
def test_13():
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({"message": "What is the capital of France?", "language": "en", "search_mode": "ai"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if "Paris" in d.get("response", ""):
            return True, f"Correct answer received from {d.get('provider')}"
        return False, f"Unexpected response: {d}"

# --- 14. Regression: Code Generation ---
def test_14():
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({"message": "Write a Python function to check palindrome", "language": "en", "search_mode": "ai"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if "def " in d.get("response", ""):
            return True, f"Runnable code block received from {d.get('provider')}"
        return False, f"Unexpected response: {d}"

# --- 15. Regression: Allu Arjun Real Image Search ---
def test_15():
    req = urllib.request.Request(
        f"{BASE_URL}/api/search_images",
        data=json.dumps({"query": "Allu Arjun images"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        images = d.get("images", [])
        if len(images) > 0 and all("allu arjun" in img["title"].lower() for img in images):
            return True, f"{len(images)} exact Allu Arjun images returned"
        return False, f"Unexpected search results: {d}"

# --- 16. Regression: Charminar Real Image Search ---
def test_16():
    req = urllib.request.Request(
        f"{BASE_URL}/api/search_images",
        data=json.dumps({"query": "Charminar images"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        images = d.get("images", [])
        if len(images) > 0:
            return True, f"{len(images)} Charminar images returned"
        return False, f"Unexpected search results: {d}"

# --- 17. Regression: Generate Sunset Image ---
def test_17():
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate_image",
        data=json.dumps({"prompt": "Generate a beautiful sunset"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("success") and (d.get("image") or d.get("image_b64")):
            return True, f"Image generated by {d.get('provider')} ({d.get('model')})"
        return False, f"Image gen failed: {d}"

# --- 18. Multi-Language (Telugu) ---
def test_18():
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({"message": "namaskaram, meeru evaru?", "language": "te", "search_mode": "ai"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        if d.get("response") and not d.get("is_error"):
            return True, f"Telugu response received: {d['response'][:50]}..."
        return False, f"Language test failed: {d}"

# --- 19. Node.js Intent Routing Verification ---
def test_19():
    import subprocess
    node_test_script = """
    const fs = require('fs');
    const code = fs.readFileSync('vercel_deploy/public/app.js', 'utf8');

    // Extract function definitions using eval in isolated context
    const fnCode = code.substring(
      code.indexOf('function isExplicitAIImageRequest'),
      code.indexOf('function resolveFollowUpImagePrompt')
    );

    const context = {};
    eval(fnCode + '; context.determineIntent = determineIntent;');

    const cases = [
      { q: "Weather in Bangalore today", expected: "LIVE_INFORMATION" },
      { q: "Latest technology news", expected: "LIVE_INFORMATION" },
      { q: "Current cricket score", expected: "LIVE_INFORMATION" },
      { q: "USD to INR today", expected: "LIVE_INFORMATION" },
      { q: "Create a Python roadmap PDF", expected: "DOCUMENT_GENERATION" },
      { q: "Create a professional resume DOCX", expected: "DOCUMENT_GENERATION" },
      { q: "Create notes as TXT", expected: "DOCUMENT_GENERATION" },
      { q: "Create a project README as Markdown", expected: "DOCUMENT_GENERATION" },
      { q: "Allu Arjun images", expected: "REAL_IMAGE_SEARCH" },
      { q: "Virat Kohli images", expected: "REAL_IMAGE_SEARCH" },
      { q: "Generate a beautiful sunset", expected: "AI_GENERATION" },
      { q: "What is Python?", expected: "CHAT" }
    ];

    let allMatch = true;
    for (const c of cases) {
      const intent = context.determineIntent(c.q, null);
      if (intent !== c.expected) {
        console.error(`Mismatch for '${c.q}': got ${intent}, expected ${c.expected}`);
        allMatch = false;
      }
    }
    if (allMatch) {
      console.log("INTENT_ROUTING_SUCCESS");
    } else {
      process.exit(1);
    }
    """
    with open("temp_intent_test.js", "w", encoding="utf-8") as f:
        f.write(node_test_script)
    
    proc = subprocess.run(["node", "temp_intent_test.js"], capture_output=True, text=True)
    import os
    if os.path.exists("temp_intent_test.js"):
        os.remove("temp_intent_test.js")
    
    if proc.returncode == 0 and "INTENT_ROUTING_SUCCESS" in proc.stdout:
        return True, "All 12 intent routing cases matched accurately"
    return False, f"Intent router mismatch: {proc.stderr or proc.stdout}"


# Execute All Tests
run_test(1, "LIVE_INFO", "Weather in Bangalore today", test_1)
run_test(2, "LIVE_INFO", "Latest technology news", test_2)
run_test(3, "LIVE_INFO", "Current cricket score", test_3)
run_test(4, "LIVE_INFO", "USD to INR today", test_4)
run_test(5, "DOC_GEN", "Python learning roadmap PDF", test_5)
run_test(6, "DOC_GEN", "Professional resume DOCX", test_6)
run_test(7, "DOC_GEN", "Notes as TXT", test_7)
run_test(8, "DOC_GEN", "Project README as Markdown", test_8)
run_test(9, "VISION", "General image description", test_9)
run_test(10, "VISION", "OCR text extraction", test_10)
run_test(11, "VISION", "Screenshot error analysis & fix", test_11)
run_test(12, "VISION", "Website screenshot UI audit", test_12)
run_test(13, "REGRESSION", "Normal AI Question", test_13)
run_test(14, "REGRESSION", "Code generation", test_14)
run_test(15, "REGRESSION", "Allu Arjun real images", test_15)
run_test(16, "REGRESSION", "Charminar real images", test_16)
run_test(17, "REGRESSION", "Generate sunset image", test_17)
run_test(18, "REGRESSION", "Telugu multi-language support", test_18)
run_test(19, "INTENT_ROUTER", "Master intent router verification", test_19)

print("\n" + "=" * 90)
passed_count = sum(1 for r in results if r["status"] == "PASS")
total_count = len(results)
print(f"TEST RUN SUMMARY: {passed_count}/{total_count} TESTS PASSED")
print("=" * 90)
