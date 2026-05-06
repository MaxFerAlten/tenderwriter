"""add rehearsal_runs, rehearsal_persona_results, rehearsal_recommendations

Wave-3 scaffolding for the tender rehearsal layer.  Adds three
read-mostly tables plus the associated Postgres enums.

- ``rehearsal_runs`` records the orchestration row (status, context
  snapshot, serialized report, error message).
- ``rehearsal_persona_results`` holds per-persona score, findings and
  questions for a completed run.
- ``rehearsal_recommendations`` tracks suggested reworks derived from
  persona findings; they can be accepted (linked to a canonical
  ``rework_actions`` row via ``linked_rework_action_id``) or dismissed.

The tables are intentionally independent from the canonical workflow
(``review_cycles`` / ``rework_actions`` / ``compliance_gates``).  The
rehearsal layer remains observational: accepting a recommendation in
PR-09 creates the ``ReworkAction`` via the existing operational
workflow path, after which this migration's FK surfaces the link.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260419_0012"
down_revision = "20260419_0011"
branch_labels = None
depends_on = None


_RUN_STATUS_ENUM = "rehearsal_run_status"
_MODE_ENUM = "rehearsal_mode"
_RECOMMENDATION_STATUS_ENUM = "rehearsal_recommendation_status"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    run_status_enum = postgresql.ENUM(
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
        name=_RUN_STATUS_ENUM,
        create_type=False,
    )
    mode_enum = postgresql.ENUM(
        "full",
        "section",
        "pre_gate",
        name=_MODE_ENUM,
        create_type=False,
    )
    recommendation_status_enum = postgresql.ENUM(
        "proposed",
        "accepted",
        "dismissed",
        name=_RECOMMENDATION_STATUS_ENUM,
        create_type=False,
    )
    run_status_enum.create(bind, checkfirst=True)
    mode_enum.create(bind, checkfirst=True)
    recommendation_status_enum.create(bind, checkfirst=True)

    if "rehearsal_runs" not in existing_tables:
        op.create_table(
            "rehearsal_runs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "tender_id",
                sa.Integer(),
                sa.ForeignKey("tenders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "proposal_id",
                sa.Integer(),
                sa.ForeignKey("proposals.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("mode", mode_enum, nullable=False, server_default="full"),
            sa.Column("status", run_status_enum, nullable=False, server_default="pending"),
            sa.Column(
                "requested_by",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("overall_score", sa.Float(), nullable=True),
            sa.Column("health_projection", sa.String(length=20), nullable=True),
            sa.Column("persona_divergence", sa.Float(), nullable=True),
            sa.Column(
                "context_snapshot_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "report_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "version",
                sa.String(length=40),
                nullable=False,
                server_default="tw-rehearsal-v1",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_rehearsal_runs_tender_id",
            "rehearsal_runs",
            ["tender_id"],
        )
        op.create_index(
            "ix_rehearsal_runs_proposal_id",
            "rehearsal_runs",
            ["proposal_id"],
        )
        op.create_index(
            "ix_rehearsal_runs_mode",
            "rehearsal_runs",
            ["mode"],
        )
        op.create_index(
            "ix_rehearsal_runs_status",
            "rehearsal_runs",
            ["status"],
        )
        op.create_index(
            "ix_rehearsal_runs_tender_created_at",
            "rehearsal_runs",
            ["tender_id", sa.text("created_at DESC")],
        )
        op.create_index(
            "ix_rehearsal_runs_proposal_created_at",
            "rehearsal_runs",
            ["proposal_id", sa.text("created_at DESC")],
        )

    if "rehearsal_persona_results" not in existing_tables:
        op.create_table(
            "rehearsal_persona_results",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "rehearsal_run_id",
                sa.Integer(),
                sa.ForeignKey("rehearsal_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("persona_id", sa.String(length=80), nullable=False),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("reviewer_type", sa.String(length=80), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column(
                "blocking_findings_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "high_severity_findings_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "findings_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "questions_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "metrics_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_rehearsal_persona_results_run_id",
            "rehearsal_persona_results",
            ["rehearsal_run_id"],
        )
        op.create_index(
            "ix_rehearsal_persona_results_persona_id",
            "rehearsal_persona_results",
            ["persona_id"],
        )
        op.create_index(
            "ix_rehearsal_persona_results_run_persona",
            "rehearsal_persona_results",
            ["rehearsal_run_id", "persona_id"],
        )

    if "rehearsal_recommendations" not in existing_tables:
        op.create_table(
            "rehearsal_recommendations",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "rehearsal_run_id",
                sa.Integer(),
                sa.ForeignKey("rehearsal_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("scope_type", sa.String(length=40), nullable=False),
            sa.Column("scope_id", sa.String(length=80), nullable=False),
            sa.Column(
                "severity",
                sa.String(length=20),
                nullable=False,
                server_default="medium",
            ),
            sa.Column(
                "is_blocking",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("suggested_owner_role", sa.String(length=80), nullable=True),
            sa.Column("source_persona_id", sa.String(length=80), nullable=False),
            sa.Column(
                "status",
                recommendation_status_enum,
                nullable=False,
                server_default="proposed",
            ),
            sa.Column(
                "linked_rework_action_id",
                sa.Integer(),
                sa.ForeignKey("rework_actions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_rehearsal_recommendations_run_id",
            "rehearsal_recommendations",
            ["rehearsal_run_id"],
        )
        op.create_index(
            "ix_rehearsal_recommendations_status",
            "rehearsal_recommendations",
            ["status"],
        )
        op.create_index(
            "ix_rehearsal_recommendations_run_status",
            "rehearsal_recommendations",
            ["rehearsal_run_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "rehearsal_recommendations" in existing_tables:
        op.drop_index(
            "ix_rehearsal_recommendations_run_status",
            table_name="rehearsal_recommendations",
        )
        op.drop_index(
            "ix_rehearsal_recommendations_status",
            table_name="rehearsal_recommendations",
        )
        op.drop_index(
            "ix_rehearsal_recommendations_run_id",
            table_name="rehearsal_recommendations",
        )
        op.drop_table("rehearsal_recommendations")

    if "rehearsal_persona_results" in existing_tables:
        op.drop_index(
            "ix_rehearsal_persona_results_run_persona",
            table_name="rehearsal_persona_results",
        )
        op.drop_index(
            "ix_rehearsal_persona_results_persona_id",
            table_name="rehearsal_persona_results",
        )
        op.drop_index(
            "ix_rehearsal_persona_results_run_id",
            table_name="rehearsal_persona_results",
        )
        op.drop_table("rehearsal_persona_results")

    if "rehearsal_runs" in existing_tables:
        op.drop_index(
            "ix_rehearsal_runs_proposal_created_at",
            table_name="rehearsal_runs",
        )
        op.drop_index(
            "ix_rehearsal_runs_tender_created_at",
            table_name="rehearsal_runs",
        )
        op.drop_index("ix_rehearsal_runs_status", table_name="rehearsal_runs")
        op.drop_index("ix_rehearsal_runs_mode", table_name="rehearsal_runs")
        op.drop_index("ix_rehearsal_runs_proposal_id", table_name="rehearsal_runs")
        op.drop_index("ix_rehearsal_runs_tender_id", table_name="rehearsal_runs")
        op.drop_table("rehearsal_runs")

    for enum_name in (
        _RECOMMENDATION_STATUS_ENUM,
        _MODE_ENUM,
        _RUN_STATUS_ENUM,
    ):
        bind.execute(sa.text(f'DROP TYPE IF EXISTS "{enum_name}"'))
