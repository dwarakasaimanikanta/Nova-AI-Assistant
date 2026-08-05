"""
tests/test_document.py
-----------------------
Unit tests for DocumentManager and DocumentTool RAG capabilities.
Fully mocked to ensure headless execution without requiring actual files or external network endpoints.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from utils.document_manager import DocumentManager
from tools.document_tool import DocumentTool
from llm.base_provider import LLMResponse


@pytest.fixture
def mock_db_path(tmp_path):
    """Generates a temporary database path for testing."""
    return tmp_path / "test_memory.db"


@pytest.fixture
def manager(mock_db_path):
    """Instantiates a DocumentManager backed by a temporary test database."""
    return DocumentManager(db_path=mock_db_path)


def test_chunk_text(manager) -> None:
    """DocumentManager: verify sliding window chunking handles lengths and overlaps."""
    text = "abcdefghijklmnop"
    # Chunk size: 5, Overlap: 2
    # Chunk 1: 'abcde'
    # Chunk 2: 'defgh'
    # Chunk 3: 'ghijk'
    # Chunk 4: 'jklmn'
    # Chunk 5: 'mnop'
    chunks = manager.chunk_text(text, chunk_size=5, overlap=2)
    assert chunks == ["abcde", "defgh", "ghijk", "jklmn", "mnop"]


def test_extract_txt_md(manager, tmp_path) -> None:
    """DocumentManager: verify TXT and Markdown extraction."""
    filepath = tmp_path / "test.txt"
    filepath.write_text("Hello text content", encoding="utf-8")
    
    txt = manager.extract_text(filepath)
    assert txt == "Hello text content"


def test_extract_pdf(manager, tmp_path) -> None:
    """DocumentManager: verify PDF extraction via pypdf mocks."""
    filepath = tmp_path / "test.pdf"
    filepath.write_text("fake pdf data", encoding="utf-8")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "PDF Page Text"
    
    with patch("pypdf.PdfReader") as mock_reader_class:
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader
        
        txt = manager.extract_text(filepath)
        assert txt == "PDF Page Text"
        mock_reader_class.assert_called_once_with(filepath)


def test_extract_docx(manager, tmp_path) -> None:
    """DocumentManager: verify Word extraction via docx mocks."""
    filepath = tmp_path / "test.docx"
    filepath.write_text("fake docx data", encoding="utf-8")

    mock_p = MagicMock()
    mock_p.text = "Word Paragraph Text"
    
    with patch("docx.Document") as mock_doc_class:
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_p]
        mock_doc_class.return_value = mock_doc
        
        txt = manager.extract_text(filepath)
        assert txt == "Word Paragraph Text"


def test_extract_xlsx(manager, tmp_path) -> None:
    """DocumentManager: verify Excel extraction via openpyxl mocks."""
    filepath = tmp_path / "test.xlsx"
    filepath.write_text("fake xlsx data", encoding="utf-8")

    with patch("openpyxl.load_workbook") as mock_load_wb:
        mock_sheet = MagicMock()
        mock_sheet.iter_rows.return_value = [("Cell A1", "Cell B1"), (None, None)]
        
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_sheet
        mock_load_wb.return_value = mock_wb
        
        txt = manager.extract_text(filepath)
        assert "Sheet: Sheet1" in txt
        assert "Cell A1, Cell B1" in txt


def test_extract_pptx(manager, tmp_path) -> None:
    """DocumentManager: verify PowerPoint extraction via python-pptx mocks."""
    filepath = tmp_path / "test.pptx"
    filepath.write_text("fake pptx data", encoding="utf-8")

    mock_shape = MagicMock()
    mock_shape.text = "PowerPoint Slide Text"
    
    mock_slide = MagicMock()
    mock_slide.shapes = [mock_shape]

    with patch("pptx.Presentation") as mock_presentation_class:
        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]
        mock_presentation_class.return_value = mock_prs
        
        txt = manager.extract_text(filepath)
        assert "Slide 1" in txt
        assert "PowerPoint Slide Text" in txt


def test_ingest_and_search(manager, tmp_path) -> None:
    """DocumentManager: verify document ingestion and semantic similarity lookup."""
    filepath = tmp_path / "demo.txt"
    filepath.write_text("Nova RAG. This is the first sentence. That is the second sentence.", encoding="utf-8")

    # Ingest document
    count = manager.ingest_document(filepath)
    assert count > 0

    # Search query
    matches = manager.search_documents("Nova RAG", top_k=2)
    assert len(matches) > 0
    assert matches[0]["doc_name"] == "demo.txt"
    assert "Nova RAG" in matches[0]["content"]


def test_document_tool_actions(manager, tmp_path) -> None:
    """DocumentTool: verify execute actions route correctly to LLM summaries and QA."""
    tool = DocumentTool(manager=manager)
    
    # Ingest test document
    filepath = tmp_path / "demo.txt"
    filepath.write_text("The secret code is 9988. RAG details.", encoding="utf-8")
    tool.execute(action="ingest_document", filepath=str(filepath))

    # Mock routing LLM Provider
    mock_llm = MagicMock()
    mock_llm.generate.return_value = LLMResponse("Mocked LLM summary or answer")
    
    with patch("llm.provider_factory.LLMProviderFactory.get_provider", return_value=mock_llm):
        # A. summarize_document
        res_sum = tool.execute(action="summarize_document", doc_name="demo.txt")
        assert "Summary of document" in res_sum
        assert "Mocked LLM summary" in res_sum

        # B. ask_document
        res_ask = tool.execute(action="ask_document", doc_name="demo.txt", query="what is the secret code?")
        assert "Answer" in res_ask
        assert "Mocked LLM summary" in res_ask

        # C. compare_documents
        res_comp = tool.execute(
            action="compare_documents",
            doc_names=["demo.txt", "demo.txt"],
            query="secret code"
        )
        assert "Comparison Report" in res_comp
        assert "Mocked LLM summary" in res_comp
