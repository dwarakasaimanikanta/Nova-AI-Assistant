"""
tools/document_tool.py
----------------------
Document intelligence tool supporting retrieval-augmented generation (RAG).
Conforms to the BaseTool interface.
"""

import json
from pathlib import Path
from typing import Any, List, Optional
from tools.base_tool import BaseTool, RiskLevel
from utils.document_manager import DocumentManager
from llm.provider_factory import LLMProviderFactory
from config import GEMINI_API_KEY
from utils.logger import get_logger

logger = get_logger(__name__)


class DocumentTool(BaseTool):
    """Retrieval-Augmented Generation (RAG) tool for document parsing, searches, and summarizations."""

    def __init__(self, manager: Optional[DocumentManager] = None) -> None:
        self.manager = manager or DocumentManager()

    @property
    def name(self) -> str:
        return "document"

    @property
    def description(self) -> str:
        return (
            "Retrieval-Augmented Generation (RAG) Document Intelligence. "
            "Supports: "
            "action='ingest_document' (requires filepath), "
            "action='search_documents' (requires query, optional doc_name, top_k), "
            "action='summarize_document' (requires doc_name or filepath), "
            "action='ask_document' (requires query, optional doc_name), "
            "action='compare_documents' (requires doc_names list, query)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "ingest_document", "search_documents",
                        "summarize_document", "ask_document", "compare_documents"
                    ],
                    "description": "The RAG action to perform.",
                },
                "filepath": {
                    "type": "string",
                    "description": "Path to the local document file to ingest/summarize.",
                },
                "doc_name": {
                    "type": "string",
                    "description": "Specific document filename in database to query.",
                },
                "doc_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of document filenames to compare.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query or question for text analysis.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of semantic chunks to return (default: 3).",
                    "default": 3,
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # RAG reads are LOW risk read-only actions.
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: Missing parameter 'action'."

        try:
            if action == "ingest_document":
                filepath_str = kwargs.get("filepath")
                if not filepath_str:
                    return "Failure: Parameter 'filepath' is required for ingest_document."
                
                path = Path(filepath_str)
                count = self.manager.ingest_document(path)
                return f"Success: Ingested document '{path.name}' and indexed {count} semantic chunks."

            elif action == "search_documents":
                query = kwargs.get("query")
                if not query:
                    return "Failure: Parameter 'query' is required for search_documents."
                
                doc_name = kwargs.get("doc_name")
                top_k = kwargs.get("top_k", 3)
                
                matches = self.manager.search_documents(query, doc_name=doc_name, top_k=top_k)
                if not matches:
                    return "No matching chunks found in database."
                
                lines = [f"Found {len(matches)} semantic matches:"]
                for i, match in enumerate(matches):
                    lines.append(
                        f"\n[{i+1}] Doc: {match['doc_name']} (Chunk {match['chunk_index']}, Score: {match['score']:.4f}):\n"
                        f"{match['content']}"
                    )
                return "\n".join(lines)

            elif action == "summarize_document":
                doc_name = kwargs.get("doc_name")
                filepath_str = kwargs.get("filepath")
                
                if not doc_name and not filepath_str:
                    return "Failure: Either 'doc_name' or 'filepath' is required for summarize_document."
                
                name = doc_name or Path(filepath_str).name
                
                # Retrieve first 5 chunks of document to summarize
                import sqlite3
                conn = sqlite3.connect(str(self.manager.db_path), check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content FROM document_chunks WHERE doc_name = ? ORDER BY chunk_index ASC LIMIT 5",
                    (name,)
                )
                rows = cursor.fetchall()
                conn.close()
                
                if not rows:
                    if filepath_str:
                        # Auto-ingest first
                        self.manager.ingest_document(Path(filepath_str))
                        return self.execute(action="summarize_document", doc_name=name)
                    return f"Failure: Document '{name}' is not indexed in database."
                
                context = "\n\n".join([r[0] for r in rows])
                
                # Fetch LLM to summarize
                provider = LLMProviderFactory.get_provider("routing", GEMINI_API_KEY)
                prompt = (
                    f"Please write a concise summary highlighting key points for document '{name}' "
                    f"based on the following content sections:\n\n{context}"
                )
                res = provider.generate([{"role": "user", "content": prompt}])
                
                # Handle generators or LLMResponses
                summary = res if isinstance(res, str) else getattr(res, "text", str(res))
                return f"Summary of document '{name}':\n\n{summary}"

            elif action == "ask_document":
                query = kwargs.get("query")
                if not query:
                    return "Failure: Parameter 'query' is required for ask_document."
                
                doc_name = kwargs.get("doc_name")
                matches = self.manager.search_documents(query, doc_name=doc_name, top_k=3)
                
                if not matches:
                    return f"Failure: No information found in document to answer '{query}'."
                
                context = "\n\n".join([f"Source [{m['doc_name']} Chunk {m['chunk_index']}]: {m['content']}" for m in matches])
                
                # Fetch LLM to answer
                provider = LLMProviderFactory.get_provider("routing", GEMINI_API_KEY)
                prompt = (
                    f"Answer the question: '{query}' based ONLY on the following context segments:\n\n"
                    f"{context}\n\n"
                    f"If the context does not contain the answer, say 'I cannot find the answer in the provided document segments.'"
                )
                res = provider.generate([{"role": "user", "content": prompt}])
                ans = res if isinstance(res, str) else getattr(res, "text", str(res))
                return f"Answer:\n\n{ans}"

            elif action == "compare_documents":
                doc_names = kwargs.get("doc_names")
                query = kwargs.get("query")
                if not doc_names or len(doc_names) < 2 or not query:
                    return "Failure: Parameters 'doc_names' (list of at least 2 docs) and 'query' are required for compare_documents."

                contexts = []
                for name in doc_names:
                    matches = self.manager.search_documents(query, doc_name=name, top_k=2)
                    if matches:
                        contexts.append(
                            f"=== Document: {name} ===\n" +
                            "\n\n".join([m["content"] for m in matches])
                        )
                
                if not contexts:
                    return f"No segments matching topic '{query}' found in any target documents."

                all_context = "\n\n".join(contexts)
                provider = LLMProviderFactory.get_provider("routing", GEMINI_API_KEY)
                prompt = (
                    f"Compare and contrast the following documents regarding the topic: '{query}':\n\n"
                    f"{all_context}\n\n"
                    f"Summarize the key similarities and differences."
                )
                res = provider.generate([{"role": "user", "content": prompt}])
                comparison = res if isinstance(res, str) else getattr(res, "text", str(res))
                return f"Comparison Report:\n\n{comparison}"

            else:
                return f"Failure: Unsupported RAG action '{action}'."

        except Exception as e:
            logger.error("DocumentTool execution failure: %s", e)
            return f"Failure: RAG tool execution error: {e}"
