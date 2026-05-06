"""Evaluate requirement pipeline output against a JSON gold set."""

from __future__ import annotations

import argparse
import json

from app.services.requirement_evaluation import (
    RequirementEvaluationThresholds,
    evaluate_requirement_pipeline_payload,
    load_requirement_evaluation_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate requirement pipeline output against a JSON gold set."
    )
    parser.add_argument("gold_file", help="Path to a JSON file with requirement evaluation cases.")
    parser.add_argument("--min-recall", type=float, default=0.8, help="Minimum requirement recall.")
    parser.add_argument(
        "--min-precision", type=float, default=0.75, help="Minimum requirement precision."
    )
    parser.add_argument(
        "--min-citation-coverage",
        type=float,
        default=0.8,
        help="Minimum citation coverage among matched requirements.",
    )
    parser.add_argument(
        "--min-conflict-recall",
        type=float,
        default=0.7,
        help="Minimum recall for expected conflicts_with relations.",
    )
    parser.add_argument(
        "--match-threshold", type=float, default=0.72, help="Token overlap matching threshold."
    )
    parser.add_argument("--json", action="store_true", help="Emit the full report as JSON.")
    parser.add_argument(
        "--report-file", help="Optional path where the full JSON report should be written."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = RequirementEvaluationThresholds(
        min_requirement_recall=args.min_recall,
        min_requirement_precision=args.min_precision,
        min_citation_coverage=args.min_citation_coverage,
        min_conflict_detection_recall=args.min_conflict_recall,
    )
    report = evaluate_requirement_pipeline_payload(
        load_requirement_evaluation_payload(args.gold_file),
        thresholds=thresholds,
        match_threshold=args.match_threshold,
    )
    report_json = json.dumps(report.as_dict(), indent=2, sort_keys=True)
    if args.report_file:
        from pathlib import Path

        Path(args.report_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_file).write_text(f"{report_json}\n", encoding="utf-8")
    if args.json:
        print(report_json)
    else:
        status = "PASS" if report.passed else "FAIL"
        print(f"Requirement evaluation: {status}")
        print(
            "requirements "
            f"precision={report.requirement_precision:.3f} "
            f"recall={report.requirement_recall:.3f} "
            f"f1={report.requirement_f1:.3f} "
            f"citation_coverage={report.citation_coverage:.3f}"
        )
        print(
            "relations "
            f"precision={report.relation_precision:.3f} "
            f"recall={report.relation_recall:.3f} "
            f"conflict_recall={report.conflict_detection_recall:.3f}"
        )
        if report.failures:
            print(f"failures={', '.join(report.failures)}")
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
