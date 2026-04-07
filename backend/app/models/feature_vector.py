from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class FeatureVector(Base):
    __tablename__ = "feature_vectors"
    __table_args__ = (UniqueConstraint("segment_id", "feature_version", name="uq_feature_vectors_segment_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    segment_id: Mapped[str] = mapped_column(ForeignKey("raw_segments.id", ondelete="CASCADE"), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    features_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    segment = relationship("RawSegment", back_populates="feature_vectors")
    predictions = relationship("ModelPrediction", back_populates="feature_vector", cascade="all, delete-orphan")
