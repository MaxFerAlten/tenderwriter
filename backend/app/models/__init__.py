"""
TenderWriter — SQLAlchemy Models for Tenders, Proposals, Content, and Documents
"""

import enum
from datetime import datetime

from sqlalchemy import (
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    tenders = relationship("Tender", back_populates="created_by_user")
    proposals = relationship("Proposal", back_populates="created_by_user")


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
    tags = Column(ARRAY(String), default=[])
    metadata_json = Column(JSONB, default={})
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    created_by_user = relationship("User", back_populates="tenders")
    requirements = relationship("TenderRequirement", back_populates="tender", cascade="all, delete")
    proposals = relationship("Proposal", back_populates="tender", cascade="all, delete")


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
    content = Column(JSONB, default={})  # TipTap JSON content
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
    tags = Column(ARRAY(String), default=[])
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
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text)
    metadata_json = Column(JSONB, default={})
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    section_title = Column(String(500))
    page_number = Column(Integer)
    metadata_json = Column(JSONB, default={})
    qdrant_point_id = Column(String(100))  # Reference to Qdrant vector
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="chunks")
