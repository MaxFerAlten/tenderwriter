"""Export reviewed consolidated requirements as a draft evaluation gold set."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export reviewed consolidated requirements as a draft evaluator gold set."
    )
    parser.add_argument(
        "--tender-id",
        action="append",
        type=int,
        dest="tender_ids",
        help="Tender id to export. Can be passed more than once. Defaults to all active graph tenders.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path where the draft gold-set JSON should be written.",
    )
    parser.add_argument(
        "--name",
        default="requirement-evaluation-draft",
        help="Name stored in the exported gold-set envelope.",
    )
    parser.add_argument(
        "--description",
        default="Draft requirement evaluation gold set exported from reviewed consolidated requirements.",
        help="Description stored in the exported gold-set envelope.",
    )
    parser.add_argument(
        "--approved-only-predictions",
        action="store_true",
        help="Use only approved graph items as predictions instead of all active graph items.",
    )
    parser.add_argument(
        "--skip-negative-cases",
        action="store_true",
        help="Do not export cases where no approved requirements or relations exist.",
    )
    return parser


async def run_export(args: argparse.Namespace) -> int:
    from app.db.database import async_session_factory
    from app.services.requirement_gold_export import (
        RequirementGoldExportOptions,
        export_requirement_gold_set_payload,
    )

    options = RequirementGoldExportOptions(
        name=args.name,
        description=args.description,
        include_pending_predictions=not args.approved_only_predictions,
        include_negative_cases=not args.skip_negative_cases,
    )
    async with async_session_factory() as session:
        payload = await export_requirement_gold_set_payload(
            session,
            tender_ids=args.tender_ids,
            options=options,
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    print(
        "Requirement gold-set draft exported: "
        f"{len(payload.get('cases') or [])} cases -> {output_path}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run_export(args))


if __name__ == "__main__":
    raise SystemExit(main())
