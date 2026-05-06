# ruff: noqa: N999,E402
"""Run a HybridRAG retrieval baseline over ``evaluation_set.json``.

Usage from ``backend/``:

    python3 -m app.utils.recall_cli --tender-id 123 --report-file reports/rag-baseline.json

Graph retrieval is opt-in for this baseline because current graph nodes can lack
source-page metadata and dominate fusion with generic Requirement results.
"""

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

from app.services.rag_retrieval_evaluation import (
    evaluate_retrieval_baseline,
    load_retrieval_evaluation_set,
)

ALLOWED_RETRIEVERS = ("dense", "sparse", "graph")
DEFAULT_RETRIEVERS = "dense,sparse"
SAFE_GRAPH_FUSION_WEIGHTS = {"dense": 0.45, "sparse": 0.35, "graph": 0.15}
DEFAULT_SOURCE_PAGE_ALIAS_OFFSETS = "0,-3,-4,-5"


def parse_retriever_selection(value: str) -> dict[str, bool]:
    requested = {item.strip().casefold() for item in str(value or "").split(",") if item.strip()}
    unknown = sorted(requested - set(ALLOWED_RETRIEVERS))
    if unknown:
        raise ValueError(
            f"Unknown retriever(s): {', '.join(unknown)}. Allowed: {', '.join(ALLOWED_RETRIEVERS)}."
        )
    if not requested:
        raise ValueError(f"At least one retriever is required: {', '.join(ALLOWED_RETRIEVERS)}.")
    return {key: key in requested for key in ALLOWED_RETRIEVERS}


def resolve_baseline_fusion_weights(retrievers: dict[str, bool]) -> dict[str, float]:
    if retrievers.get("graph"):
        return dict(SAFE_GRAPH_FUSION_WEIGHTS)
    return {}


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
        description="Measure HybridRAG retrieval Recall@K and Precision@K on a gold set."
    )
    parser.add_argument(
        "--evaluation-set",
        default=str(Path(__file__).with_name("evaluation_set.json")),
        help="Path to evaluation_set.json.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Recall@K retrieval depth.")
    parser.add_argument("--precision-k", type=int, default=3, help="Precision@K retrieval depth.")
    parser.add_argument("--tender-id", type=int, default=None, help="Optional tender_id filter.")
    parser.add_argument("--doc-type", default="tender", help="Document type filter.")
    parser.add_argument(
        "--retrievers",
        default=DEFAULT_RETRIEVERS,
        help=(
            "Comma-separated retrievers to enable. Default disables graph; "
            "use dense,sparse,graph to opt in."
        ),
    )
    parser.add_argument(
        "--source-page-alias-offsets",
        default=DEFAULT_SOURCE_PAGE_ALIAS_OFFSETS,
        help=(
            "Comma-separated retrieved-page offsets used only for PageHit calibration. "
            "Use 0 for exact-only page matching."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--report-file", help="Optional JSON report output path.")
    return parser


async def _run(args: argparse.Namespace) -> int:
    from app.rag.engine import HybridRAGEngine

    cases = load_retrieval_evaluation_set(args.evaluation_set)
    retrievers = getattr(args, "retriever_selection", parse_retriever_selection(args.retrievers))
    fusion_weights = resolve_baseline_fusion_weights(retrievers)
    page_alias_offsets = getattr(
        args,
        "source_page_alias_offsets_tuple",
        parse_source_page_alias_offsets(args.source_page_alias_offsets),
    )
    engine = HybridRAGEngine()
    try:
        report = await evaluate_retrieval_baseline(
            engine,
            cases,
            top_k=args.top_k,
            precision_k=args.precision_k,
            filters={"doc_type": args.doc_type} if args.doc_type else None,
            tender_id=args.tender_id,
            retrievers=retrievers,
            fusion_weights=fusion_weights,
            source_page_alias_offsets=page_alias_offsets,
        )
    finally:
        await engine.shutdown()

    payload = report.as_dict()
    report_json = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(f"{report_json}\n", encoding="utf-8")

    if args.json:
        print(report_json)
    else:
        print(
            f"Retrieval baseline: Recall@{report.top_k}={report.recall_at_k:.2%} "
            f"Precision@{report.precision_k}={report.precision_at_k:.2%} "
            f"PageHit={report.source_page_hit_rate:.2%} "
            f"ExactPageHit={report.exact_source_page_hit_rate:.2%} "
            f"LatencyAvg={report.average_latency_ms:.1f}ms "
            f"Cases={report.case_count}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.retriever_selection = parse_retriever_selection(args.retrievers)
        args.source_page_alias_offsets_tuple = parse_source_page_alias_offsets(
            args.source_page_alias_offsets
        )
    except ValueError as exc:
        parser.error(str(exc))
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
