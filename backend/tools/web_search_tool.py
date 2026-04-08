"""Web Search tool — search the web for information.

Uses httpx to query search APIs. Phase 2 supports a simple DuckDuckGo
HTML scrape. Phase 3+ will integrate Exa, Tavily, or Brave Search APIs.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.web_search")

SEARCH_TIMEOUT = 15


class WebSearchTool(BaseTool):
    """Search the web and return results."""

    name = "WebSearch"
    description = (
        "Search the web for information. Returns search results with titles, "
        "URLs, and snippets."
    )
    risk_level = RiskLevel.LOW
    is_read_only = True
    concurrency_safe = True

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results (default 5, max 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        query = tool_input.get("query", "")
        num_results = min(tool_input.get("num_results", 5), 10)

        if not query.strip():
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content="Error: empty search query",
                is_error=True,
            )

        try:
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "TenderClaw/0.1"},
                )
                resp.raise_for_status()
                results = _parse_ddg_html(resp.text, num_results)

            if not results:
                return ToolResult(
                    tool_use_id=context.tool_use_id,
                    content=f"No results found for: {query}",
                )

            output = f"Search results for '{query}':\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n\n"

            return ToolResult(tool_use_id=context.tool_use_id, content=output.strip())

        except Exception as exc:
            logger.error("Web search error: %s", exc)
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Search failed: {exc}",
                is_error=True,
            )


def _parse_ddg_html(html: str, max_results: int) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML results (simple regex extraction)."""
    import re

    results: list[dict[str, str]] = []

    # Find result links
    link_pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'class="result__snippet"[^>]*>(.*?)</(?:a|span|td)',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (url, title) in enumerate(links[:max_results]):
        clean_title = re.sub(r"<[^>]+>", "", title).strip()
        clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
        # DuckDuckGo wraps URLs in redirect
        actual_url = url
        if "uddg=" in url:
            match = re.search(r"uddg=([^&]+)", url)
            if match:
                from urllib.parse import unquote
                actual_url = unquote(match.group(1))

        results.append({"title": clean_title, "url": actual_url, "snippet": clean_snippet})

    return results
