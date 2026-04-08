"""Grep.app MCP service for GitHub code search."""

from __future__ import annotations

from typing import Any

from backend.mcp.client import BuiltinMCPs, MCPError, MCPManager, mcp_manager


class GrepAppService:
    """Grep.app service for GitHub code search."""

    def __init__(self, manager: MCPManager | None = None):
        self.manager = manager or mcp_manager
        self._setup()

    def _setup(self) -> None:
        """Setup the grep_app MCP."""
        config = BuiltinMCPs.grep_app()
        self.manager.register(config)

    async def search(
        self,
        query: str,
        repos: list[str] | None = None,
        language: str | None = None,
        max_results: int = 25
    ) -> dict[str, Any]:
        """
        Search code across GitHub repositories.
        
        Args:
            query: Code search query
            repos: Optional list of repos to search (e.g., ["github/codeql"])
            language: Optional language filter
            max_results: Maximum results (default 25)
            
        Returns:
            Code search results
        """
        try:
            params = {
                "q": query,
                "max_results": max_results
            }
            if repos:
                params["repos"] = repos
            if language:
                params["language"] = language

            result = await self.manager.call_tool("grep_app", "search_code", params)
            return result
        except MCPError as e:
            return {"error": str(e), "results": []}

    async def search_file(
        self,
        repo: str,
        file_path: str,
        query: str | None = None
    ) -> dict[str, Any]:
        """
        Search within a specific file.
        
        Args:
            repo: Repository (e.g., "facebook/react")
            file_path: Path to file
            query: Optional line search query
            
        Returns:
            File content or search results
        """
        try:
            params = {
                "repo": repo,
                "file_path": file_path
            }
            if query:
                params["q"] = query

            result = await self.manager.call_tool("grep_app", "search_file", params)
            return result
        except MCPError as e:
            return {"error": str(e), "content": ""}


grep_app_service = GrepAppService()
