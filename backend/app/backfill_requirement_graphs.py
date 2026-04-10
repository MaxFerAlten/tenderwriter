"""Backfill consolidated requirement graphs from staged extraction runs.

Usage examples:

    python -m app.backfill_requirement_graphs --dry-run
    python -m app.backfill_requirement_graphs --migrate --tender-id 12
"""

from __future__ import annotations

import argparse
import asyncio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill consolidated requirement graphs from staged requirement candidates."
    )
    parser.add_argument(
        "--tender-id",
        action="append",
        type=int,
        dest="tender_ids",
        help="Tender id to rebuild. Can be passed more than once. Defaults to all staged tenders.",
    )
    parser.add_argument(
        "--limit-runs",
        type=int,
        default=5,
        help="Number of latest extraction runs to use per tender.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the tenders that would be rebuilt without writing graph rows.",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run Alembic migrations before the backfill.",
    )
    return parser


async def run_backfill(args: argparse.Namespace) -> int:
    from app.db.database import async_session_factory
    from app.db.migrations import run_migrations
    from app.services.requirement_graph_backfill import backfill_requirement_graphs

    if args.migrate:
        await asyncio.to_thread(run_migrations)

    async with async_session_factory() as session:
        try:
            summary = await backfill_requirement_graphs(
                session,
                tender_ids=args.tender_ids,
                limit_runs=args.limit_runs,
                dry_run=args.dry_run,
            )
            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()
        except Exception:
            await session.rollback()
            raise

    mode = "planned" if summary.dry_run else "rebuilt"
    print(
        f"Requirement graph backfill {mode}: "
        f"{summary.tender_count} tenders, limit_runs={summary.limit_runs}"
    )
    for result in summary.results:
        print(
            f"- tender {result.tender_id}: {result.status}, "
            f"source={result.source}, "
            f"consolidated_requirements={result.consolidated_count}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_backfill(args))


if __name__ == "__main__":
    raise SystemExit(main())
