"""requirement relation review foundation"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260404_0006"
down_revision = "20260404_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "requirement_relations",
        sa.Column(
            "review_state",
            sa.String(length=50),
            nullable=True,
            server_default=sa.text("'pending'"),
        ),
    )
    op.execute(
        "UPDATE requirement_relations SET review_state = 'pending' WHERE review_state IS NULL"
    )
    op.alter_column(
        "requirement_relations",
        "review_state",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=None,
    )
    op.create_index(
        "ix_requirement_relations_review_state",
        "requirement_relations",
        ["review_state"],
    )

    op.create_table(
        "requirement_relation_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tender_id",
            sa.Integer(),
            sa.ForeignKey("tenders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requirement_relation_id",
            sa.Integer(),
            sa.ForeignKey("requirement_relations.id", ondelete="CASCADE"),
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
    op.create_index(
        "ix_requirement_relation_reviews_tender_id",
        "requirement_relation_reviews",
        ["tender_id"],
    )
    op.create_index(
        "ix_requirement_relation_reviews_requirement_relation_id",
        "requirement_relation_reviews",
        ["requirement_relation_id"],
    )
    op.create_index(
        "ix_requirement_relation_reviews_actor_id",
        "requirement_relation_reviews",
        ["actor_id"],
    )
    op.create_index(
        "ix_requirement_relation_reviews_action",
        "requirement_relation_reviews",
        ["action"],
    )
    op.create_index(
        "ix_requirement_relation_reviews_new_review_state",
        "requirement_relation_reviews",
        ["new_review_state"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_relation_reviews_new_review_state",
        table_name="requirement_relation_reviews",
    )
    op.drop_index(
        "ix_requirement_relation_reviews_action",
        table_name="requirement_relation_reviews",
    )
    op.drop_index(
        "ix_requirement_relation_reviews_actor_id",
        table_name="requirement_relation_reviews",
    )
    op.drop_index(
        "ix_requirement_relation_reviews_requirement_relation_id",
        table_name="requirement_relation_reviews",
    )
    op.drop_index(
        "ix_requirement_relation_reviews_tender_id",
        table_name="requirement_relation_reviews",
    )
    op.drop_table("requirement_relation_reviews")
    op.drop_index(
        "ix_requirement_relations_review_state",
        table_name="requirement_relations",
    )
    op.drop_column("requirement_relations", "review_state")
