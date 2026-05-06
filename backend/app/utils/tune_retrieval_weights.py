#!/usr/bin/env python3
# ruff: noqa: E402
"""Grid-search safe HybridRAG retrieval profiles over the curated evaluation set."""

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
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.rag_retrieval_evaluation import (
    evaluate_retrieval_baseline,
    load_retrieval_evaluation_set,
)

RETRIEVER_PROFILES = (
    {"dense": True, "sparse": True, "graph": False},
    {"dense": True, "sparse": True, "graph": True},
)
RETRIEVAL_TOP_K_OPTIONS = (5, 8, 10, 15)
DEFAULT_WEIGHT_GRID = (
    {"dense": 0.45, "sparse": 0.35, "graph": 0.15},
    {"dense": 0.35, "sparse": 0.50, "graph": 0.10},
    {"dense": 0.40, "sparse": 0.45, "graph": 0.10},
    {"dense": 0.50, "sparse": 0.40, "graph": 0.05},
)
DEFAULT_SOURCE_PAGE_ALIAS_OFFSETS = "0,-3,-4,-5"


def build_candidate_grid() -> list[dict[str, float]]:
    return [dict(item) for item in DEFAULT_WEIGHT_GRID]


def parse_source_page_alias_offsets(value: str) -> tuple[int, ...]:
    offsets: list[int] = []
    for raw_item in str(value or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            offset = int(item)
        except ValueError as exc:
            raise ValueError(f"Invalid source page alias offset: {item!r}.") from exc
        if offset not in offsets:
            offsets.append(offset)
    if not offsets:
        raise ValueError("At least one source page alias offset is required.")
    if 0 not in offsets:
        offsets.insert(0, 0)
    return tuple(offsets)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tune HybridRAG dense/sparse/graph fusion profiles."
    )
    parser.add_argument(
        "--evaluation-set",
        default=str(SCRIPT_DIR / "evaluation_set.json"),
        help="Path to evaluation_set.json.",
    )
    parser.add_argument("--precision-k", type=int, default=3)
    parser.add_argument("--tender-id", type=int, default=None)
    parser.add_argument("--doc-type", default="tender")
    parser.add_argument(
        "--source-page-alias-offsets",
        default=DEFAULT_SOURCE_PAGE_ALIAS_OFFSETS,
        help=(
            "Comma-separated retrieved-page offsets used only for PageHit calibration. "
            "Use 0 for exact-only page matching."
        ),
    )
    parser.add_argument(
        "--report-file",
        default=str(BACKEND_ROOT / "reports" / "rag-retrieval-tuning.json"),
        help="JSON report output path.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    return parser


def _sort_key(item: dict[str, Any]) -> tuple[float, float, float, float]:
    metrics = item["metrics"]
    return (
        -float(metrics["recall_at_k"]),
        -float(metrics["source_page_hit_rate"]),
        -float(metrics["precision_at_k"]),
        float(metrics["average_latency_ms"]),
    )


def sort_tuning_results(results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((dict(item) for item in results), key=_sort_key)


async def run_tuning(args: argparse.Namespace) -> dict[str, Any]:
    from app.rag.engine import HybridRAGEngine

    cases = load_retrieval_evaluation_set(args.evaluation_set)
    page_alias_offsets = parse_source_page_alias_offsets(args.source_page_alias_offsets)
    engine = HybridRAGEngine()
    results: list[dict[str, Any]] = []

    try:
        for retrievers in RETRIEVER_PROFILES:
            for top_k in RETRIEVAL_TOP_K_OPTIONS:
                for weights in build_candidate_grid():
                    report = await evaluate_retrieval_baseline(
                        engine,
                        cases,
                        top_k=top_k,
                        precision_k=args.precision_k,
                        filters={"doc_type": args.doc_type} if args.doc_type else None,
                        tender_id=args.tender_id,
                        retrievers=retrievers,
                        fusion_weights=weights,
                        source_page_alias_offsets=page_alias_offsets,
                    )
                    results.append(
                        {
                            "retrievers": dict(retrievers),
                            "retrieval_top_k": top_k,
                            "fusion_weights": dict(weights),
                            "metrics": {
                                "recall_at_k": report.recall_at_k,
                                "source_page_hit_rate": report.source_page_hit_rate,
                                "exact_source_page_hit_rate": report.exact_source_page_hit_rate,
                                "precision_at_k": report.precision_at_k,
                                "average_latency_ms": report.average_latency_ms,
                            },
                            "report": report.as_dict(),
                        }
                    )
    finally:
        await engine.shutdown()

    sorted_results = sort_tuning_results(results)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_count": len(cases),
        "candidate_count": len(sorted_results),
        "best": sorted_results[0] if sorted_results else None,
        "results": sorted_results,
    }


async def _run(args: argparse.Namespace) -> int:
    payload = await run_tuning(args)
    report_json = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(f"{report_json}\n", encoding="utf-8")

    if args.json:
        print(report_json)
    else:
        best = payload.get("best") or {}
        metrics = best.get("metrics") or {}
        print(
            "Retrieval tuning: "
            f"candidates={payload['candidate_count']} "
            f"best_recall={float(metrics.get('recall_at_k', 0.0)):.2%} "
            f"best_page_hit={float(metrics.get('source_page_hit_rate', 0.0)):.2%} "
            f"best_exact_page_hit={float(metrics.get('exact_source_page_hit_rate', 0.0)):.2%} "
            f"best_precision={float(metrics.get('precision_at_k', 0.0)):.2%}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        parse_source_page_alias_offsets(args.source_page_alias_offsets)
    except ValueError as exc:
        parser.error(str(exc))
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
