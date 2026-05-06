"""add documents.ingestion_progress column when missing"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260410_0010"
down_revision = "20260410_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    document_columns = {column["name"] for column in inspector.get_columns("documents")}

    if "ingestion_progress" not in document_columns:
        op.add_column(
            "documents",
            sa.Column(
                "ingestion_progress",
                sa.Float(),
                nullable=True,
                server_default="0",
            ),
        )
        op.execute("UPDATE documents SET ingestion_progress = 0 WHERE ingestion_progress IS NULL")
        op.alter_column(
            "documents",
            "ingestion_progress",
            server_default=None,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    if "ingestion_progress" in document_columns:
        op.drop_column("documents", "ingestion_progress")
