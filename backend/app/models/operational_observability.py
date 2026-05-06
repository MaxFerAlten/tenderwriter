from __future__ import annotations

import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.db.database import Base


class ContributionUnitStatus(str, enum.Enum):
    OPEN = "open"
    REQUESTED = "requested"
    RECEIVED = "received"
    IN_REVIEW = "in_review"
    REWORK = "rework"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ContributionRequestStatus(str, enum.Enum):
    OPEN = "open"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class ReviewCycleStatus(str, enum.Enum):
    OPEN = "open"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ReworkStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class ComplianceGateStatus(str, enum.Enum):
    OPEN = "open"
    PASSED = "passed"
    FAILED = "failed"


class CallSessionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AttendanceStatus(str, enum.Enum):
    INVITED = "invited"
    ATTENDED = "attended"
    ABSENT = "absent"
    EXCUSED = "excused"


class ContributionUnit(Base):
    __tablename__ = "contribution_units"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(
        Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposal_section_id = Column(
        Integer, ForeignKey("proposal_sections.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    department_name = Column(String(120), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(ContributionUnitStatus), default=ContributionUnitStatus.OPEN, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tender = relationship("Tender")
    proposal_section = relationship("ProposalSection")
    owner_user = relationship("User", foreign_keys=[owner_user_id])
    created_by_user = relationship("User", foreign_keys=[created_by])


class ContributionRequest(Base):
    __tablename__ = "contribution_requests"

    id = Column(Integer, primary_key=True, index=True)
    contribution_unit_id = Column(
        Integer, ForeignKey("contribution_units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_to_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_to_label = Column(String(255), nullable=True)
    request_channel = Column(String(80), nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    due_at = Column(DateTime(timezone=True), nullable=True)
    sla_target_hours = Column(Integer, nullable=True)
    sla_max_hours = Column(Integer, nullable=True)
    response_received_at = Column(DateTime(timezone=True), nullable=True)
    response_summary = Column(Text, nullable=True)
    status = Column(
        Enum(ContributionRequestStatus), default=ContributionRequestStatus.OPEN, index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contribution_unit = relationship("ContributionUnit")
    requested_by_user = relationship("User", foreign_keys=[requested_by])
    requested_to_user = relationship("User", foreign_keys=[requested_to_user_id])


class ReviewCycle(Base):
    __tablename__ = "review_cycles"

    id = Column(Integer, primary_key=True, index=True)
    contribution_unit_id = Column(
        Integer, ForeignKey("contribution_units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stage_name = Column(String(120), nullable=False, default="quality_review")
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    outcome = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(Enum(ReviewCycleStatus), default=ReviewCycleStatus.OPEN, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contribution_unit = relationship("ContributionUnit")
    reviewer = relationship("User", foreign_keys=[reviewer_id])


class ReworkAction(Base):
    __tablename__ = "rework_actions"

    id = Column(Integer, primary_key=True, index=True)
    contribution_unit_id = Column(
        Integer, ForeignKey("contribution_units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_cycle_id = Column(
        Integer, ForeignKey("review_cycles.id", ondelete="SET NULL"), nullable=True
    )
    requested_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_to_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    severity = Column(String(30), nullable=False, default="medium")
    is_blocking = Column(Boolean, nullable=False, default=True)
    reason = Column(Text, nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    status = Column(Enum(ReworkStatus), default=ReworkStatus.OPEN, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contribution_unit = relationship("ContributionUnit")
    review_cycle = relationship("ReviewCycle")
    requested_by_user = relationship("User", foreign_keys=[requested_by])
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id])


class ComplianceGate(Base):
    __tablename__ = "compliance_gates"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(
        Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contribution_unit_id = Column(
        Integer, ForeignKey("contribution_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    gate_name = Column(String(255), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    decision_notes = Column(Text, nullable=True)
    status = Column(Enum(ComplianceGateStatus), default=ComplianceGateStatus.OPEN, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tender = relationship("Tender")
    contribution_unit = relationship("ContributionUnit")
    owner_user = relationship("User", foreign_keys=[owner_user_id])


class CallSession(Base):
    __tablename__ = "call_sessions"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(
        Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(255), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(CallSessionStatus), default=CallSessionStatus.SCHEDULED, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tender = relationship("Tender")
    created_by_user = relationship("User", foreign_keys=[created_by])


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    call_session_id = Column(
        Integer, ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    attendee_label = Column(String(255), nullable=True)
    attendance_status = Column(Enum(AttendanceStatus), default=AttendanceStatus.INVITED, index=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    call_session = relationship("CallSession")
    user = relationship("User", foreign_keys=[user_id])
