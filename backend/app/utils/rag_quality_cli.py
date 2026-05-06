#!/usr/bin/env python3
# ruff: noqa: N999,E402
"""Run deterministic answer-level RAG quality gates over JSON fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parents[1]

if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.rag_answer_quality_evaluation import evaluate_answer_quality_cases


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate answer-level RAG quality metrics from JSON fixtures."
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        required=True,
        help="JSON fixture file. Accepts either a list or an object with a 'cases' list.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        help="Optional path where the JSON report will be written.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON report instead of a concise text summary.",
    )
    return parser


def load_quality_fixtures(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        return [dict(item) for item in data["cases"] if isinstance(item, dict)]
    raise ValueError(f"Expected a JSON list or an object with a 'cases' list in {path}")


def _print_summary(report: dict[str, Any]) -> None:
    print(f"Cases: {report['case_count']}")
    print(f"Average duplicate block ratio: {report['average_duplicate_block_ratio']:.4f}")
    print(f"Average required fact coverage: {report['average_required_fact_coverage']:.4f}")
    print(f"Average numeric fact coverage: {report['average_numeric_fact_coverage']:.4f}")
    print(f"Unsupported entity count: {report['unsupported_entity_count']}")
    print(f"Failed case count: {report['failed_case_count']}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fixtures = load_quality_fixtures(args.fixtures)
    report = evaluate_answer_quality_cases(fixtures).to_dict()

    if args.report_file:
        args.report_file.parent.mkdir(parents=True, exist_ok=True)
        args.report_file.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_summary(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
