from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class DifyRun(Base):
    __tablename__ = "dify_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    segment_id: Mapped[str] = mapped_column(ForeignKey("raw_segments.id", ondelete="CASCADE"), nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(String(128))
    dify_inputs_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    dify_outputs_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="dify_runs")
    segment = relationship("RawSegment", back_populates="dify_runs")
