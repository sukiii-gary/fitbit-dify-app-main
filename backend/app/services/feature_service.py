from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.feature_engineering import build_feature_vector
from app.models.feature_vector import FeatureVector
from app.schemas.segment import FeatureExtractionResponse
from app.services.segment_service import get_segment_or_404

FEATURE_VERSION = "v1"


def extract_features_for_segment(db: Session, segment_id: str) -> FeatureExtractionResponse:
    segment = get_segment_or_404(db=db, segment_id=segment_id)
    existing = db.scalar(
        select(FeatureVector).where(
            FeatureVector.segment_id == segment.id,
            FeatureVector.feature_version == FEATURE_VERSION,
        )
    )
    if existing:
        return FeatureExtractionResponse(
            feature_vector_id=existing.id,
            segment_id=segment.id,
            feature_version=existing.feature_version,
            features=existing.features_json,
        )

    features = build_feature_vector(segment.raw_payload_json)
    feature_vector = FeatureVector(
        segment_id=segment.id,
        feature_version=FEATURE_VERSION,
        features_json=features,
    )
    db.add(feature_vector)
    db.commit()
    db.refresh(feature_vector)
    return FeatureExtractionResponse(
        feature_vector_id=feature_vector.id,
        segment_id=segment.id,
        feature_version=feature_vector.feature_version,
        features=feature_vector.features_json,
    )
