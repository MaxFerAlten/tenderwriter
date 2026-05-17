"""add tenders.profile_id

Revision ID: 20260517_0014
Revises: 20260429_0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260517_0014"
down_revision = "20260429_0013"
branch_labels = None
depends_on = None


_TABLE = "tenders"
_COLUMN = "profile_id"


def _existing_columns(inspector) -> set[str]:
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _COLUMN not in _existing_columns(inspector):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(length=64), nullable=True),
        )
        op.create_index(
            f"ix_{_TABLE}_{_COLUMN}", _TABLE, [_COLUMN], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _COLUMN in _existing_columns(inspector):
        op.drop_index(f"ix_{_TABLE}_{_COLUMN}", table_name=_TABLE)
        op.drop_column(_TABLE, _COLUMN)
