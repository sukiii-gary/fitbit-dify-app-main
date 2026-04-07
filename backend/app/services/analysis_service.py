from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dify.client import DifyClient, extract_workflow_outputs
from app.dify.prompt_builder import build_analysis_payload, build_local_fallback_output
from app.models.dify_run import DifyRun
from app.schemas.segment import AnalyzeRequest, AnalyzeResponse, PredictionRequest, SavedAnalysisResponse
from app.services.daily_analysis_service import build_daily_comparison, get_daily_data
from app.services.feature_service import extract_features_for_segment
from app.services.memory_service import build_rolling_memory_summary
from app.services.prediction_service import predict_for_segment
from app.services.segment_service import get_segment_or_404
from app.services.user_service import get_profile_or_404

dify_client = DifyClient()


def analyze_segment(db: Session, segment_id: str, payload: AnalyzeRequest) -> AnalyzeResponse:
    """
    分析一个 segment，支持两种模式：
    
    1. hour_level: 单小时数据分析，直接通过当前小时的metrics判断状态
    2. day_level: 日级数据分析，将当天数据与用户基线对比
    """
    segment = get_segment_or_404(db=db, segment_id=segment_id)
    
    # ⭐ Bug Fix: 删除该 segment 的所有旧分析数据
    old_runs = db.scalars(
        select(DifyRun).where(DifyRun.segment_id == segment.id)
    ).all()
    for old_run in old_runs:
        db.delete(old_run)
    db.commit()
    
    profile = get_profile_or_404(db=db, user_id=segment.user_id)
    prediction = predict_for_segment(db=db, segment_id=segment_id, payload=PredictionRequest())
    
    # 获取提取的特征向量
    feature_result = extract_features_for_segment(db=db, segment_id=segment_id)
    feature_vector = feature_result.features
    
    memory_summary = build_rolling_memory_summary(db=db, user_id=segment.user_id)

    # 根据分析类型选择不同的数据传递方式
    analysis_type = payload.analysis_type or "hour_level"
    
    if analysis_type == "day_level":
        # 日级分析：聚合当天的所有数据
        daily_data = get_daily_data(db=db, user_id=segment.user_id, segment=segment)
        daily_comparison = build_daily_comparison(
            daily_data=daily_data,
            baseline_stats=profile.baseline_stats_json or {},
        )
        
        # ⭐ 关键修复：构造当天聚合的raw_payload（而不是单小时数据）
        # 这样Dify收到的是当天的总步数、总热量、总睡眠等，而非单小时数据
        daily_aggregate_payload = {
            "date": daily_data.date,
            "steps": daily_data.total_steps,
            "calories": daily_data.total_calories,
            "sleep_minutes": daily_data.total_sleep_minutes,
            "active_minutes": daily_data.total_active_minutes,
            "sedentary_minutes": daily_data.total_sedentary_minutes,
            "heart_rate_stats": {
                "mean": daily_data.avg_heart_rate,
            },
            "segment_count": daily_data.segment_count,
        }
        
        dify_payload = build_analysis_payload(
            user_id=segment.user_id,
            segment_id=segment.id,
            profile=profile,
            raw_payload=daily_aggregate_payload,
            feature_vector=feature_vector,
            model_output={
                "top_label": prediction.top_label,
                "probabilities": prediction.probabilities,
            },
            rolling_memory_summary=memory_summary,
            user_query=payload.user_query,
            analysis_type="day_level",
            daily_comparison=daily_comparison,
        )
    else:
        # 小时级分析（默认）：直接分析单小时数据
        dify_payload = build_analysis_payload(
            user_id=segment.user_id,
            segment_id=segment.id,
            profile=profile,
            raw_payload=segment.raw_payload_json,
            feature_vector=feature_vector,
            model_output={
                "top_label": prediction.top_label,
                "probabilities": prediction.probabilities,
            },
            rolling_memory_summary=memory_summary,
            user_query=payload.user_query,
            analysis_type="hour_level",
            daily_comparison=None,
        )

    dify_result, status, workflow_run_id = dify_client.run_workflow(dify_payload)
    if status == "sent":
        llm_output = extract_workflow_outputs(dify_result)
    else:
        llm_output = build_local_fallback_output(
            raw_payload=segment.raw_payload_json,
            feature_vector=feature_vector,
            model_output={
                "top_label": prediction.top_label,
                "probabilities": prediction.probabilities,
            },
            memory_summary=memory_summary,
            status=status,
            status_message=dify_result.get("message"),
        )

    dify_run = DifyRun(
        user_id=segment.user_id,
        segment_id=segment.id,
        workflow_run_id=workflow_run_id,
        dify_inputs_json=dify_payload,
        dify_outputs_json=dify_result,
        status=status,
    )
    db.add(dify_run)
    db.commit()

    return AnalyzeResponse(
        segment_id=segment.id,
        user_id=segment.user_id,
        model_output={
            "top_label": prediction.top_label,
            "probabilities": prediction.probabilities,
        },
        dify_payload=dify_payload,
        llm_output=llm_output,
        status=status,
    )


def get_latest_analysis_for_segment(db: Session, segment_id: str) -> SavedAnalysisResponse | None:
    segment = get_segment_or_404(db=db, segment_id=segment_id)
    run = db.scalar(
        select(DifyRun)
        .where(DifyRun.segment_id == segment.id)
        .order_by(DifyRun.created_at.desc())
        .limit(1)
    )
    if not run:
        return None
    return build_saved_analysis_response(run)


def build_saved_analysis_response(run: DifyRun) -> SavedAnalysisResponse:
    dify_payload = run.dify_inputs_json or {}
    raw_output = run.dify_outputs_json or {}
    return SavedAnalysisResponse(
        dify_run_id=run.id,
        workflow_run_id=run.workflow_run_id,
        created_at=run.created_at,
        segment_id=run.segment_id,
        user_id=run.user_id,
        model_output=_model_output_from_dify_payload(dify_payload),
        dify_payload=dify_payload,
        llm_output=extract_workflow_outputs(raw_output),
        status=run.status,
        raw_dify_output=run.dify_outputs_json,
    )


def _model_output_from_dify_payload(dify_payload: dict) -> dict:
    inputs = dify_payload.get("inputs")
    if not isinstance(inputs, dict):
        return {}

    probabilities: dict | list | str | None = inputs.get("probability_json")
    if isinstance(probabilities, str):
        try:
            probabilities = json.loads(probabilities)
        except json.JSONDecodeError:
            probabilities = {"raw": probabilities}

    return {
        "top_label": inputs.get("top_label"),
        "probabilities": probabilities or {},
    }
