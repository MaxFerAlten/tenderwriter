"""
TenderWriter — App Settings Model

Stores general application settings as key-value pairs in a JSONB column.
Only one row is expected (singleton pattern).
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(JSONB, default=dict, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
