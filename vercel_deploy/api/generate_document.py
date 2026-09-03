"""
NOVA Web API — /api/generate_document
AI-powered document generation engine supporting PDF (via ReportLab), DOCX (via python-docx), TXT, and Markdown.
"""

import os
import sys
import io
import json
import re
import time
import base64
import datetime
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from dotenv import load_dotenv

_env_loaded = False

def _ensure_env():
    global _env_loaded
    if _env_loaded:
        return
    here = Path(__file__).resolve().parent
    candidates = [here, here.parent, Path.cwd(), here.parent.parent]
    for directory in candidates:
        for filename in (".env.local", ".env"):
            env_path = directory / filename
            if env_path.is_file():
                load_dotenv(dotenv_path=env_path, override=False)
    _env_loaded = True

def _get_api_key(var_name: str) -> str | None:
    _ensure_env()
    key = os.environ.get(var_name, "")
    placeholders = {
        "your_gemini_api_key_here", "your_api_key", "your_api_key_here",
        "your_gemini_api_key", "your_groq_api_key_here"
    }
    if key and key.strip() and key.strip().lower() not in placeholders:
        return key.strip()
    return None

def _safe_log(msg: str):
    try:
        sys.stderr.write(f"[DOC_GEN] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


# ===========================================================================
# 1. DOCUMENT CONTENT SYNTHESIS (LLM + Rule Fallback)
# ===========================================================================

DOC_SYSTEM_PROMPT = """You are a professional document creator.
Given a user request to generate a document (e.g. resume, roadmap, project report, cover letter, notes, study plan, README):
Generate a comprehensive, high-quality, professional structured document in JSON format.

Output MUST be valid JSON with this exact schema:
{
  "title": "Document Title",
  "subtitle": "Document Subtitle / Purpose",
  "author": "Prepared by NOVA AI Assistant",
  "sections": [
    {
      "heading": "Section Heading",
      "paragraphs": ["Paragraph 1 text..."],
      "bullets": ["Bullet point 1", "Bullet point 2"]
    }
  ]
}
Do NOT include markdown formatting in the JSON keys. Output strictly valid JSON."""

def _generate_document_structure(prompt: str) -> dict:
    """Generate structured document sections using Gemini / Groq or intelligent template."""
    gemini_key = _get_api_key("GEMINI_API_KEY")
    groq_key = _get_api_key("GROQ_API_KEY")

    # Try Groq for fast structured JSON
    if groq_key:
        for g_model in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "groq/compound-mini", "qwen/qwen3.6-27b"]:
            try:
                req_data = {
                    "model": g_model,
                    "messages": [
                        {"role": "system", "content": DOC_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Create a comprehensive document for: {prompt}"}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2
                }
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps(req_data).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {groq_key}",
                        "User-Agent": "NOVA-DocGen/3.0"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    doc_json = json.loads(content)
                    if doc_json.get("title") and doc_json.get("sections"):
                        return doc_json
            except Exception as ge:
                _safe_log(f"Groq doc generation failed ({g_model}): {ge}")

    # Intelligent Fallback Templates
    clean_p = prompt.lower()
    if "python" in clean_p and ("roadmap" in clean_p or "learning" in clean_p or "plan" in clean_p):
        return {
            "title": "Python Learning Roadmap",
            "subtitle": "Complete Step-by-Step Curriculum from Basics to Advanced Mastery",
            "author": "NOVA AI Assistant",
            "sections": [
                {
                    "heading": "1. Python Basics",
                    "paragraphs": ["Getting started with Python installation, interpreter, script execution, syntax, and comments."],
                    "bullets": ["Installing Python 3 & VS Code setup", "Interactive REPL vs Python Scripts", "Basic Syntax, Indentation, and PEP 8 Standards"]
                },
                {
                    "heading": "2. Variables and Data Types",
                    "paragraphs": ["Understanding dynamic typing, primitive variables, strings, booleans, and type casting."],
                    "bullets": ["Numbers (int, float, complex) and Arithmetic operations", "Strings: Slicing, Methods, and f-string formatting", "Type conversion: int(), str(), float(), bool()"]
                },
                {
                    "heading": "3. Conditions and Loops",
                    "paragraphs": ["Controlling execution flow with conditional branching and iteration."],
                    "bullets": ["if, elif, else conditional blocks and logical operators (and, or, not)", "for loops, range(), and enumerate()", "while loops, break, continue, and pass statements"]
                },
                {
                    "heading": "4. Functions",
                    "paragraphs": ["Writing reusable, modular functions with arguments and return values."],
                    "bullets": ["Defining functions with def, default parameters, and keyword arguments", "*args and **kwargs for variable positional/keyword parameters", "Lambda functions, Scope (LEGB rule), and Docstrings"]
                },
                {
                    "heading": "5. Lists, Tuples, Sets and Dictionaries",
                    "paragraphs": ["Mastering built-in composite data structures and collections."],
                    "bullets": ["Lists: Indexing, Slicing, Methods (append, extend, pop), and List Comprehensions", "Tuples: Immutability and Tuple unpacking", "Sets: Unique elements and Mathematical set operations (union, intersection)", "Dictionaries: Key-value pairs, Dict comprehensions, and Dictionary methods"]
                },
                {
                    "heading": "6. Object-Oriented Programming (OOP)",
                    "paragraphs": ["Designing software using object-oriented paradigms and design patterns."],
                    "bullets": ["Classes, Objects, __init__ constructor, and self", "Encapsulation, Private attributes, and Property decorators", "Inheritance, super(), and Method Overriding", "Polymorphism, Abstract Base Classes, and Dunder methods (__str__, __repr__, __len__)"]
                },
                {
                    "heading": "7. File Handling",
                    "paragraphs": ["Reading, writing, and managing local file systems efficiently."],
                    "bullets": ["open() with 'r', 'w', 'a' modes and encoding='utf-8'", "with open() context managers for automatic resource cleanup", "Working with JSON, CSV, and pathlib module"]
                },
                {
                    "heading": "8. Exception Handling",
                    "paragraphs": ["Gracefully intercepting runtime errors and debugging software."],
                    "bullets": ["try, except, else, and finally blocks", "Catching specific exceptions (ValueError, KeyError, TypeError)", "Raising custom exceptions and debugging with traceback"]
                },
                {
                    "heading": "9. Modules and Packages",
                    "paragraphs": ["Organizing codebases into modular reusable components."],
                    "bullets": ["import statements and __name__ == '__main__' guard", "Standard Library: os, sys, math, datetime, re, collections", "Virtual environments (venv/uv) and pip package manager"]
                },
                {
                    "heading": "10. Advanced Python",
                    "paragraphs": ["Advanced language features for high-performance scalable engineering."],
                    "bullets": ["Iterators, Generators, and the yield keyword", "Decorators with @functools.wraps and Parameterized decorators", "Concurrency: Asyncio (async/await), Threading, and Multiprocessing", "Type Hints and Static Type Checking with mypy"]
                },
                {
                    "heading": "11. Projects",
                    "paragraphs": ["Practical real-world projects to solidify your Python knowledge."],
                    "bullets": ["Beginner: CLI Task Manager, Web Scraper (BeautifulSoup), Currency Converter", "Intermediate: REST API Backend with FastAPI / SQLite, Automation Bot", "Advanced: Full-Stack AI Chatbot with Google Gemini / Groq API, Real-Time Dashboard"]
                },
                {
                    "heading": "12. Next Steps",
                    "paragraphs": ["Recommended career pathways and specialization tracks."],
                    "bullets": ["Backend Engineering: FastAPI, Django, PostgreSQL, Redis, Docker", "Data Science & AI: NumPy, Pandas, Scikit-Learn, PyTorch, LangChain", "DevOps & Cloud: CI/CD with GitHub Actions, AWS Lambda, Kubernetes"]
                }
            ]
        }
    elif "resume" in clean_p or "cv" in clean_p:
        return {
            "title": "Professional Software Engineer Resume",
            "subtitle": "Senior Full-Stack & AI Systems Developer",
            "author": "NOVA AI Assistant",
            "sections": [
                {
                    "heading": "Professional Summary",
                    "paragraphs": [
                        "Results-driven Senior Software Engineer with 5+ years of experience in architecting scalable web applications, real-time AI systems, and cloud backend services. Adept at leading cross-functional teams, optimizing system performance, and delivering robust software solutions."
                    ],
                    "bullets": []
                },
                {
                    "heading": "Technical Skills",
                    "paragraphs": ["Core competencies and technical stack expertise:"],
                    "bullets": [
                        "Languages: Python, JavaScript, TypeScript, SQL, HTML5, CSS3",
                        "Frameworks: FastAPI, Django, React, Next.js, Node.js",
                        "AI & ML: OpenAI API, Google Gemini, LangChain, Multimodal Vision, Embeddings",
                        "Databases & Cloud: PostgreSQL, Redis, MongoDB, AWS, Docker, Git, CI/CD"
                    ]
                },
                {
                    "heading": "Professional Experience",
                    "paragraphs": ["Senior Full-Stack Engineer — Tech Innovations Inc. (2022 - Present)"],
                    "bullets": [
                        "Architected real-time AI assistant platform serving 100K+ daily active users with 99.9% uptime.",
                        "Reduced backend API latency by 45% through async query optimization and Redis distributed caching.",
                        "Engineered zero-dependency microservices for document generation and real-time live data aggregation.",
                        "Mentored 6 junior engineers and spearheaded automated testing adoption, reaching 90%+ code coverage."
                    ]
                },
                {
                    "heading": "Education & Certifications",
                    "paragraphs": ["Bachelor of Technology in Computer Science & Engineering"],
                    "bullets": [
                        "AWS Certified Solutions Architect",
                        "Certified Kubernetes Application Developer (CKAD)"
                    ]
                }
            ]
        }
    elif "readme" in clean_p:
        return {
            "title": "Project README & Technical Documentation",
            "subtitle": "Overview, Setup, and API Specification",
            "author": "NOVA AI Assistant",
            "sections": [
                {
                    "heading": "Overview",
                    "paragraphs": [
                        "This project is a modern, high-performance web service providing real-time AI assistance, intelligent document generation, live data synchronization, and multimodal computer vision capabilities."
                    ],
                    "bullets": []
                },
                {
                    "heading": "Features",
                    "paragraphs": ["Key features included in this release:"],
                    "bullets": [
                        "Live Information System: Real-time weather, news, sports, and financial rates",
                        "Document Generation: PDF, DOCX, TXT, and Markdown export",
                        "Multimodal Vision Analysis & OCR: Text extraction, UI/UX audit, error debugging",
                        "Celebrity-Aware AI Image Generation & Web Search Integration"
                    ]
                },
                {
                    "heading": "Installation & Quick Start",
                    "paragraphs": ["Follow these steps to run the application locally:"],
                    "bullets": [
                        "1. Clone the repository: git clone https://github.com/example/project.git",
                        "2. Install dependencies: pip install -r requirements.txt",
                        "3. Configure environment: cp .env.example .env",
                        "4. Start development server: python server.py"
                    ]
                }
            ]
        }
    else:
        # General Document
        title = prompt.title()[:60]
        return {
            "title": title,
            "subtitle": "Comprehensive Guide & Summary",
            "author": "NOVA AI Assistant",
            "sections": [
                {
                    "heading": "Executive Summary",
                    "paragraphs": [f"This document provides a structured analysis and detailed walkthrough for '{prompt}'."],
                    "bullets": [
                        "Core objectives and fundamental principles",
                        "Key requirements, milestones, and actionable recommendations",
                        "Best practices and standard implementation procedures"
                    ]
                },
                {
                    "heading": "Key Analysis & Implementation Points",
                    "paragraphs": ["Detailed breakdown of recommended steps:"],
                    "bullets": [
                        "Phase 1: Planning, environment configuration, and requirement validation",
                        "Phase 2: Execution, modular development, and error handling",
                        "Phase 3: Testing, verification, and deployment optimization"
                    ]
                },
                {
                    "heading": "Conclusion & Next Steps",
                    "paragraphs": ["Review the outlined recommendations and proceed with systematic execution."],
                    "bullets": []
                }
            ]
        }


# ===========================================================================
# 2. PDF GENERATOR (ReportLab)
# ===========================================================================

def _build_pdf(doc_data: dict) -> bytes:
    """Compile document structure into a polished PDF using ReportLab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    # Custom Clean Palette
    primary_color = colors.HexColor("#0f172a")    # Slate 900
    accent_color  = colors.HexColor("#0284c7")    # Sky 600
    text_color    = colors.HexColor("#334155")    # Slate 700
    bg_light      = colors.HexColor("#f8fafc")    # Slate 50

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=primary_color,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=accent_color,
        spaceAfter=12
    )

    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=14
    )

    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=text_color,
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=text_color,
        leftIndent=14,
        spaceAfter=3
    )

    story = []

    # Header
    story.append(Paragraph(doc_data.get("title", "Document"), title_style))
    if doc_data.get("subtitle"):
        story.append(Paragraph(doc_data["subtitle"], subtitle_style))
    
    date_str = datetime.datetime.now().strftime("%B %d, %Y")
    author_str = f"Generated by {doc_data.get('author', 'NOVA AI')} &bull; {date_str}"
    story.append(Paragraph(author_str, meta_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=accent_color, spaceBefore=2, spaceAfter=14))

    # Sections
    for sec in doc_data.get("sections", []):
        heading = sec.get("heading", "")
        if heading:
            story.append(Paragraph(heading, h1_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=2, spaceAfter=8))
        
        for p in sec.get("paragraphs", []):
            if p:
                story.append(Paragraph(p, body_style))
        
        for b in sec.get("bullets", []):
            if b:
                bullet_text = f"&bull;&nbsp;&nbsp;{b}"
                story.append(Paragraph(bullet_text, bullet_style))
        
        story.append(Spacer(1, 8))

    doc.build(story)
    return buf.getvalue()


# ===========================================================================
# 3. DOCX GENERATOR (python-docx)
# ===========================================================================

def _build_docx(doc_data: dict) -> bytes:
    """Compile document structure into a clean DOCX file using python-docx."""
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = docx.Document()

    # Set Margins
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    # Title
    title_p = doc.add_paragraph()
    title_run = title_p.add_run(doc_data.get("title", "Document"))
    title_run.font.name = "Arial"
    title_run.font.size = Pt(20)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(15, 23, 42)
    title_p.paragraph_format.space_after = Pt(2)

    # Subtitle
    if doc_data.get("subtitle"):
        sub_p = doc.add_paragraph()
        sub_run = sub_p.add_run(doc_data["subtitle"])
        sub_run.font.name = "Arial"
        sub_run.font.size = Pt(11)
        sub_run.font.color.rgb = RGBColor(2, 132, 199)
        sub_p.paragraph_format.space_after = Pt(4)

    # Meta / Author
    meta_p = doc.add_paragraph()
    date_str = datetime.datetime.now().strftime("%B %d, %Y")
    meta_run = meta_p.add_run(f"Generated by {doc_data.get('author', 'NOVA AI')} | {date_str}")
    meta_run.font.name = "Arial"
    meta_run.font.size = Pt(9)
    meta_run.font.italic = True
    meta_run.font.color.rgb = RGBColor(100, 116, 139)
    meta_p.paragraph_format.space_after = Pt(16)

    # Sections
    for sec in doc_data.get("sections", []):
        heading = sec.get("heading", "")
        if heading:
            h = doc.add_heading(level=1)
            hrun = h.add_run(heading)
            hrun.font.name = "Arial"
            hrun.font.size = Pt(13)
            hrun.font.bold = True
            hrun.font.color.rgb = RGBColor(15, 23, 42)
            h.paragraph_format.space_before = Pt(12)
            h.paragraph_format.space_after = Pt(6)

        for p in sec.get("paragraphs", []):
            if p:
                par = doc.add_paragraph()
                prun = par.add_run(p)
                prun.font.name = "Calibri"
                prun.font.size = Pt(10.5)
                prun.font.color.rgb = RGBColor(51, 65, 85)
                par.paragraph_format.space_after = Pt(4)

        for b in sec.get("bullets", []):
            if b:
                bp = doc.add_paragraph(style='List Bullet')
                brun = bp.add_run(b)
                brun.font.name = "Calibri"
                brun.font.size = Pt(10)
                brun.font.color.rgb = RGBColor(51, 65, 85)
                bp.paragraph_format.space_after = Pt(2)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ===========================================================================
# 4. TXT & MARKDOWN GENERATORS
# ===========================================================================

def _build_txt(doc_data: dict) -> bytes:
    """Compile document into clean UTF-8 plain text."""
    lines = []
    lines.append("=" * 70)
    lines.append(doc_data.get("title", "DOCUMENT").upper())
    if doc_data.get("subtitle"):
        lines.append(doc_data["subtitle"])
    lines.append(f"Generated by: {doc_data.get('author', 'NOVA AI')} | {datetime.datetime.now().strftime('%Y-%m-%d')}")
    lines.append("=" * 70)
    lines.append("")

    for sec in doc_data.get("sections", []):
        heading = sec.get("heading", "")
        if heading:
            lines.append(f"[{heading.upper()}]")
            lines.append("-" * len(heading))
        for p in sec.get("paragraphs", []):
            if p: lines.append(p)
        for b in sec.get("bullets", []):
            if b: lines.append(f"  * {b}")
        lines.append("")

    return "\n".join(lines).encode("utf-8")


def _build_markdown(doc_data: dict) -> bytes:
    """Compile document into GitHub Flavored Markdown."""
    lines = []
    lines.append(f"# {doc_data.get('title', 'Document')}\n")
    if doc_data.get("subtitle"):
        lines.append(f"> **{doc_data['subtitle']}**\n")
    lines.append(f"*Generated by {doc_data.get('author', 'NOVA AI')} on {datetime.datetime.now().strftime('%B %d, %Y')}*\n")
    lines.append("---\n")

    for sec in doc_data.get("sections", []):
        heading = sec.get("heading", "")
        if heading:
            lines.append(f"## {heading}\n")
        for p in sec.get("paragraphs", []):
            if p: lines.append(f"{p}\n")
        for b in sec.get("bullets", []):
            if b: lines.append(f"- {b}")
        lines.append("")

    return "\n".join(lines).encode("utf-8")


# ===========================================================================
# 5. IMAGE TO PDF GENERATOR
# ===========================================================================

def generate_image_pdf(prompt: str, image_b64: str, image_mime: str = "image/jpeg") -> dict:
    """Convert an uploaded or referenced image into a styled downloadable PDF document."""
    try:
        from PIL import Image as PILImage
        img_bytes = base64.b64decode(image_b64)
        pil_img = PILImage.open(io.BytesIO(img_bytes))

        if pil_img.mode in ("RGBA", "P"):
            pil_img = pil_img.convert("RGB")

        buf = io.BytesIO()
        doc_title = "Image Document"
        clean_p = prompt.strip()
        lower_p = clean_p.lower()

        if "krishna" in lower_p:
            doc_title = "Lord Sri Krishna - Image Document"
        elif "allu arjun" in lower_p:
            doc_title = "Allu Arjun - Photo Document"
        elif clean_p and not any(k in lower_p for k in ["ee image", "this image", "image ni", "convert", "pdf loo", "pdf chesi"]):
            doc_title = clean_p.title()[:45]

        # 1. Try ReportLab for a clean styled PDF
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image as RLImage
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors

            doc = SimpleDocTemplate(
                buf,
                pagesize=letter,
                rightMargin=40,
                leftMargin=40,
                topMargin=40,
                bottomMargin=40
            )

            styles = getSampleStyleSheet()
            primary_color = colors.HexColor("#0f172a")
            accent_color  = colors.HexColor("#0284c7")

            title_style = ParagraphStyle(
                'ImgDocTitle',
                parent=styles['Heading1'],
                fontName='Helvetica-Bold',
                fontSize=20,
                leading=24,
                textColor=primary_color,
                spaceAfter=4
            )
            meta_style = ParagraphStyle(
                'ImgDocMeta',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#64748b"),
                spaceAfter=12
            )

            story = []
            story.append(Paragraph(doc_title, title_style))
            date_str = datetime.datetime.now().strftime("%B %d, %Y")
            story.append(Paragraph(f"Converted &amp; Prepared by NOVA AI Assistant &bull; {date_str}", meta_style))
            story.append(HRFlowable(width="100%", thickness=1.5, color=accent_color, spaceBefore=2, spaceAfter=14))

            # Resize to fit printable page area
            orig_w, orig_h = pil_img.size
            max_w, max_h = 500, 560
            ratio = min(max_w / orig_w, max_h / orig_h)
            target_w = int(orig_w * ratio)
            target_h = int(orig_h * ratio)

            img_buf = io.BytesIO()
            pil_img.save(img_buf, format="JPEG", quality=95)
            img_buf.seek(0)

            rl_img = RLImage(img_buf, width=target_w, height=target_h)
            story.append(rl_img)

            doc.build(story)
            pdf_bytes = buf.getvalue()
        except Exception as rle:
            _safe_log(f"ReportLab image PDF error: {rle}, falling back to PIL direct PDF save")
            pil_buf = io.BytesIO()
            pil_img.save(pil_buf, format="PDF", resolution=100.0)
            pdf_bytes = pil_buf.getvalue()

        b64_data = base64.b64encode(pdf_bytes).decode("utf-8")
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', doc_title.lower()).strip('_') or "image_document"
        filename = f"{clean_name}.pdf"

        return {
            "success": True,
            "format": "pdf",
            "filename": filename,
            "mime_type": "application/pdf",
            "base64_data": b64_data,
            "file_size": len(pdf_bytes),
            "title": doc_title,
            "subtitle": "Image Converted to PDF",
            "summary": f"Converted image to high-quality PDF document '{filename}' ({len(pdf_bytes) // 1024 + 1} KB).",
            "sections_count": 1,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    except Exception as e:
        _safe_log(f"Image PDF conversion error: {e}")
        return generate_document(prompt, requested_format="pdf")


# ===========================================================================
# 6. MASTER DOCUMENT GENERATION ROUTER
# ===========================================================================

def generate_document(prompt: str, requested_format: str | None = None, image_b64: str | None = None, image_mime: str | None = None) -> dict:
    """Generate structured document and compile into requested format."""
    clean_p = prompt.strip()
    clean_lower = clean_p.lower()

    # If image is attached, convert image to PDF
    if image_b64:
        return generate_image_pdf(clean_p, image_b64, image_mime or "image/jpeg")

    # Detect format if not explicitly passed
    fmt = (requested_format or "").lower().strip()
    if not fmt:
        if "docx" in clean_lower or "word" in clean_lower:
            fmt = "docx"
        elif "pdf" in clean_lower:
            fmt = "pdf"
        elif "markdown" in clean_lower or "md" in clean_lower or "readme" in clean_lower:
            fmt = "md"
        elif "txt" in clean_lower or "text file" in clean_lower:
            fmt = "txt"
        else:
            fmt = "pdf"  # Default format

    doc_data = _generate_document_structure(clean_p)
    raw_title = doc_data.get("title", "document")
    sanitized_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_title.lower()).strip('_') or "generated_document"
    filename = f"{sanitized_name}.{fmt}"

    # Build binary bytes
    if fmt == "docx":
        raw_bytes = _build_docx(doc_data)
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif fmt == "txt":
        raw_bytes = _build_txt(doc_data)
        mime = "text/plain; charset=utf-8"
    elif fmt == "md":
        raw_bytes = _build_markdown(doc_data)
        mime = "text/markdown; charset=utf-8"
    else:
        # Default PDF
        fmt = "pdf"
        raw_bytes = _build_pdf(doc_data)
        mime = "application/pdf"

    b64_data = base64.b64encode(raw_bytes).decode("utf-8")
    summary = f"Generated {fmt.upper()} document '{doc_data.get('title')}' ({len(raw_bytes) // 1024 + 1} KB) with {len(doc_data.get('sections', []))} sections."

    return {
        "success": True,
        "format": fmt,
        "filename": filename,
        "mime_type": mime,
        "base64_data": b64_data,
        "file_size": len(raw_bytes),
        "title": doc_data.get("title", "Document"),
        "subtitle": doc_data.get("subtitle", ""),
        "summary": summary,
        "sections_count": len(doc_data.get("sections", [])),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }


# ===========================================================================
# REQUEST HANDLER
# ===========================================================================

class handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))

            prompt = (data.get("prompt") or data.get("query") or "").strip()
            fmt = data.get("format")
            image_b64 = data.get("image") or data.get("image_b64")
            image_mime = data.get("image_mime") or "image/jpeg"

            if not prompt and not image_b64:
                return self._json(400, {"success": False, "error": "Document prompt or image is required."})

            result = generate_document(prompt or "Image Document", requested_format=fmt, image_b64=image_b64, image_mime=image_mime)
            return self._json(200, result)

        except Exception as e:
            _safe_log(f"Document generation error: {e}")
            return self._json(200, {
                "success": False,
                "error": f"Failed to generate document: {e}",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age",       "86400")

    def _json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)
