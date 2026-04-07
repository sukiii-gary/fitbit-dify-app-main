from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class RawSegment(Base):
    __tablename__ = "raw_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    segment_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granularity: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="segments")
    feature_vectors = relationship("FeatureVector", back_populates="segment", cascade="all, delete-orphan")
    dify_runs = relationship("DifyRun", back_populates="segment", cascade="all, delete-orphan")
