"""add analysis job lifecycle columns

Revision ID: 20260315_0002
Revises: 20260315_0001
Create Date: 2026-03-15 11:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20260315_0002'
down_revision = '20260315_0001'
branch_labels = None
depends_on = None


def _schema_name() -> str | None:
    normalized = str(op.get_context().config.get_main_option('kpi.schema') or '').strip()
    return normalized or None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema_name = _schema_name()
    columns = {column['name'] for column in inspector.get_columns('kpi_analysis_jobs', schema=schema_name)}

    with op.batch_alter_table('kpi_analysis_jobs', schema=schema_name) as batch_op:
        if 'started_at' not in columns:
            batch_op.add_column(sa.Column('started_at', sa.Text(), nullable=True))
        if 'completed_at' not in columns:
            batch_op.add_column(sa.Column('completed_at', sa.Text(), nullable=True))
        if 'updated_at' not in columns:
            batch_op.add_column(sa.Column('updated_at', sa.Text(), nullable=True))
        if 'error_message' not in columns:
            batch_op.add_column(sa.Column('error_message', sa.Text(), nullable=True))
        if 'result_snapshot_id' not in columns:
            batch_op.add_column(sa.Column('result_snapshot_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema_name = _schema_name()
    columns = {column['name'] for column in inspector.get_columns('kpi_analysis_jobs', schema=schema_name)}

    with op.batch_alter_table('kpi_analysis_jobs', schema=schema_name) as batch_op:
        if 'result_snapshot_id' in columns:
            batch_op.drop_column('result_snapshot_id')
        if 'error_message' in columns:
            batch_op.drop_column('error_message')
        if 'updated_at' in columns:
            batch_op.drop_column('updated_at')
        if 'completed_at' in columns:
            batch_op.drop_column('completed_at')
        if 'started_at' in columns:
            batch_op.drop_column('started_at')
