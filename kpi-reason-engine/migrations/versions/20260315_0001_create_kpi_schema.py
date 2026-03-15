"""create kpi schema

Revision ID: 20260315_0001
Revises:
Create Date: 2026-03-15 10:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20260315_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if 'kpi_tenders' not in existing:
        op.create_table(
            'kpi_tenders',
            sa.Column('external_tender_id', sa.Text(), primary_key=True),
            sa.Column('title', sa.Text(), nullable=False),
            sa.Column('customer_name', sa.Text(), nullable=True),
            sa.Column('due_at', sa.Text(), nullable=True),
            sa.Column('current_status', sa.Text(), nullable=True),
            sa.Column('departments_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('requirement_contexts_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('section_contexts_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('health', sa.Text(), nullable=False, server_default='unknown'),
            sa.Column('analytical_phase', sa.Text(), nullable=True),
            sa.Column('created_at', sa.Text(), nullable=False),
            sa.Column('updated_at', sa.Text(), nullable=False),
            sa.Column('last_synced_at', sa.Text(), nullable=False),
        )

    if 'kpi_domain_events' not in existing:
        op.create_table(
            'kpi_domain_events',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('external_tender_id', sa.Text(), nullable=False),
            sa.Column('event_type', sa.Text(), nullable=False),
            sa.Column('occurred_at', sa.Text(), nullable=False),
            sa.Column('actor_id', sa.Text(), nullable=True),
            sa.Column('source', sa.Text(), nullable=False),
            sa.Column('schema_version', sa.Text(), nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=False),
            sa.Column('envelope_hash', sa.Text(), nullable=False),
            sa.Column('created_at', sa.Text(), nullable=False),
            sa.UniqueConstraint('external_tender_id', 'event_type', 'occurred_at', 'source', 'envelope_hash', name='uq_kpi_domain_events_envelope'),
        )

    if 'kpi_document_contexts' not in existing:
        op.create_table(
            'kpi_document_contexts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('external_tender_id', sa.Text(), nullable=False),
            sa.Column('document_id', sa.Text(), nullable=False),
            sa.Column('document_type', sa.Text(), nullable=False),
            sa.Column('filename', sa.Text(), nullable=True),
            sa.Column('extracted_text_ref', sa.Text(), nullable=True),
            sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.Text(), nullable=False),
        )

    if 'kpi_analysis_jobs' not in existing:
        op.create_table(
            'kpi_analysis_jobs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('external_tender_id', sa.Text(), nullable=False),
            sa.Column('job_type', sa.Text(), nullable=False),
            sa.Column('requested_by', sa.Text(), nullable=True),
            sa.Column('priority', sa.Text(), nullable=False),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('status', sa.Text(), nullable=False),
            sa.Column('created_at', sa.Text(), nullable=False),
        )

    if 'kpi_model_versions' not in existing:
        op.create_table(
            'kpi_model_versions',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('version_type', sa.Text(), nullable=False),
            sa.Column('version_code', sa.Text(), nullable=False),
            sa.Column('descriptor_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.Text(), nullable=False),
            sa.UniqueConstraint('version_type', 'version_code', name='uq_kpi_model_versions_type_code'),
        )

    if 'kpi_snapshots' not in existing:
        op.create_table(
            'kpi_snapshots',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('external_tender_id', sa.Text(), nullable=False),
            sa.Column('snapshot_hash', sa.Text(), nullable=False),
            sa.Column('analytical_phase', sa.Text(), nullable=True),
            sa.Column('health', sa.Text(), nullable=False),
            sa.Column('summary', sa.Text(), nullable=False),
            sa.Column('kpis_json', sa.Text(), nullable=False),
            sa.Column('notes_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('model_version_id', sa.Integer(), sa.ForeignKey('kpi_model_versions.id', ondelete='SET NULL'), nullable=True),
            sa.Column('generated_at', sa.Text(), nullable=False),
            sa.Column('created_at', sa.Text(), nullable=False),
            sa.UniqueConstraint('external_tender_id', 'snapshot_hash', name='uq_kpi_snapshots_hash'),
        )

    if 'kpi_findings' not in existing:
        op.create_table(
            'kpi_findings',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('snapshot_id', sa.Integer(), sa.ForeignKey('kpi_snapshots.id', ondelete='CASCADE'), nullable=False),
            sa.Column('finding_kind', sa.Text(), nullable=False),
            sa.Column('finding_key', sa.Text(), nullable=True),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('created_at', sa.Text(), nullable=False),
        )

    if 'kpi_phase_transitions' not in existing:
        op.create_table(
            'kpi_phase_transitions',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('external_tender_id', sa.Text(), nullable=False),
            sa.Column('snapshot_id', sa.Integer(), sa.ForeignKey('kpi_snapshots.id', ondelete='SET NULL'), nullable=True),
            sa.Column('from_state', sa.Text(), nullable=False),
            sa.Column('to_state', sa.Text(), nullable=False),
            sa.Column('occurred_at', sa.Text(), nullable=True),
            sa.Column('cause', sa.Text(), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('source_event_type', sa.Text(), nullable=True),
            sa.Column('related_entity_id', sa.Text(), nullable=True),
            sa.Column('transition_hash', sa.Text(), nullable=False),
            sa.Column('created_at', sa.Text(), nullable=False),
            sa.UniqueConstraint('external_tender_id', 'transition_hash', name='uq_kpi_phase_transitions_hash'),
        )


def downgrade() -> None:
    op.drop_table('kpi_phase_transitions')
    op.drop_table('kpi_findings')
    op.drop_table('kpi_snapshots')
    op.drop_table('kpi_model_versions')
    op.drop_table('kpi_analysis_jobs')
    op.drop_table('kpi_document_contexts')
    op.drop_table('kpi_domain_events')
    op.drop_table('kpi_tenders')
