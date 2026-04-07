from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.predictor import Predictor
from app.models.feature_vector import FeatureVector
from app.models.model_prediction import ModelPrediction
from app.schemas.segment import FeatureExtractionResponse, PredictionRequest, PredictionResponse
from app.services.feature_service import extract_features_for_segment

predictor = Predictor()


def _ensure_feature_vector(db: Session, segment_id: str) -> FeatureExtractionResponse:
    return extract_features_for_segment(db=db, segment_id=segment_id)


def predict_for_segment(db: Session, segment_id: str, payload: PredictionRequest) -> PredictionResponse:
    feature_result = _ensure_feature_vector(db=db, segment_id=segment_id)

    feature_vector = db.scalar(select(FeatureVector).where(FeatureVector.id == feature_result.feature_vector_id))
    if not feature_vector:
        raise ValueError("Feature vector not found")

    existing = db.scalar(
        select(ModelPrediction).where(
            ModelPrediction.feature_vector_id == feature_vector.id,
            ModelPrediction.model_name == payload.model_name,
            ModelPrediction.model_version == payload.model_version,
        )
    )
    if existing:
        return PredictionResponse(
            prediction_id=existing.id,
            segment_id=segment_id,
            model_name=existing.model_name,
            model_version=existing.model_version,
            top_label=existing.top_label,
            probabilities=existing.probabilities_json,
        )

    top_label, probabilities = predictor.predict(
        features=feature_vector.features_json,
        model_name=payload.model_name,
        model_version=payload.model_version,
    )
    prediction = ModelPrediction(
        feature_vector_id=feature_vector.id,
        model_name=payload.model_name,
        model_version=payload.model_version,
        top_label=top_label,
        probabilities_json=probabilities,
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return PredictionResponse(
        prediction_id=prediction.id,
        segment_id=segment_id,
        model_name=prediction.model_name,
        model_version=prediction.model_version,
        top_label=prediction.top_label,
        probabilities=prediction.probabilities_json,
    )
