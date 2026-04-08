"""Minimal SSE (Server-Sent Events) helper (Wave 1).

This is a placeholder to provide a streaming interface for the runtime layer.
"""

from __future__ import annotations

from typing import AsyncIterator


async def sse_stream_stub(event_source: list[str] | None = None) -> AsyncIterator[str]:
    """Yield a few dummy SSE chunks for testing."""
    chunks = event_source or ["data: heartbeat", "data: ping"]
    for c in chunks:
        yield f"{c}\n\n"
