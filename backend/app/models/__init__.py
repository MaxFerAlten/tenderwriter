"""
TenderWriter — SQLAlchemy Models for Tenders, Proposals, Content, and Documents
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class TenderStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"


class ProposalStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    SUBMITTED = "submitted"


class SectionStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    APPROVED = "approved"


class ComplianceStatus(str, enum.Enum):
    NOT_ADDRESSED = "not_addressed"
    PARTIALLY_ADDRESSED = "partially_addressed"
    FULLY_ADDRESSED = "fully_addressed"


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatRoomStatus(str, enum.Enum):
    PROVISIONED = "provisioned"
    OPEN = "open"
    ARCHIVED = "archived"


class ChatMessageType(str, enum.Enum):
    TEXT = "text"
    SYSTEM = "system"


class KpiEventDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"

# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="editor")
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    tenders = relationship("Tender", back_populates="created_by_user")
    proposals = relationship("Proposal", back_populates="created_by_user")
    otp_tokens = relationship("OTPToken", back_populates="user", cascade="all, delete")
    search_history = relationship(
        "SearchHistory",
        back_populates="user",
        cascade="all, delete",
        order_by="desc(SearchHistory.created_at)",
    )
    tender_permissions = relationship(
        "TenderPermission",
        back_populates="user",
        foreign_keys="TenderPermission.user_id",
        cascade="all, delete",
    )
    chat_memberships = relationship("ChatMember", back_populates="user", cascade="all, delete")
    chat_messages_sent = relationship(
        "ChatMessage",
        back_populates="sender",
        foreign_keys="ChatMessage.sender_id",
    )
    chat_events = relationship(
        "ChatEvent",
        back_populates="actor",
        foreign_keys="ChatEvent.actor_id",
    )


class OTPToken(Base):
    __tablename__ = "otp_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(10), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="otp_tokens")


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="search_history")


class Tender(Base):
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    client = Column(String(255))
    description = Column(Text)
    deadline = Column(DateTime(timezone=True))
    status = Column(Enum(TenderStatus), default=TenderStatus.DRAFT, index=True)
    source_file_url = Column(String(1000))
    budget_estimate = Column(Float)
    category = Column(String(100), index=True)
    tags = Column(ARRAY(String), default=list)
    metadata_json = Column(JSONB, default=dict)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    created_by_user = relationship("User", back_populates="tenders")
    requirements = relationship("TenderRequirement", back_populates="tender", cascade="all, delete")
    requirement_extraction_runs = relationship(
        "RequirementExtractionRun",
        back_populates="tender",
        cascade="all, delete",
    )
    requirement_candidates = relationship(
        "RequirementCandidate",
        back_populates="tender",
        cascade="all, delete",
    )
    requirement_reviews = relationship(
        "RequirementReview",
        back_populates="tender",
        cascade="all, delete",
    )
    requirement_relations = relationship(
        "RequirementRelation",
        back_populates="tender",
        cascade="all, delete",
    )
    requirement_relation_reviews = relationship(
        "RequirementRelationReview",
        back_populates="tender",
        cascade="all, delete",
    )
    consolidated_requirements = relationship(
        "ConsolidatedRequirement",
        back_populates="tender",
        cascade="all, delete",
    )
    proposals = relationship("Proposal", back_populates="tender", cascade="all, delete")
    permissions = relationship("TenderPermission", back_populates="tender", cascade="all, delete")
    chat_room = relationship("ChatRoom", back_populates="tender", uselist=False, cascade="all, delete")
    documents = relationship(
        "Document",
        back_populates="tender",
        cascade="all, delete",
        foreign_keys="Document.tender_id",
    )


class TenderRequirement(Base):
    __tablename__ = "tender_requirements"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False)
    requirement_text = Column(Text, nullable=False)
    category = Column(String(100))
    priority = Column(String(20), default="medium")
    compliance_status = Column(
        Enum(ComplianceStatus), default=ComplianceStatus.NOT_ADDRESSED
    )
    proposal_section_id = Column(Integer, ForeignKey("proposal_sections.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    tender = relationship("Tender", back_populates="requirements")
    proposal_section = relationship("ProposalSection", back_populates="requirements")


class RequirementExtractionRun(Base):
    __tablename__ = "requirement_extraction_runs"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source_document_ref = Column(String(1000), nullable=True)
    filename = Column(String(500), nullable=True)
    extraction_method = Column(String(100), nullable=False, default="heuristic_v1")
    candidate_count = Column(Integer, default=0)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tender = relationship("Tender", back_populates="requirement_extraction_runs")
    actor = relationship("User", foreign_keys=[actor_id])
    candidates = relationship(
        "RequirementCandidate",
        back_populates="extraction_run",
        cascade="all, delete",
    )


class RequirementCandidate(Base):
    __tablename__ = "requirement_candidates"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    extraction_run_id = Column(
        Integer,
        ForeignKey("requirement_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_position = Column(Integer, nullable=False, default=0)
    source_document_ref = Column(String(1000), nullable=True)
    source_reference = Column(String(255), nullable=True)
    summary_text = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=False)
    category = Column(String(100))
    priority = Column(String(20), default="medium")
    confidence = Column(Float, nullable=True)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tender = relationship("Tender", back_populates="requirement_candidates")
    extraction_run = relationship("RequirementExtractionRun", back_populates="candidates")


class ConsolidatedRequirement(Base):
    __tablename__ = "consolidated_requirements"
    __table_args__ = (
        UniqueConstraint(
            "tender_id",
            "normalized_text",
            name="uq_consolidated_requirements_tender_normalized",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    canonical_text = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=False)
    category = Column(String(100))
    priority = Column(String(20), default="medium")
    confidence = Column(Float, nullable=True)
    source_count = Column(Integer, default=1)
    consolidation_method = Column(String(100), default="staging_v1")
    review_state = Column(String(50), default="pending")
    graph_state = Column(String(50), default="active", index=True)
    parent_requirement_id = Column(
        Integer,
        ForeignKey("consolidated_requirements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_requirement_key = Column(String(255), nullable=True, index=True)
    applicability = Column(JSONB, default=dict)
    conditions = Column(JSONB, default=list)
    exceptions = Column(JSONB, default=list)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tender = relationship("Tender", back_populates="consolidated_requirements")
    reviews = relationship(
        "RequirementReview",
        back_populates="consolidated_requirement",
        cascade="all, delete",
    )
    parent_requirement = relationship(
        "ConsolidatedRequirement",
        remote_side=[id],
        back_populates="child_requirements",
        foreign_keys=[parent_requirement_id],
    )
    child_requirements = relationship(
        "ConsolidatedRequirement",
        back_populates="parent_requirement",
        foreign_keys=[parent_requirement_id],
    )
    outgoing_relations = relationship(
        "RequirementRelation",
        foreign_keys="RequirementRelation.source_requirement_id",
        back_populates="source_requirement",
        cascade="all, delete",
    )
    incoming_relations = relationship(
        "RequirementRelation",
        foreign_keys="RequirementRelation.target_requirement_id",
        back_populates="target_requirement",
        cascade="all, delete",
    )


class RequirementReview(Base):
    __tablename__ = "requirement_reviews"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    consolidated_requirement_id = Column(
        Integer,
        ForeignKey("consolidated_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    previous_review_state = Column(String(50), nullable=True)
    new_review_state = Column(String(50), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tender = relationship("Tender", back_populates="requirement_reviews")
    consolidated_requirement = relationship("ConsolidatedRequirement", back_populates="reviews")
    actor = relationship("User", foreign_keys=[actor_id])


class RequirementRelation(Base):
    __tablename__ = "requirement_relations"
    __table_args__ = (
        UniqueConstraint(
            "tender_id",
            "source_requirement_id",
            "target_requirement_id",
            "relation_type",
            name="uq_requirement_relations_edge",
        ),
        CheckConstraint(
            "source_requirement_id <> target_requirement_id",
            name="ck_requirement_relations_not_self",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    source_requirement_id = Column(
        Integer,
        ForeignKey("consolidated_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_requirement_id = Column(
        Integer,
        ForeignKey("consolidated_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=True)
    review_state = Column(String(50), default="pending", index=True)
    graph_state = Column(String(50), default="active", index=True)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tender = relationship("Tender", back_populates="requirement_relations")
    source_requirement = relationship(
        "ConsolidatedRequirement",
        foreign_keys=[source_requirement_id],
        back_populates="outgoing_relations",
    )
    target_requirement = relationship(
        "ConsolidatedRequirement",
        foreign_keys=[target_requirement_id],
        back_populates="incoming_relations",
    )
    reviews = relationship(
        "RequirementRelationReview",
        back_populates="requirement_relation",
        cascade="all, delete",
    )


class RequirementRelationReview(Base):
    __tablename__ = "requirement_relation_reviews"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_relation_id = Column(
        Integer,
        ForeignKey("requirement_relations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    previous_review_state = Column(String(50), nullable=True)
    new_review_state = Column(String(50), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tender = relationship("Tender", back_populates="requirement_relation_reviews")
    requirement_relation = relationship("RequirementRelation", back_populates="reviews")
    actor = relationship("User", foreign_keys=[actor_id])


class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    status = Column(Enum(ProposalStatus), default=ProposalStatus.DRAFT, index=True)
    version = Column(Integer, default=1)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    tender = relationship("Tender", back_populates="proposals")
    created_by_user = relationship("User", back_populates="proposals")
    sections = relationship(
        "ProposalSection", back_populates="proposal", cascade="all, delete",
        order_by="ProposalSection.order"
    )


class ProposalSection(Base):
    __tablename__ = "proposal_sections"

    id = Column(Integer, primary_key=True, index=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(JSONB, default=dict)  # TipTap JSON content
    order = Column(Integer, default=0)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(Enum(SectionStatus), default=SectionStatus.TODO)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    proposal = relationship("Proposal", back_populates="sections")
    requirements = relationship("TenderRequirement", back_populates="proposal_section")


class ContentBlock(Base):
    __tablename__ = "content_blocks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(100), index=True)
    tags = Column(ARRAY(String), default=list)
    usage_count = Column(Integer, default=0)
    quality_rating = Column(Float, default=0.0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    file_url = Column(String(1000), nullable=False)
    doc_type = Column(String(50), index=True)  # tender, proposal, reference, cv, etc.
    file_size = Column(Integer)
    mime_type = Column(String(100))
    ingestion_status = Column(Enum(IngestionStatus), default=IngestionStatus.PENDING, index=True)
    ingestion_progress = Column(Float, default=0.0)
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text)
    metadata_json = Column(JSONB, default=dict)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ── New fields for tender document lifecycle ──
    tender_id = Column(
        Integer,
        ForeignKey("tenders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    storage_bucket = Column(String(255), nullable=True)
    storage_object_name = Column(String(1000), nullable=True)
    source_kind = Column(String(50), default="upload")  # upload | onlyoffice | generated | library
    ingestion_started_at = Column(DateTime(timezone=True), nullable=True)
    ingestion_completed_at = Column(DateTime(timezone=True), nullable=True)
    ingestion_job_id = Column(String(200), nullable=True)

    # Relationships
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete")
    tender = relationship(
        "Tender",
        back_populates="documents",
        foreign_keys=[tender_id],
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    section_title = Column(String(500))
    page_number = Column(Integer)
    metadata_json = Column(JSONB, default=dict)
    qdrant_point_id = Column(String(100))  # Reference to Qdrant vector
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="chunks")


class TenderPermission(Base):
    """Granular per-tender access control."""
    __tablename__ = "tender_permissions"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission = Column(String(50), default="viewer")  # viewer, editor
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    tender = relationship("Tender", back_populates="permissions")
    user = relationship("User", back_populates="tender_permissions", foreign_keys=[user_id])
    granted_by_user = relationship("User", foreign_keys=[granted_by])


class ChatRoom(Base):
    __tablename__ = "chat_rooms"
    __table_args__ = (UniqueConstraint("tender_id", name="uq_chat_rooms_tender_id"),)

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False)
    is_official = Column(Boolean, default=True, nullable=False)
    status = Column(Enum(ChatRoomStatus), default=ChatRoomStatus.PROVISIONED, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tender = relationship("Tender", back_populates="chat_room")
    creator = relationship("User", foreign_keys=[created_by])
    members = relationship("ChatMember", back_populates="chat_room", cascade="all, delete")
    messages = relationship("ChatMessage", back_populates="chat_room", cascade="all, delete")
    events = relationship("ChatEvent", back_populates="chat_room", cascade="all, delete")


class ChatMember(Base):
    __tablename__ = "chat_members"
    __table_args__ = (
        UniqueConstraint("chat_room_id", "user_id", name="uq_chat_members_room_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    chat_room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="viewer")
    source = Column(String(50), default="permission")
    is_active = Column(Boolean, default=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    chat_room = relationship("ChatRoom", back_populates="members")
    user = relationship("User", back_populates="chat_memberships")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    message_type = Column(Enum(ChatMessageType), default=ChatMessageType.TEXT, index=True)
    text_bucket = Column(String(255), nullable=True)
    text_object_key = Column(String(1000), nullable=True)
    text_preview = Column(Text, nullable=True)
    text_sha256 = Column(String(64), nullable=True)
    text_size = Column(Integer, nullable=True)
    reply_to_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    chat_room = relationship("ChatRoom", back_populates="messages")
    sender = relationship("User", back_populates="chat_messages_sent", foreign_keys=[sender_id])
    reply_to = relationship("ChatMessage", remote_side=[id], foreign_keys=[reply_to_message_id])
    attachments = relationship("ChatAttachment", back_populates="message", cascade="all, delete")


class ChatAttachment(Base):
    __tablename__ = "chat_attachments"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    bucket = Column(String(255), nullable=False)
    object_key = Column(String(1000), nullable=False)
    filename = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("ChatMessage", back_populates="attachments")


class ChatEvent(Base):
    __tablename__ = "chat_events"

    id = Column(Integer, primary_key=True, index=True)
    chat_room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(100), nullable=False, index=True)
    payload_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    chat_room = relationship("ChatRoom", back_populates="events")
    actor = relationship("User", back_populates="chat_events", foreign_keys=[actor_id])


class KpiDomainEvent(Base):
    __tablename__ = "kpi_domain_events"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(100), nullable=False, index=True)
    source = Column(String(100), nullable=False, default="tw-backend")
    external_tender_id = Column(String(100), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    payload_json = Column(JSONB, default=dict)
    delivery_status = Column(Enum(KpiEventDeliveryStatus), default=KpiEventDeliveryStatus.PENDING, index=True)
    delivery_attempts = Column(Integer, default=0)
    response_status_code = Column(Integer, nullable=True)
    response_json = Column(JSONB, default=dict)
    published_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tender = relationship("Tender")
    actor = relationship("User", foreign_keys=[actor_id])


class KpiAdminAuditLog(Base):
    __tablename__ = "kpi_admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="SET NULL"), nullable=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    admin_user_email = Column(String(255), nullable=False)
    admin_user_role = Column(String(50), nullable=False)
    delivered = Column(Boolean, nullable=True)
    degraded = Column(Boolean, default=False, nullable=False)
    upstream_status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    payload_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    tender = relationship("Tender")
    admin_user = relationship("User", foreign_keys=[admin_user_id])


class AIGatewayTarget(Base):
    __tablename__ = "ai_gateway_targets"

    id = Column(Integer, primary_key=True, index=True)
    route_key = Column(String(50), nullable=False)  # tender | opencode
    target_kind = Column(String(50), nullable=False, default="docker")  # docker|dmz|cloud
    connection_method = Column(String(50), nullable=False, default="llama_cpp")
    provider = Column(String(50), nullable=False, default="llama")
    base_url = Column(String(500), nullable=False)
    model_name = Column(String(200))
    api_key = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=1)
    timeout_ms = Column(Integer, default=30000)
    use_anonymizer = Column(Boolean, default=False)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AnonymizerAuditLog(Base):
    __tablename__ = "anonymizer_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_email = Column(String(255), nullable=False, default="")
    user_role = Column(String(50), nullable=False, default="")
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="SET NULL"), nullable=True, index=True)
    route_key = Column(String(50), nullable=True, index=True)
    llm_route = Column(String(50), nullable=True, index=True)
    anonymized = Column(Boolean, nullable=True)
    target_id = Column(Integer, ForeignKey("ai_gateway_targets.id", ondelete="SET NULL"), nullable=True, index=True)
    target_provider = Column(String(50), nullable=True)
    target_base_url = Column(String(500), nullable=True)
    session_token = Column(String(64), nullable=True)
    success = Column(Boolean, default=True, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    payload_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id])
    tender = relationship("Tender", foreign_keys=[tender_id])
    target = relationship("AIGatewayTarget", foreign_keys=[target_id])

from app.models.operational_observability import (
    AttendanceRecord,
    AttendanceStatus,
    CallSession,
    CallSessionStatus,
    ComplianceGate,
    ComplianceGateStatus,
    ContributionRequest,
    ContributionRequestStatus,
    ContributionUnit,
    ContributionUnitStatus,
    ReworkAction,
    ReworkStatus,
    ReviewCycle,
    ReviewCycleStatus,
)
from app.models.llm_settings import LLMSettings
from app.models.app_settings import AppSettings

