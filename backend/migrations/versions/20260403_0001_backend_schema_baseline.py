"""backend schema baseline"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260403_0001'
down_revision = None
branch_labels = None
depends_on = None

BASELINE_TABLES = (
    'ai_gateway_targets',
    'app_settings',
    'llm_settings',
    'users',
    'content_blocks',
    'documents',
    'otp_tokens',
    'search_history',
    'tenders',
    'anonymizer_audit_logs',
    'call_sessions',
    'chat_rooms',
    'chunks',
    'kpi_admin_audit_logs',
    'kpi_domain_events',
    'proposals',
    'tender_permissions',
    'attendance_records',
    'chat_events',
    'chat_members',
    'chat_messages',
    'proposal_sections',
    'chat_attachments',
    'contribution_units',
    'tender_requirements',
    'compliance_gates',
    'contribution_requests',
    'review_cycles',
    'rework_actions',
)

metadata = sa.MetaData()

sa.Table('ai_gateway_targets', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('route_key', sa.String(length=50), nullable=False),
    sa.Column('target_kind', sa.String(length=50), nullable=False),
    sa.Column('connection_method', sa.String(length=50), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=False),
    sa.Column('model_name', sa.String(length=200), nullable=True),
    sa.Column('api_key', sa.Text(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=True),
    sa.Column('timeout_ms', sa.Integer(), nullable=True),
    sa.Column('use_anonymizer', sa.Boolean(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('app_settings', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('llm_settings', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('max_tokens', sa.Integer(), nullable=True),
    sa.Column('temperature', sa.Float(), nullable=True),
    sa.Column('stop_tokens', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('users', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('email', sa.String(length=255), nullable=False, index=True, unique=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_verified', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('content_blocks', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('title', sa.String(length=500), nullable=False, index=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True, index=True),
    sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True),
    sa.Column('usage_count', sa.Integer(), nullable=True),
    sa.Column('quality_rating', sa.Float(), nullable=True),
    sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('documents', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('filename', sa.String(length=500), nullable=False),
    sa.Column('file_url', sa.String(length=1000), nullable=False),
    sa.Column('doc_type', sa.String(length=50), nullable=True, index=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('mime_type', sa.String(length=100), nullable=True),
    sa.Column('ingestion_status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='ingestionstatus'), nullable=True, index=True),
    sa.Column('chunk_count', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('otp_tokens', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    sa.Column('token', sa.String(length=10), nullable=False, index=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=True),
    sa.Column('max_attempts', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
)

sa.Table('search_history', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('response', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
)

sa.Table('tenders', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('title', sa.String(length=500), nullable=False, index=True),
    sa.Column('client', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('DRAFT', 'ACTIVE', 'IN_PROGRESS', 'SUBMITTED', 'WON', 'LOST', 'CANCELLED', name='tenderstatus'), nullable=True, index=True),
    sa.Column('source_file_url', sa.String(length=1000), nullable=True),
    sa.Column('budget_estimate', sa.Float(), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True, index=True),
    sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('anonymizer_audit_logs', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('action', sa.String(length=100), nullable=False, index=True),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
    sa.Column('user_email', sa.String(length=255), nullable=False),
    sa.Column('user_role', sa.String(length=50), nullable=False),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='SET NULL'), nullable=True, index=True),
    sa.Column('route_key', sa.String(length=50), nullable=True, index=True),
    sa.Column('llm_route', sa.String(length=50), nullable=True, index=True),
    sa.Column('anonymized', sa.Boolean(), nullable=True),
    sa.Column('target_id', sa.Integer(), sa.ForeignKey('ai_gateway_targets.id', ondelete='SET NULL'), nullable=True, index=True),
    sa.Column('target_provider', sa.String(length=50), nullable=True),
    sa.Column('target_base_url', sa.String(length=500), nullable=True),
    sa.Column('session_token', sa.String(length=64), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=False, index=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, index=True, server_default=sa.text("now()")),
)

sa.Table('call_sessions', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('SCHEDULED', 'COMPLETED', 'CANCELLED', name='callsessionstatus'), nullable=True, index=True),
    sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('chat_rooms', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False),
    sa.Column('is_official', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Enum('PROVISIONED', 'OPEN', 'ARCHIVED', name='chatroomstatus'), nullable=True, index=True),
    sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint('tender_id', name='uq_chat_rooms_tender_id'),
)

sa.Table('chunks', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('section_title', sa.String(length=500), nullable=True),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('qdrant_point_id', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
)

sa.Table('kpi_admin_audit_logs', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('action', sa.String(length=100), nullable=False, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='SET NULL'), nullable=True, index=True),
    sa.Column('admin_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
    sa.Column('admin_user_email', sa.String(length=255), nullable=False),
    sa.Column('admin_user_role', sa.String(length=50), nullable=False),
    sa.Column('delivered', sa.Boolean(), nullable=True),
    sa.Column('degraded', sa.Boolean(), nullable=False),
    sa.Column('upstream_status_code', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, index=True, server_default=sa.text("now()")),
)

sa.Table('kpi_domain_events', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('event_type', sa.String(length=100), nullable=False, index=True),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('external_tender_id', sa.String(length=100), nullable=False, index=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('delivery_status', sa.Enum('PENDING', 'DELIVERED', 'FAILED', name='kpieventdeliverystatus'), nullable=True, index=True),
    sa.Column('delivery_attempts', sa.Integer(), nullable=True),
    sa.Column('response_status_code', sa.Integer(), nullable=True),
    sa.Column('response_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('proposals', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('status', sa.Enum('DRAFT', 'IN_REVIEW', 'APPROVED', 'SUBMITTED', name='proposalstatus'), nullable=True, index=True),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('tender_permissions', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    sa.Column('permission', sa.String(length=50), nullable=True),
    sa.Column('granted_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
)

sa.Table('attendance_records', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('call_session_id', sa.Integer(), sa.ForeignKey('call_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('attendee_label', sa.String(length=255), nullable=True),
    sa.Column('attendance_status', sa.Enum('INVITED', 'ATTENDED', 'ABSENT', 'EXCUSED', name='attendancestatus'), nullable=True, index=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('chat_events', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('chat_room_id', sa.Integer(), sa.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('event_type', sa.String(length=100), nullable=False, index=True),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, index=True, server_default=sa.text("now()")),
)

sa.Table('chat_members', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('chat_room_id', sa.Integer(), sa.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=True),
    sa.Column('source', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint('chat_room_id', 'user_id', name='uq_chat_members_room_user'),
)

sa.Table('chat_messages', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('chat_room_id', sa.Integer(), sa.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('sender_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('message_type', sa.Enum('TEXT', 'SYSTEM', name='chatmessagetype'), nullable=True, index=True),
    sa.Column('text_bucket', sa.String(length=255), nullable=True),
    sa.Column('text_object_key', sa.String(length=1000), nullable=True),
    sa.Column('text_preview', sa.Text(), nullable=True),
    sa.Column('text_sha256', sa.String(length=64), nullable=True),
    sa.Column('text_size', sa.Integer(), nullable=True),
    sa.Column('reply_to_message_id', sa.Integer(), sa.ForeignKey('chat_messages.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, index=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('proposal_sections', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('proposal_id', sa.Integer(), sa.ForeignKey('proposals.id', ondelete='CASCADE'), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('order', sa.Integer(), nullable=True),
    sa.Column('assigned_to', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('status', sa.Enum('TODO', 'IN_PROGRESS', 'IN_REVIEW', 'APPROVED', name='sectionstatus'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('chat_attachments', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('message_id', sa.Integer(), sa.ForeignKey('chat_messages.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('bucket', sa.String(length=255), nullable=False),
    sa.Column('object_key', sa.String(length=1000), nullable=False),
    sa.Column('filename', sa.String(length=500), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=True),
    sa.Column('size_bytes', sa.Integer(), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
)

sa.Table('contribution_units', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('proposal_section_id', sa.Integer(), sa.ForeignKey('proposal_sections.id', ondelete='SET NULL'), nullable=True),
    sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('department_name', sa.String(length=120), nullable=True, index=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'REQUESTED', 'RECEIVED', 'IN_REVIEW', 'REWORK', 'COMPLETED', 'BLOCKED', name='contributionunitstatus'), nullable=True, index=True),
    sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('tender_requirements', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False),
    sa.Column('requirement_text', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('priority', sa.String(length=20), nullable=True),
    sa.Column('compliance_status', sa.Enum('NOT_ADDRESSED', 'PARTIALLY_ADDRESSED', 'FULLY_ADDRESSED', name='compliancestatus'), nullable=True),
    sa.Column('proposal_section_id', sa.Integer(), sa.ForeignKey('proposal_sections.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
)

sa.Table('compliance_gates', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tenders.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('contribution_unit_id', sa.Integer(), sa.ForeignKey('contribution_units.id', ondelete='SET NULL'), nullable=True, index=True),
    sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('gate_name', sa.String(length=255), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_notes', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'PASSED', 'FAILED', name='compliancegatestatus'), nullable=True, index=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('contribution_requests', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('contribution_unit_id', sa.Integer(), sa.ForeignKey('contribution_units.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('requested_to_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('requested_to_label', sa.String(length=255), nullable=True),
    sa.Column('request_channel', sa.String(length=80), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sla_target_hours', sa.Integer(), nullable=True),
    sa.Column('sla_max_hours', sa.Integer(), nullable=True),
    sa.Column('response_received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('response_summary', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'RECEIVED', 'CANCELLED', name='contributionrequeststatus'), nullable=True, index=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('review_cycles', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('contribution_unit_id', sa.Integer(), sa.ForeignKey('contribution_units.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('reviewer_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('stage_name', sa.String(length=120), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome', sa.String(length=80), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'COMPLETED', 'BLOCKED', name='reviewcyclestatus'), nullable=True, index=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

sa.Table('rework_actions', metadata,
    sa.Column('id', sa.Integer(), nullable=False, primary_key=True, index=True),
    sa.Column('contribution_unit_id', sa.Integer(), sa.ForeignKey('contribution_units.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('review_cycle_id', sa.Integer(), sa.ForeignKey('review_cycles.id', ondelete='SET NULL'), nullable=True),
    sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('assigned_to_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    sa.Column('severity', sa.String(length=30), nullable=False),
    sa.Column('is_blocking', sa.Boolean(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolution_notes', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'RESOLVED', name='reworkstatus'), nullable=True, index=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
)

COMPATIBILITY_COLUMNS = {
    "users": {
        "is_active": sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        "is_verified": sa.Column("is_verified", sa.Boolean(), nullable=True, server_default=sa.text("false")),
    },
    "ai_gateway_targets": {
        "connection_method": sa.Column("connection_method", sa.String(length=50), nullable=True, server_default=sa.text("'llama_cpp'")),
        "api_key": sa.Column("api_key", sa.Text(), nullable=True),
    },
}

def _existing_columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    try:
        return {column["name"] for column in inspector.get_columns(table_name)}
    except sa.exc.NoSuchTableError:
        return set()

def _ensure_compatibility_columns() -> None:
    bind = op.get_bind()
    for table_name, columns in COMPATIBILITY_COLUMNS.items():
        existing_columns = _existing_columns(bind, table_name)
        for column_name, column in columns.items():
            if column_name not in existing_columns:
                op.add_column(table_name, column.copy())

def upgrade() -> None:
    bind = op.get_bind()
    metadata.create_all(bind=bind, checkfirst=True)
    _ensure_compatibility_columns()

def downgrade() -> None:
    bind = op.get_bind()
    metadata.drop_all(bind=bind, checkfirst=True)