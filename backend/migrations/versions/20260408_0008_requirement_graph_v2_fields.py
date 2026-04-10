"""add requirement graph v2 fields"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260408_0008"
down_revision = "20260408_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consolidated_requirements",
        sa.Column("parent_requirement_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "consolidated_requirements",
        sa.Column("parent_requirement_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "consolidated_requirements",
        sa.Column(
            "applicability",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "consolidated_requirements",
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "consolidated_requirements",
        sa.Column(
            "exceptions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_foreign_key(
        "fk_consolidated_requirements_parent_requirement",
        "consolidated_requirements",
        "consolidated_requirements",
        ["parent_requirement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_consolidated_requirements_parent_requirement_id",
        "consolidated_requirements",
        ["parent_requirement_id"],
    )
    op.create_index(
        "ix_consolidated_requirements_parent_requirement_key",
        "consolidated_requirements",
        ["parent_requirement_key"],
    )
    for column_name, existing_type in (
        ("applicability", postgresql.JSONB(astext_type=sa.Text())),
        ("conditions", postgresql.JSONB(astext_type=sa.Text())),
        ("exceptions", postgresql.JSONB(astext_type=sa.Text())),
    ):
        op.alter_column(
            "consolidated_requirements",
            column_name,
            existing_type=existing_type,
            server_default=None,
        )


def downgrade() -> None:
    op.drop_index(
        "ix_consolidated_requirements_parent_requirement_key",
        table_name="consolidated_requirements",
    )
    op.drop_index(
        "ix_consolidated_requirements_parent_requirement_id",
        table_name="consolidated_requirements",
    )
    op.drop_constraint(
        "fk_consolidated_requirements_parent_requirement",
        "consolidated_requirements",
        type_="foreignkey",
    )
    op.drop_column("consolidated_requirements", "exceptions")
    op.drop_column("consolidated_requirements", "conditions")
    op.drop_column("consolidated_requirements", "applicability")
    op.drop_column("consolidated_requirements", "parent_requirement_key")
    op.drop_column("consolidated_requirements", "parent_requirement_id")
