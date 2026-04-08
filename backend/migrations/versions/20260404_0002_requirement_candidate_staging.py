"""requirement candidate staging"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260404_0002"
down_revision = "20260403_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requirement_extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_document_ref", sa.String(length=1000), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column("extraction_method", sa.String(length=100), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_requirement_extraction_runs_tender_id",
        "requirement_extraction_runs",
        ["tender_id"],
    )
    op.create_index(
        "ix_requirement_extraction_runs_actor_id",
        "requirement_extraction_runs",
        ["actor_id"],
    )

    op.create_table(
        "requirement_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "extraction_run_id",
            sa.Integer(),
            sa.ForeignKey("requirement_extraction_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("candidate_position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_document_ref", sa.String(length=1000), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True, server_default="medium"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_requirement_candidates_tender_id",
        "requirement_candidates",
        ["tender_id"],
    )
    op.create_index(
        "ix_requirement_candidates_extraction_run_id",
        "requirement_candidates",
        ["extraction_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_requirement_candidates_extraction_run_id", table_name="requirement_candidates")
    op.drop_index("ix_requirement_candidates_tender_id", table_name="requirement_candidates")
    op.drop_table("requirement_candidates")
    op.drop_index("ix_requirement_extraction_runs_actor_id", table_name="requirement_extraction_runs")
    op.drop_index("ix_requirement_extraction_runs_tender_id", table_name="requirement_extraction_runs")
    op.drop_table("requirement_extraction_runs")
