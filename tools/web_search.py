"""
tools/web_search.py
-------------------
Consolidated web search tool using duckduckgo_search package.
Conforms to the BaseTool interface.
"""

from typing import Any
from ddgs import DDGS

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class WebSearchTool(BaseTool):
    """Consolidated web search tool querying DuckDuckGo and returning the top 5 results."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Queries the web using DuckDuckGo search and returns the top 5 search results "
            "including title, URL, and a snippet for each result. Use this to find current "
            "information, facts, or reference tutorials on the web."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query term to look up on the web.",
                }
            },
            "required": ["query"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Web queries are read-only and LOW risk (auto-approved)
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "").strip()
        if not query:
            return "Failure: No search query provided."

        try:
            logger.info("Executing web search for query: '%s'", query)
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            if not results:
                return f"No search results found for query: '{query}'."

            formatted_results = []
            for idx, r in enumerate(results, 1):
                title = r.get("title", "No Title")
                url = r.get("href", "No URL")
                snippet = r.get("body", "No snippet available.")
                formatted_results.append(
                    f"{idx}. {title}\n"
                    f"   URL: {url}\n"
                    f"   Snippet: {snippet}"
                )

            return "\n\n".join(formatted_results)

        except Exception as e:
            logger.exception("Error during web search for query '%s': %s", query, e)
            return f"Failure executing web search: {e}"
