"""requirement relation foundation"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260404_0005"
down_revision = "20260404_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requirement_relations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "source_requirement_id",
            sa.Integer(),
            sa.ForeignKey("consolidated_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_requirement_id",
            sa.Integer(),
            sa.ForeignKey("consolidated_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source_requirement_id <> target_requirement_id",
            name="ck_requirement_relations_not_self",
        ),
        sa.UniqueConstraint(
            "tender_id",
            "source_requirement_id",
            "target_requirement_id",
            "relation_type",
            name="uq_requirement_relations_edge",
        ),
    )
    op.create_index("ix_requirement_relations_tender_id", "requirement_relations", ["tender_id"])
    op.create_index(
        "ix_requirement_relations_source_requirement_id",
        "requirement_relations",
        ["source_requirement_id"],
    )
    op.create_index(
        "ix_requirement_relations_target_requirement_id",
        "requirement_relations",
        ["target_requirement_id"],
    )
    op.create_index(
        "ix_requirement_relations_relation_type",
        "requirement_relations",
        ["relation_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_requirement_relations_relation_type", table_name="requirement_relations")
    op.drop_index(
        "ix_requirement_relations_target_requirement_id",
        table_name="requirement_relations",
    )
    op.drop_index(
        "ix_requirement_relations_source_requirement_id",
        table_name="requirement_relations",
    )
    op.drop_index("ix_requirement_relations_tender_id", table_name="requirement_relations")
    op.drop_table("requirement_relations")
