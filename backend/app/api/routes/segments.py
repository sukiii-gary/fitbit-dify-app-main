from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.segment import (
    AnalyzeRequest,
    AnalyzeResponse,
    FeatureExtractionResponse,
    PredictionRequest,
    PredictionResponse,
    SavedAnalysisResponse,
    SegmentDetailResponse,
    SegmentIngestRequest,
    SegmentIngestResponse,
)
from app.services.analysis_service import analyze_segment, get_latest_analysis_for_segment
from app.services.feature_service import extract_features_for_segment
from app.services.prediction_service import predict_for_segment
from app.services.segment_service import get_segment_detail, ingest_segment

router = APIRouter()


@router.post("/ingest", response_model=SegmentIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_segment_endpoint(
    payload: SegmentIngestRequest,
    db: Session = Depends(get_db),
) -> SegmentIngestResponse:
    try:
        return ingest_segment(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{segment_id}", response_model=SegmentDetailResponse)
def get_segment_endpoint(segment_id: str, db: Session = Depends(get_db)) -> SegmentDetailResponse:
    segment = get_segment_detail(db=db, segment_id=segment_id)
    if not segment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
    return segment


@router.get("/{segment_id}/latest-analysis", response_model=SavedAnalysisResponse)
def get_latest_analysis_endpoint(segment_id: str, db: Session = Depends(get_db)) -> SavedAnalysisResponse:
    try:
        record = get_latest_analysis_for_segment(db=db, segment_id=segment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return record


@router.post("/{segment_id}/extract-features", response_model=FeatureExtractionResponse)
def extract_features_endpoint(segment_id: str, db: Session = Depends(get_db)) -> FeatureExtractionResponse:
    try:
        return extract_features_for_segment(db=db, segment_id=segment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{segment_id}/predict", response_model=PredictionResponse)
def predict_endpoint(
    segment_id: str,
    payload: PredictionRequest,
    db: Session = Depends(get_db),
) -> PredictionResponse:
    try:
        return predict_for_segment(db=db, segment_id=segment_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{segment_id}/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(
    segment_id: str,
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    try:
        return analyze_segment(db=db, segment_id=segment_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
