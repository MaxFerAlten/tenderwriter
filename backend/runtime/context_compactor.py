"""Lightweight context compactor (Wave 1).

Provides a simple API to shrink context to a target length by truncating
older messages. In a future Wave this will implement smarter pruning strategies.
"""

from __future__ import annotations

from typing import List


def compact_context(context: str, max_chars: int = 2000) -> str:
    if len(context) <= max_chars:
        return context
    return context[-max_chars:]
