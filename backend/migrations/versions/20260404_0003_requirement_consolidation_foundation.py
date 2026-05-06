"""requirement consolidation foundation"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260404_0003"
down_revision = "20260404_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consolidated_requirements",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tender_id",
            sa.Integer(),
            sa.ForeignKey("tenders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True, server_default="medium"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=True, server_default="1"),
        sa.Column(
            "consolidation_method",
            sa.String(length=100),
            nullable=True,
            server_default="staging_v1",
        ),
        sa.Column("review_state", sa.String(length=50), nullable=True, server_default="pending"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tender_id",
            "normalized_text",
            name="uq_consolidated_requirements_tender_normalized",
        ),
    )
    op.create_index(
        "ix_consolidated_requirements_tender_id",
        "consolidated_requirements",
        ["tender_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_consolidated_requirements_tender_id", table_name="consolidated_requirements")
    op.drop_table("consolidated_requirements")
