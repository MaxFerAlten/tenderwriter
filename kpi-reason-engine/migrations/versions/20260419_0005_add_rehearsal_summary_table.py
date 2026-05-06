"""add kpi_tender_rehearsal_summaries table

Revision ID: 20260419_0005
Revises: 20260329_0004
Create Date: 2026-04-19 11:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260419_0005"
down_revision = "20260329_0004"
branch_labels = None
depends_on = None


def _schema_name() -> str | None:
    normalized = str(op.get_context().config.get_main_option("kpi.schema") or "").strip()
    return normalized or None


def _qualified_foreign_key(table_name: str, column_name: str) -> str:
    schema_name = _schema_name()
    if schema_name:
        return f"{schema_name}.{table_name}.{column_name}"
    return f"{table_name}.{column_name}"


def _json_column_type() -> sa.types.TypeEngine:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.Text()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema_name = _schema_name()
    existing = set(inspector.get_table_names(schema=schema_name))

    if "kpi_tender_rehearsal_summaries" in existing:
        return

    op.create_table(
        "kpi_tender_rehearsal_summaries",
        sa.Column("external_tender_id", sa.Text(), primary_key=True),
        sa.Column(
            "summary_json",
            _json_column_type(),
            nullable=False,
            server_default=sa.text("'{}'") if bind.dialect.name == "sqlite" else sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["external_tender_id"],
            [_qualified_foreign_key("kpi_tenders", "external_tender_id")],
            ondelete="CASCADE",
        ),
        schema=schema_name,
    )


def downgrade() -> None:
    schema_name = _schema_name()
    op.drop_table("kpi_tender_rehearsal_summaries", schema=schema_name)
