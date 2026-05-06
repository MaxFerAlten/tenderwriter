"""SQLAlchemy models for the Wave 3 tender rehearsal layer.

Three tables, one-to-many along ``rehearsal_runs.id``:

- ``rehearsal_runs`` — orchestration row (status, overall score,
  snapshot of context and request parameters, serialized report).
- ``rehearsal_persona_results`` — per-persona score + findings snapshot
  of a completed (or partially completed) run.
- ``rehearsal_recommendations`` — optional suggested reworks extracted
  from persona findings; they carry their own lifecycle
  (``proposed`` / ``accepted`` / ``dismissed``) and can be linked to
  an existing :class:`~app.models.operational_observability.ReworkAction`
  when the operator accepts them.

The intelligence layer must stay observational: nothing here writes
back into the canonical workflow tables.  Accepting a recommendation
(PR-09) creates the linked :class:`ReworkAction` via the existing
operational workflow path — this module only records the link.
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


class RehearsalRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RehearsalMode(str, enum.Enum):
    FULL = "full"
    SECTION = "section"
    PRE_GATE = "pre_gate"


class RehearsalRecommendationStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class RehearsalRun(Base):
    __tablename__ = "rehearsal_runs"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(
        Integer,
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposal_id = Column(
        Integer,
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mode = Column(
        Enum(RehearsalMode, name="rehearsal_mode"),
        nullable=False,
        default=RehearsalMode.FULL,
        index=True,
    )
    status = Column(
        Enum(RehearsalRunStatus, name="rehearsal_run_status"),
        nullable=False,
        default=RehearsalRunStatus.PENDING,
        index=True,
    )

    requested_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    overall_score = Column(Float, nullable=True)
    health_projection = Column(String(20), nullable=True)
    persona_divergence = Column(Float, nullable=True)

    context_snapshot_json = Column(JSONB, nullable=False, default=dict)
    report_json = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    version = Column(String(40), nullable=False, default="tw-rehearsal-v1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tender = relationship("Tender")
    proposal = relationship("Proposal")
    requested_by_user = relationship("User", foreign_keys=[requested_by])
    persona_results = relationship(
        "RehearsalPersonaResult",
        back_populates="rehearsal_run",
        cascade="all, delete-orphan",
    )
    recommendations = relationship(
        "RehearsalRecommendation",
        back_populates="rehearsal_run",
        cascade="all, delete-orphan",
    )


class RehearsalPersonaResult(Base):
    __tablename__ = "rehearsal_persona_results"

    id = Column(Integer, primary_key=True, index=True)
    rehearsal_run_id = Column(
        Integer,
        ForeignKey("rehearsal_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    persona_id = Column(String(80), nullable=False, index=True)
    display_name = Column(String(120), nullable=False)
    reviewer_type = Column(String(80), nullable=False)

    score = Column(Float, nullable=True)
    blocking_findings_count = Column(Integer, nullable=False, default=0)
    high_severity_findings_count = Column(Integer, nullable=False, default=0)

    findings_json = Column(JSONB, nullable=False, default=list)
    questions_json = Column(JSONB, nullable=False, default=list)
    metrics_json = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    rehearsal_run = relationship("RehearsalRun", back_populates="persona_results")


class RehearsalRecommendation(Base):
    __tablename__ = "rehearsal_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    rehearsal_run_id = Column(
        Integer,
        ForeignKey("rehearsal_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scope_type = Column(String(40), nullable=False)
    scope_id = Column(String(80), nullable=False)
    severity = Column(String(20), nullable=False, default="medium")
    is_blocking = Column(Boolean, nullable=False, default=False)

    rationale = Column(Text, nullable=False)
    suggested_owner_role = Column(String(80), nullable=True)
    source_persona_id = Column(String(80), nullable=False)

    status = Column(
        Enum(RehearsalRecommendationStatus, name="rehearsal_recommendation_status"),
        nullable=False,
        default=RehearsalRecommendationStatus.PROPOSED,
        index=True,
    )

    linked_rework_action_id = Column(
        Integer,
        ForeignKey("rework_actions.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    rehearsal_run = relationship("RehearsalRun", back_populates="recommendations")
    linked_rework_action = relationship("ReworkAction")


__all__ = [
    "RehearsalMode",
    "RehearsalPersonaResult",
    "RehearsalRecommendation",
    "RehearsalRecommendationStatus",
    "RehearsalRun",
    "RehearsalRunStatus",
]
