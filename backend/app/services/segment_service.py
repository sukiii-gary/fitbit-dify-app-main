from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.feature_vector import FeatureVector
from app.models.raw_segment import RawSegment
from app.schemas.segment import SegmentDetailResponse, SegmentIngestRequest, SegmentIngestResponse
from app.services.user_service import get_user_or_404


def ingest_segment(db: Session, payload: SegmentIngestRequest) -> SegmentIngestResponse:
    user = get_user_or_404(db=db, user_id=payload.user_id)
    segment = RawSegment(
        user_id=user.id,
        segment_start=payload.segment_start,
        segment_end=payload.segment_end,
        granularity=payload.granularity,
        source_type=payload.source_type,
        raw_payload_json=payload.raw_payload,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return SegmentIngestResponse(segment_id=segment.id, user_id=user.id)


def get_segment_or_404(db: Session, segment_id: str) -> RawSegment:
    query = (
        select(RawSegment)
        .where(RawSegment.id == segment_id)
        .options(selectinload(RawSegment.feature_vectors).selectinload(FeatureVector.predictions))
    )
    segment = db.scalar(query)
    if not segment:
        raise ValueError("Segment not found")
    return segment


def get_segment_detail(db: Session, segment_id: str) -> SegmentDetailResponse | None:
    try:
        segment = get_segment_or_404(db=db, segment_id=segment_id)
    except ValueError:
        return None

    predictions: list[dict] = []
    for feature_vector in segment.feature_vectors:
        for prediction in feature_vector.predictions:
            predictions.append(
                {
                    "prediction_id": prediction.id,
                    "feature_vector_id": feature_vector.id,
                    "model_name": prediction.model_name,
                    "model_version": prediction.model_version,
                    "top_label": prediction.top_label,
                    "probabilities": prediction.probabilities_json,
                    "created_at": prediction.created_at,
                }
            )

    return SegmentDetailResponse(
        id=segment.id,
        user_id=segment.user_id,
        segment_start=segment.segment_start,
        segment_end=segment.segment_end,
        granularity=segment.granularity,
        source_type=segment.source_type,
        raw_payload_json=segment.raw_payload_json,
        feature_vectors=[
            {
                "feature_vector_id": fv.id,
                "feature_version": fv.feature_version,
                "features": fv.features_json,
                "created_at": fv.created_at,
            }
            for fv in segment.feature_vectors
        ],
        predictions=predictions,
    )
