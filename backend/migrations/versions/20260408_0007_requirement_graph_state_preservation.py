"""preserve requirement graph state across rebuilds"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0007"
down_revision = "20260404_0006"
branch_labels = None
depends_on = None


def _add_state_column(table_name: str, index_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column(
            "graph_state",
            sa.String(length=50),
            nullable=True,
            server_default=sa.text("'active'"),
        ),
    )
    op.execute(f"UPDATE {table_name} SET graph_state = 'active' WHERE graph_state IS NULL")
    op.alter_column(
        table_name,
        "graph_state",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=None,
    )
    op.create_index(index_name, table_name, ["graph_state"])


def upgrade() -> None:
    _add_state_column(
        "consolidated_requirements",
        "ix_consolidated_requirements_graph_state",
    )
    _add_state_column(
        "requirement_relations",
        "ix_requirement_relations_graph_state",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_relations_graph_state",
        table_name="requirement_relations",
    )
    op.drop_column("requirement_relations", "graph_state")
    op.drop_index(
        "ix_consolidated_requirements_graph_state",
        table_name="consolidated_requirements",
    )
    op.drop_column("consolidated_requirements", "graph_state")
