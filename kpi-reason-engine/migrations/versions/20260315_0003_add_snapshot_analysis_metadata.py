"""add analysis metadata to snapshots

Revision ID: 20260315_0003
Revises: 20260315_0002
Create Date: 2026-03-15 18:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20260315_0003'
down_revision = '20260315_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('kpi_snapshots')}

    with op.batch_alter_table('kpi_snapshots') as batch_op:
        if 'analysis_metadata_json' not in columns:
            batch_op.add_column(sa.Column('analysis_metadata_json', sa.Text(), nullable=False, server_default='{}'))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('kpi_snapshots')}

    with op.batch_alter_table('kpi_snapshots') as batch_op:
        if 'analysis_metadata_json' in columns:
            batch_op.drop_column('analysis_metadata_json')
