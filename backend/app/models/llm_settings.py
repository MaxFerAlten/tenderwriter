from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.db.database import Base


class LLMSettings(Base):
    __tablename__ = "llm_settings"

    id = Column(Integer, primary_key=True, index=True)
    max_tokens = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    stop_tokens = Column(String, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
