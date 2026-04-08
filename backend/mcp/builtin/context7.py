"""Context7 MCP service for official documentation lookup."""

from __future__ import annotations

from typing import Any

from backend.mcp.client import BuiltinMCPs, MCPError, MCPManager, mcp_manager


class Context7Service:
    """Context7 service for documentation lookup."""

    def __init__(self, manager: MCPManager | None = None):
        self.manager = manager or mcp_manager
        self._setup()

    def _setup(self) -> None:
        """Setup the context7 MCP."""
        config = BuiltinMCPs.context7()
        self.manager.register(config)

    async def get_docs(
        self,
        library: str,
        version: str | None = None,
        question: str | None = None
    ) -> dict[str, Any]:
        """
        Get documentation for a library/framework.
        
        Args:
            library: Library name (e.g., "react", "fastapi")
            version: Optional version constraint
            question: Optional question about the docs
            
        Returns:
            Documentation content
        """
        try:
            params = {"library": library}
            if version:
                params["version"] = version
            if question:
                params["question"] = question

            result = await self.manager.call_tool("context7", "getDocumentation", params)
            return result
        except MCPError as e:
            return {"error": str(e), "content": ""}

    async def search_docs(
        self,
        library: str,
        query: str
    ) -> dict[str, Any]:
        """
        Search documentation for a library.
        
        Args:
            library: Library name
            query: Search query
            
        Returns:
            Search results from docs
        """
        try:
            result = await self.manager.call_tool(
                "context7",
                "searchDocumentation",
                {
                    "library": library,
                    "query": query
                }
            )
            return result
        except MCPError as e:
            return {"error": str(e), "results": []}


context7_service = Context7Service()
