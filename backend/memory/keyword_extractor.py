"""Keyword Extractor — extract meaningful keywords from text for memory retrieval.

Pure Python, no external dependencies.
"""

from __future__ import annotations

import re
from collections import Counter

# ---------------------------------------------------------------------------
# Stopwords — common English words to filter out
# ---------------------------------------------------------------------------
STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "not", "no", "nor",
    "so", "yet", "both", "either", "neither", "each", "every", "all",
    "any", "few", "more", "most", "other", "some", "such", "that", "this",
    "these", "those", "then", "than", "too", "very", "just", "also",
    "only", "even", "much", "many", "into", "about", "above", "after",
    "before", "between", "during", "if", "its", "it", "he", "she", "we",
    "you", "they", "them", "their", "there", "here", "when", "where",
    "which", "who", "how", "what", "why", "my", "your", "our", "his",
    "her", "get", "set", "use", "used", "using", "make", "made", "add",
    "new", "now", "need", "want", "like", "go", "come", "up", "out",
    "i", "me", "us", "am", "as", "at", "oh", "ok", "yes", "no",
    "please", "thanks", "hello", "hi",
})

# ---------------------------------------------------------------------------
# Tech patterns — words that signal programming/tech domains; get a score boost
# ---------------------------------------------------------------------------
TECH_BOOST: dict[str, float] = {
    # Languages
    "python": 2.0, "javascript": 2.0, "typescript": 2.0, "rust": 2.0,
    "golang": 2.0, "java": 1.5, "cpp": 1.5, "csharp": 1.5, "ruby": 1.5,
    # Frameworks
    "fastapi": 2.5, "django": 2.0, "flask": 2.0, "react": 2.0,
    "vue": 2.0, "angular": 2.0, "nextjs": 2.0, "express": 1.5,
    "sqlalchemy": 2.0, "pydantic": 2.0,
    # Concepts
    "api": 2.0, "endpoint": 2.0, "router": 2.0, "database": 2.0,
    "sql": 2.0, "postgres": 2.0, "sqlite": 2.0, "mongodb": 2.0,
    "auth": 2.0, "jwt": 2.5, "oauth": 2.5, "security": 2.0,
    "websocket": 2.5, "streaming": 2.0, "async": 1.5,
    "test": 1.5, "pytest": 2.0, "jest": 2.0,
    "docker": 2.0, "kubernetes": 2.0, "deploy": 1.5,
    "agent": 2.0, "llm": 2.5, "tool": 1.5, "prompt": 1.5,
    # Common code actions
    "refactor": 2.0, "debug": 2.0, "fix": 1.5, "implement": 1.5,
    "optimize": 2.0, "migrate": 2.0,
}

# Regex to find word tokens (letters, digits, underscore; min 3 chars)
_TOKEN_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b")


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Extract the most relevant keywords from text.

    1. Tokenize with a word-boundary regex
    2. Filter stopwords and very short tokens
    3. Apply tech boost weights
    4. Return top-N by weighted frequency
    """
    tokens = _TOKEN_RE.findall(text.lower())
    # Filter stopwords
    tokens = [t for t in tokens if t not in STOPWORDS]

    # Weighted frequency count
    counts: Counter[str] = Counter()
    for token in tokens:
        weight = TECH_BOOST.get(token, 1.0)
        counts[token] += weight

    # Return top-N as a plain list
    return [word for word, _ in counts.most_common(top_n)]


def score_relevance(item_text: str, keywords: list[str]) -> float:
    """Score how relevant item_text is to the given keywords.

    Higher = more relevant.
    """
    if not keywords:
        return 0.0

    item_lower = item_text.lower()
    score = 0.0
    for kw in keywords:
        if kw in item_lower:
            boost = TECH_BOOST.get(kw, 1.0)
            score += boost
    # Normalize by keyword count so short queries don't dominate
    return score / len(keywords)
