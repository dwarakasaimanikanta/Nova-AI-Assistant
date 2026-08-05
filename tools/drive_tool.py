"""
tools/drive_tool.py
-------------------
Google Drive integration tool supporting listing and searching files.
Conforms to the BaseTool interface.
"""

from typing import Any
from tools.base_tool import BaseTool, RiskLevel
from utils.google_auth import get_google_service
from utils.logger import get_logger

logger = get_logger(__name__)


class DriveTool(BaseTool):
    """Google Drive tool to inspect and query files."""

    @property
    def name(self) -> str:
        return "drive"

    @property
    def description(self) -> str:
        return (
            "Interacts with Google Drive. "
            "Supports action='list_files' (optionally max_results), "
            "and action='search_files' (requires query, optionally max_results)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_files", "search_files"],
                    "description": "Drive action to perform.",
                },
                "query": {
                    "type": "string",
                    "description": "Sub-string matching filter for files (required for search_files, e.g. 'Project Proposal').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of files to return (default: 10).",
                    "default": 10,
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Listing and searching are read-only operations, so LOW risk.
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action parameter provided."

        try:
            service = get_google_service("drive", "v3")
        except Exception as e:
            logger.exception("Failed to connect to Google Auth/Drive service: %s", e)
            return f"Failure: Google Authentication failed: {e}"

        max_results = kwargs.get("max_results", 10)

        if action == "list_files":
            try:
                results = service.files().list(
                    pageSize=max_results,
                    fields="nextPageToken, files(id, name, mimeType)",
                ).execute()
                files = results.get("files", [])

                if not files:
                    return "No files found on Google Drive."

                lines = ["Google Drive Files:"]
                for f in files:
                    lines.append(f"- Name: {f.get('name')} | Type: {f.get('mimeType')} | ID: {f.get('id')}")

                return "\n".join(lines)
            except Exception as e:
                logger.error("Drive list error: %s", e)
                return f"Failure: Error listing files: {e}"

        elif action == "search_files":
            query = kwargs.get("query")
            if not query:
                return "Failure: Missing parameter. 'query' is required for search_files."

            try:
                # Filter by name match
                search_q = f"name contains '{query}' and trashed = false"
                results = service.files().list(
                    q=search_q,
                    pageSize=max_results,
                    fields="nextPageToken, files(id, name, mimeType)",
                ).execute()
                files = results.get("files", [])

                if not files:
                    return f"No files found matching search query: '{query}'"

                lines = [f"Search results for file query '{query}':"]
                for f in files:
                    lines.append(f"- Name: {f.get('name')} | Type: {f.get('mimeType')} | ID: {f.get('id')}")

                return "\n".join(lines)
            except Exception as e:
                logger.error("Drive search error: %s", e)
                return f"Failure: Error searching files: {e}"

        else:
            return f"Failure: Unsupported Drive action '{action}'."
