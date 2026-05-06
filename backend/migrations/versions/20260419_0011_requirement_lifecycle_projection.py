"""add requirement lifecycle projection tracking column

Adds an opaque ``last_projected_at`` timestamp on ``tender_requirements``
so operators (and the lifecycle projector reconciliation path) can tell
whether the canonical row has been re-projected onto the Neo4j
``Requirement`` snapshot since its last DB-side change.

The column is purely observability: idempotency for the projection is
guaranteed by ``MERGE`` on ``RequirementEvent.external_event_id`` in
Neo4j; this column only lets us detect projection lag.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260419_0011"
down_revision = "20260410_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tender_requirements" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("tender_requirements")}
    if "last_projected_at" not in columns:
        op.add_column(
            "tender_requirements",
            sa.Column(
                "last_projected_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tender_requirements" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("tender_requirements")}
    if "last_projected_at" in columns:
        op.drop_column("tender_requirements", "last_projected_at")
