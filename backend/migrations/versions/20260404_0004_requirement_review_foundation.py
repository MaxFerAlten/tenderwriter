"""requirement review foundation"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260404_0004"
down_revision = "20260404_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requirement_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tender_id",
            sa.Integer(),
            sa.ForeignKey("tenders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consolidated_requirement_id",
            sa.Integer(),
            sa.ForeignKey("consolidated_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("previous_review_state", sa.String(length=50), nullable=True),
        sa.Column("new_review_state", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_requirement_reviews_tender_id", "requirement_reviews", ["tender_id"])
    op.create_index(
        "ix_requirement_reviews_consolidated_requirement_id",
        "requirement_reviews",
        ["consolidated_requirement_id"],
    )
    op.create_index("ix_requirement_reviews_actor_id", "requirement_reviews", ["actor_id"])
    op.create_index("ix_requirement_reviews_action", "requirement_reviews", ["action"])
    op.create_index(
        "ix_requirement_reviews_new_review_state",
        "requirement_reviews",
        ["new_review_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_requirement_reviews_new_review_state", table_name="requirement_reviews")
    op.drop_index("ix_requirement_reviews_action", table_name="requirement_reviews")
    op.drop_index("ix_requirement_reviews_actor_id", table_name="requirement_reviews")
    op.drop_index(
        "ix_requirement_reviews_consolidated_requirement_id",
        table_name="requirement_reviews",
    )
    op.drop_index("ix_requirement_reviews_tender_id", table_name="requirement_reviews")
    op.drop_table("requirement_reviews")
