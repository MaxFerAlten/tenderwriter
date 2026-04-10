"""add document tender lifecycle fields"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0009"
down_revision = "20260408_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("tender_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("storage_bucket", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("storage_object_name", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "source_kind",
            sa.String(length=50),
            nullable=True,
            server_default="upload",
        ),
    )
    op.add_column(
        "documents",
        sa.Column("ingestion_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("ingestion_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("ingestion_job_id", sa.String(length=200), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_tender_id",
        "documents",
        "tenders",
        ["tender_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_tender_id",
        "documents",
        ["tender_id"],
    )
    # Remove server_default after column creation (consistent with other migrations)
    op.alter_column(
        "documents",
        "source_kind",
        existing_type=sa.String(length=50),
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_tender_id", table_name="documents")
    op.drop_constraint("fk_documents_tender_id", "documents", type_="foreignkey")
    op.drop_column("documents", "ingestion_job_id")
    op.drop_column("documents", "ingestion_completed_at")
    op.drop_column("documents", "ingestion_started_at")
    op.drop_column("documents", "source_kind")
    op.drop_column("documents", "storage_object_name")
    op.drop_column("documents", "storage_bucket")
    op.drop_column("documents", "tender_id")
