"""Web search MCP service using Exa."""

from __future__ import annotations

import os
from typing import Any

from backend.mcp.client import BuiltinMCPs, MCPError, MCPManager, mcp_manager


class WebSearchService:
    """Web search service using Exa MCP."""

    def __init__(self, manager: MCPManager | None = None):
        self.manager = manager or mcp_manager
        self._setup()

    def _setup(self) -> None:
        """Setup the websearch MCP."""
        api_key = os.environ.get("EXA_API_KEY")
        config = BuiltinMCPs.websearch(provider="exa", api_key=api_key)
        self.manager.register(config)

    async def search(
        self,
        query: str,
        num_results: int = 10,
        type: str = "auto"
    ) -> dict[str, Any]:
        """
        Search the web.
        
        Args:
            query: Search query
            num_results: Number of results (default 10)
            type: Result type (auto, keyword, neural)
            
        Returns:
            Search results with URLs and snippets
        """
        try:
            result = await self.manager.call_tool(
                "websearch",
                "web_search_exa",
                {
                    "query": query,
                    "num_results": num_results,
                    "type": type
                }
            )
            return result
        except MCPError as e:
            return {"error": str(e), "results": []}

    async def search_and_scrape(
        self,
        query: str,
        num_results: int = 5
    ) -> dict[str, Any]:
        """
        Search and scrape content from results.
        
        Args:
            query: Search query
            num_results: Number of results to scrape
            
        Returns:
            Search results with scraped content
        """
        try:
            result = await self.manager.call_tool(
                "websearch",
                "web_search_exa_and_scrape",
                {
                    "query": query,
                    "num_results": num_results
                }
            )
            return result
        except MCPError as e:
            return {"error": str(e), "results": []}


web_search_service = WebSearchService()
