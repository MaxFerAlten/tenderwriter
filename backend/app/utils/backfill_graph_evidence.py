# ruff: noqa: E402
"""Backfill Qdrant retrieval chunks into Neo4j EvidenceChunk nodes."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import argparse
import asyncio

from app.services.graph_evidence_backfill import backfill_graph_evidence_chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill persisted retrieval chunks into Neo4j as EvidenceChunk nodes."
    )
    parser.add_argument("--collection", default="documents", help="Dense retriever collection.")
    parser.add_argument("--doc-type", default="tender", help="Optional doc_type filter.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max chunk count.")
    return parser


async def _run(args: argparse.Namespace) -> int:
    from app.rag.engine import HybridRAGEngine

    engine = HybridRAGEngine()
    try:
        await engine.ensure_initialized()
        if not engine.dense_retriever or not engine.graph_retriever:
            raise RuntimeError("HybridRAG dense and graph retrievers must be initialized.")
        texts, metadatas = engine.dense_retriever.load_persisted_chunks(collection=args.collection)
        synced = await backfill_graph_evidence_chunks(
            engine.graph_retriever,
            texts=texts,
            metadatas=metadatas,
            doc_type=args.doc_type or None,
            limit=args.limit,
        )
    finally:
        await engine.shutdown()

    print(f"Backfilled graph evidence chunks: {synced}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
