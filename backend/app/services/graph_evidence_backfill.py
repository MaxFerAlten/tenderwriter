"""Backfill retrieval chunks into Neo4j as ontology-tagged evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from app.intelligence.ontology import TenderOntologyService, default_ontology_service


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_extra(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    extra = metadata.get("extra")
    return extra if isinstance(extra, Mapping) else {}


def _evidence_chunk_id(text: str, metadata: Mapping[str, Any]) -> str:
    identity_parts = (
        str(metadata.get("source_document_ref") or ""),
        str(metadata.get("document_id") or ""),
        str(metadata.get("chunk_index") or ""),
        str(metadata.get("page_number") or ""),
        text[:160],
    )
    digest = hashlib.sha256("::".join(identity_parts).encode()).hexdigest()[:20]
    return f"evidence-{digest}"


def build_evidence_chunk_payload(
    text: str,
    metadata: Mapping[str, Any],
    *,
    ontology_service: TenderOntologyService | None = None,
) -> dict[str, Any] | None:
    cleaned_text = " ".join(str(text or "").split())
    if not cleaned_text:
        return None

    tagger = ontology_service or default_ontology_service()
    tag = tagger.tag_text(
        cleaned_text,
        category=str(metadata.get("section_title") or metadata.get("doc_type") or "") or None,
    )
    ontology_payload = tag.model_dump(mode="json")
    extra = _metadata_extra(metadata)
    return {
        "id": _evidence_chunk_id(cleaned_text, metadata),
        "text": cleaned_text,
        "doc_type": metadata.get("doc_type"),
        "tender_id": metadata.get("tender_id"),
        "document_id": metadata.get("document_id"),
        "chunk_index": metadata.get("chunk_index"),
        "section_title": metadata.get("section_title"),
        "page_number": _as_int(metadata.get("page_number")),
        "source_document_ref": metadata.get("source_document_ref"),
        "procedure_key": extra.get("procedure_key") or metadata.get("procedure_key"),
        **ontology_payload,
    }


async def backfill_graph_evidence_chunks(
    graph,
    *,
    texts: Sequence[str],
    metadatas: Sequence[Mapping[str, Any]],
    doc_type: str | None = None,
    limit: int | None = None,
) -> int:
    synced = 0
    max_items = len(texts) if limit is None else max(0, int(limit))
    for text, metadata in zip(texts[:max_items], metadatas[:max_items], strict=False):
        if doc_type and metadata.get("doc_type") != doc_type:
            continue
        payload = build_evidence_chunk_payload(text, metadata)
        if not payload:
            continue
        await graph.upsert_evidence_chunk(payload)
        synced += 1
    return synced
