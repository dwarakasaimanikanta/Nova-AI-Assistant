"""
plugins/document_plugin.py
--------------------------
RAG document intelligence plugin registering the DocumentTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.document_tool import DocumentTool


class DocumentPlugin(BasePlugin):
    """Plugin providing Retrieval-Augmented Generation (RAG) document intelligence."""

    @property
    def name(self) -> str:
        return "document"

    def get_tools(self) -> list[BaseTool]:
        return [DocumentTool()]
