"""add audit columns to search_history (tender_id, route_key, llm_route, anonymized, retrieval_version, sources_json, settings_json)"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260429_0013"
down_revision = "20260419_0012"
branch_labels = None
depends_on = None


_TABLE = "search_history"


def _existing_columns(inspector) -> set[str]:
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _existing_columns(inspector)

    if "tender_id" not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                "tender_id",
                sa.Integer(),
                sa.ForeignKey("tenders.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "route_key" not in columns:
        op.add_column(_TABLE, sa.Column("route_key", sa.String(length=16), nullable=True))
    if "llm_route" not in columns:
        op.add_column(_TABLE, sa.Column("llm_route", sa.String(length=64), nullable=True))
    if "anonymized" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("anonymized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "retrieval_version" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("retrieval_version", sa.String(length=32), nullable=True),
        )
    if "sources_json" not in columns:
        op.add_column(_TABLE, sa.Column("sources_json", JSONB(), nullable=True))
    if "settings_json" not in columns:
        op.add_column(_TABLE, sa.Column("settings_json", JSONB(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _existing_columns(inspector)

    for col in (
        "settings_json",
        "sources_json",
        "retrieval_version",
        "anonymized",
        "llm_route",
        "route_key",
        "tender_id",
    ):
        if col in columns:
            op.drop_column(_TABLE, col)
