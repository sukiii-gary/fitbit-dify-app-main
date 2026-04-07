"""日级分析服务 - 聚合单天数据与基线对比"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.raw_segment import RawSegment
from app.services.segment_service import get_segment_or_404
from app.services.user_service import get_profile_or_404


@dataclass(slots=True)
class DailyData:
    """单天聚合数据"""

    date: str
    total_steps: float
    total_calories: float
    total_sleep_minutes: float
    total_active_minutes: float
    total_sedentary_minutes: float
    avg_heart_rate: float
    segment_count: int


def get_daily_data(db: Session, user_id: str, segment: RawSegment) -> DailyData:
    """
    获取某个 segment 所在日期的所有数据聚合。
    用于日级分析时，获取当天的完整数据。
    """
    target_date = segment.segment_start.date()

    # 查询该用户该日期的所有 segments
    daily_segments = db.scalars(
        select(RawSegment)
        .where(
            RawSegment.user_id == user_id,
            func.date(RawSegment.segment_start) == target_date,
        )
        .order_by(RawSegment.segment_start)
    ).all()

    if not daily_segments:
        # 如果没找到，至少返回当前 segment 的数据
        daily_segments = [segment]

    # 聚合数据
    total_steps = 0.0
    total_calories = 0.0
    total_sleep_minutes = 0.0
    total_active_minutes = 0.0
    total_sedentary_minutes = 0.0
    all_hr_values = []

    for seg in daily_segments:
        payload = seg.raw_payload_json or {}
        total_steps += float(payload.get("steps", 0))
        total_calories += float(payload.get("calories", 0))
        total_sleep_minutes += float(payload.get("sleep_minutes", 0))
        total_active_minutes += float(payload.get("active_minutes", 0))
        total_sedentary_minutes += float(payload.get("sedentary_minutes", 0))

        # 心率数据：优先用 heart_rate_stats，再用 heart_rate_series
        hr_stats = payload.get("heart_rate_stats", {})
        if hr_stats and isinstance(hr_stats, dict):
            mean_hr = float(hr_stats.get("mean", 0))
            if mean_hr > 0:
                all_hr_values.append(mean_hr)
        else:
            hr_series = payload.get("heart_rate_series", [])
            if hr_series:
                all_hr_values.extend(float(v) for v in hr_series)

    avg_heart_rate = sum(all_hr_values) / len(all_hr_values) if all_hr_values else 0.0

    return DailyData(
        date=target_date.isoformat(),
        total_steps=round(total_steps, 2),
        total_calories=round(total_calories, 2),
        total_sleep_minutes=round(total_sleep_minutes, 2),
        total_active_minutes=round(total_active_minutes, 2),
        total_sedentary_minutes=round(total_sedentary_minutes, 2),
        avg_heart_rate=round(avg_heart_rate, 2),
        segment_count=len(daily_segments),
    )


def build_daily_comparison(
    daily_data: DailyData,
    baseline_stats: dict[str, Any],
) -> dict[str, Any]:
    """
    构建日数据与基线的对比。

    Args:
        daily_data: 当天聚合数据
        baseline_stats: 用户基线统计 (来自 user_profile.baseline_stats_json)

    Returns:
        对比结果
    """
    comparison = {
        "date": daily_data.date,
        "daily_metrics": {
            "total_steps": daily_data.total_steps,
            "total_calories": daily_data.total_calories,
            "total_sleep_minutes": daily_data.total_sleep_minutes,
            "total_active_minutes": daily_data.total_active_minutes,
            "total_sedentary_minutes": daily_data.total_sedentary_minutes,
            "avg_heart_rate": daily_data.avg_heart_rate,
        },
        "baseline_stats": {
            "avg_daily_steps": baseline_stats.get("avg_daily_steps", 0),
            "avg_daily_active_minutes": baseline_stats.get("avg_daily_active_minutes", 0),
            "avg_daily_sedentary_minutes": baseline_stats.get("avg_daily_sedentary_minutes", 0),
            "avg_daily_sleep_minutes": baseline_stats.get("avg_daily_sleep_minutes", 0),
        },
        "comparison": {
            "steps_vs_baseline": round(
                daily_data.total_steps - baseline_stats.get("avg_daily_steps", 0), 2
            ),
            "steps_ratio": round(
                daily_data.total_steps / max(baseline_stats.get("avg_daily_steps", 1), 1), 2
            ),
            "sleep_vs_baseline": round(
                daily_data.total_sleep_minutes - baseline_stats.get("avg_daily_sleep_minutes", 0), 2
            ),
            "sleep_ratio": round(
                daily_data.total_sleep_minutes
                / max(baseline_stats.get("avg_daily_sleep_minutes", 1), 1),
                2,
            ),
            "active_vs_baseline": round(
                daily_data.total_active_minutes
                - baseline_stats.get("avg_daily_active_minutes", 0),
                2,
            ),
            "sedentary_vs_baseline": round(
                daily_data.total_sedentary_minutes
                - baseline_stats.get("avg_daily_sedentary_minutes", 0),
                2,
            ),
        },
    }

    return comparison
