"""
Tests for bugs 7, 10, 13, 15 from codebase analysis.
"""
import ast
import json
from pathlib import Path
import pytest


_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _read_backend_source(relative_path: str) -> str:
    return (_BACKEND_ROOT / relative_path).read_text(encoding="utf-8")


# ── Bug 7: Tender update missing FOR UPDATE ──

def test_bug7_tender_update_uses_for_update():
    """tenders.py — update_tender should use SELECT FOR UPDATE to prevent race conditions."""
    source = _read_backend_source("app/api/tenders.py")

    # Find the update_tender function
    func_start = source.index("async def update_tender")
    # Find the next route decorator or function
    next_route = source.find("\n@router.", func_start + 1)
    func_body = source[func_start:next_route] if next_route != -1 else source[func_start:]

    # The update path should use with_for_update() to prevent concurrent overwrites
    assert "with_for_update" in func_body or "for_update" in func_body, (
        "update_tender should use SELECT ... FOR UPDATE to prevent concurrent "
        "updates from overwriting each other (lost update race condition)."
    )


# ── Bug 10: Qdrant vector dimension mismatch ──

def test_bug10_qdrant_dimension_validation():
    """dense_retriever.py — _ensure_collection should validate dimension of existing collections."""
    source = _read_backend_source("app/rag/dense_retriever.py")

    func_start = source.index("def _ensure_collection")
    next_func = source.find("\n    def ", func_start + 1)
    func_body = source[func_start:next_func] if next_func != -1 else source[func_start:]

    # The else branch (collection exists) should check dimension
    assert "else:" in func_body, (
        "_ensure_collection must have an else branch to validate existing collections"
    )
    else_body = func_body[func_body.index("else:"):]
    assert "mismatch" in else_body.lower() or "existing_size" in else_body, (
        "_ensure_collection should detect dimension mismatch on existing collections. "
        "A model change causes silent search failures without this check."
    )


# ── Bug 13: Proposal section content dict|str inconsistency ──

def test_bug13_section_content_normalized():
    """proposals.py — section content should be normalized to dict before saving to JSONB."""
    source = _read_backend_source("app/api/proposals.py")

    # Check that the code handles str→dict conversion when saving section content.
    # The DB column is JSONB (expects dict for TipTap format), but the schema accepts str.
    # There should be normalization logic.
    has_content_normalization = (
        "isinstance" in source and "content" in source and ("str" in source)
        and ("_text_to_tiptap" in source or "tiptap" in source.lower() or "normalize" in source.lower()
             or '"type": "doc"' in source or "type.*doc" in source)
    )

    assert has_content_normalization, (
        "proposals.py should normalize string content to TipTap dict format before saving. "
        "Passing a raw string to a JSONB column expecting TipTap format causes "
        "_section_content_to_text() to return empty string."
    )


# ── Bug 15: MinIO blocking calls without run_in_executor ──

def test_bug15_minio_uses_executor():
    """onlyoffice.py — MinIO sync operations should use run_in_executor to avoid blocking event loop."""
    source = _read_backend_source("app/api/onlyoffice.py")

    # Find the MinioDocumentStore class
    class_start = source.index("class MinioDocumentStore")
    class_end = source.index("\n# Singleton", class_start)
    class_body = source[class_start:class_end]

    # The async methods should use run_in_executor or asyncio.to_thread for blocking minio calls
    assert "run_in_executor" in class_body or "to_thread" in class_body, (
        "MinioDocumentStore async methods call synchronous minio client directly, "
        "blocking the asyncio event loop. Should use loop.run_in_executor() or "
        "asyncio.to_thread() for all minio operations."
    )
