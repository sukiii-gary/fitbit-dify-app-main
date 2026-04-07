from __future__ import annotations

from statistics import mean, pstdev
from typing import Any


def _safe_mean(values: list[float]) -> float:
    return round(mean(values), 4) if values else 0.0


def _safe_std(values: list[float]) -> float:
    return round(pstdev(values), 4) if len(values) > 1 else 0.0


def build_feature_vector(raw_payload: dict[str, Any]) -> dict[str, Any]:
    """
    从原始 payload 构建特征向量。
    支持两种数据源：
    1. heart_rate_series: 原始秒级心率数据（直接计算统计）
    2. heart_rate_stats: 预计算的心率统计（直接使用）
    """
    # 尽量从 heart_rate_stats 中获取（预计算的精确值）
    heart_rate_stats = raw_payload.get("heart_rate_stats", {})
    if heart_rate_stats and isinstance(heart_rate_stats, dict):
        hr_mean = float(heart_rate_stats.get("mean", 0.0))
        hr_std = float(heart_rate_stats.get("std", 0.0))
        hr_min = float(heart_rate_stats.get("min", 0.0))
        hr_max = float(heart_rate_stats.get("max", 0.0))
    else:
        # Fallback: 从原始秒级数据计算（如果 heart_rate_stats 不可用）
        heart_rate_series = [float(value) for value in raw_payload.get("heart_rate_series", [])]
        hr_mean = _safe_mean(heart_rate_series)
        hr_std = _safe_std(heart_rate_series)
        hr_min = round(min(heart_rate_series), 4) if heart_rate_series else 0.0
        hr_max = round(max(heart_rate_series), 4) if heart_rate_series else 0.0

    hr_range = round(hr_max - hr_min, 4)
    
    steps = float(raw_payload.get("steps", 0))
    calories = float(raw_payload.get("calories", 0))
    sleep_minutes = float(raw_payload.get("sleep_minutes", 0))
    sedentary_minutes = float(raw_payload.get("sedentary_minutes", 0))
    active_minutes = float(raw_payload.get("active_minutes", 0))

    return {
        "steps_sum": round(steps, 4),
        "calories_sum": round(calories, 4),
        "sleep_minutes": round(sleep_minutes, 4),
        "sedentary_minutes": round(sedentary_minutes, 4),
        "active_minutes": round(active_minutes, 4),
        "hr_mean": round(hr_mean, 4),
        "hr_std": round(hr_std, 4),
        "hr_min": round(hr_min, 4),
        "hr_max": round(hr_max, 4),
        "hr_range": hr_range,
    }
