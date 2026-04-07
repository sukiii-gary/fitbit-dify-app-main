from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable


@dataclass(slots=True)
class ProfileSeed:
    profile: dict[str, Any]
    goals: dict[str, Any]
    thresholds: dict[str, Any]
    baseline_stats: dict[str, Any]
    system_prompt_prefix: str


def build_fitabase_profile_seed(segments: Iterable[Any], external_user_id: str) -> ProfileSeed:
    segment_list = list(segments)
    if not segment_list:
        raise ValueError("At least one segment is required to build a fitabase profile seed.")

    daily = defaultdict(
        lambda: {
            "steps": 0.0,
            "calories": 0.0,
            "sleep_minutes": 0.0,
            "active_minutes": 0.0,
            "sedentary_minutes": 0.0,
        }
    )
    hourly_steps = defaultdict(list)
    all_hr_values: list[float] = []
    hr_segments = 0

    first_segment = min(segment_list, key=lambda item: item.segment_start)
    last_segment = max(segment_list, key=lambda item: item.segment_start)

    for segment in segment_list:
        payload = segment.raw_payload_json or {}
        day_key = segment.segment_start.date().isoformat()

        steps = _as_float(payload.get("steps"))
        calories = _as_float(payload.get("calories"))
        sleep_minutes = _as_float(payload.get("sleep_minutes"))
        active_minutes = _as_float(payload.get("active_minutes"))
        sedentary_minutes = _as_float(payload.get("sedentary_minutes"))

        daily[day_key]["steps"] += steps
        daily[day_key]["calories"] += calories
        daily[day_key]["sleep_minutes"] += sleep_minutes
        daily[day_key]["active_minutes"] += active_minutes
        daily[day_key]["sedentary_minutes"] += sedentary_minutes

        hourly_steps[segment.segment_start.hour].append(steps)

        hr_series = payload.get("heart_rate_series") or []
        if hr_series:
            hr_segments += 1
            all_hr_values.extend(float(value) for value in hr_series)

    daily_steps = [values["steps"] for values in daily.values()]
    daily_calories = [values["calories"] for values in daily.values()]
    daily_sleep = [values["sleep_minutes"] for values in daily.values()]
    daily_sleep_tracked = [value for value in daily_sleep if value > 0]
    daily_active = [values["active_minutes"] for values in daily.values()]
    daily_sedentary = [values["sedentary_minutes"] for values in daily.values()]

    days_observed = len(daily)
    segment_count = len(segment_list)
    data_span_days = (last_segment.segment_start.date() - first_segment.segment_start.date()).days + 1

    avg_daily_steps = _safe_mean(daily_steps)
    avg_daily_calories = _safe_mean(daily_calories)
    avg_daily_active = _safe_mean(daily_active)
    avg_daily_sedentary = _safe_mean(daily_sedentary)
    avg_daily_sleep_all_days = _safe_mean(daily_sleep)
    avg_daily_sleep_tracked = _safe_mean(daily_sleep_tracked) if daily_sleep_tracked else 0.0

    sleep_tracking_ratio = round(len(daily_sleep_tracked) / max(1, days_observed), 4)
    sleep_tracking_quality = _label_sleep_tracking(sleep_tracking_ratio)

    heart_rate_coverage_ratio = round(hr_segments / max(1, segment_count), 4)
    heart_rate_coverage = _label_coverage(heart_rate_coverage_ratio)
    heart_rate_mean = round(_safe_mean(all_hr_values), 2) if all_hr_values else 0.0
    resting_hr_proxy = round(_percentile(all_hr_values, 0.1), 2) if all_hr_values else 0.0

    peak_activity_hour = max(hourly_steps, key=lambda hour: _safe_mean(hourly_steps[hour]))
    peak_activity_window = _label_peak_window(peak_activity_hour)

    activity_level = _label_activity_level(avg_daily_steps)
    activity_consistency = _label_consistency(daily_steps)
    primary_goal = _pick_primary_goal(
        avg_daily_steps=avg_daily_steps,
        avg_daily_active=avg_daily_active,
        avg_daily_sleep_tracked=avg_daily_sleep_tracked,
        sleep_tracking_quality=sleep_tracking_quality,
    )

    step_goal = _round_to_step(_clamp(max(avg_daily_steps * 1.1, 6000.0), 6000.0, 12000.0), 500)
    active_goal = _round_to_step(_clamp(max(avg_daily_active * 1.1, 30.0), 30.0, 90.0), 5)
    if sleep_tracking_quality == "limited":
        sleep_goal_hours = 8.0
    else:
        sleep_goal_hours = _round_to_half(_clamp((avg_daily_sleep_tracked / 60.0) * 1.05, 7.0, 8.5))

    low_sleep_threshold = _round_to_step(
        _clamp((avg_daily_sleep_tracked or 480.0) * 0.85, 360.0, 480.0),
        15,
    )
    low_activity_threshold = _round_to_step(_clamp(avg_daily_steps * 0.7, 2500.0, 8000.0), 250)
    high_sedentary_threshold = _round_to_step(_clamp(avg_daily_sedentary * 1.1, 600.0, 960.0), 15)
    elevated_hr_threshold = int(round(_clamp((resting_hr_proxy or heart_rate_mean or 80.0) + 15.0, 85.0, 120.0)))

    source_user_id = external_user_id.removeprefix("fitabase_")

    profile = {
        "source": "fitabase_merged",
        "source_user_id": source_user_id,
        "primary_goal": primary_goal,
        "activity_level": activity_level,
        "activity_consistency": activity_consistency,
        "sleep_tracking_quality": sleep_tracking_quality,
        "heart_rate_coverage": heart_rate_coverage,
        "peak_activity_window": peak_activity_window,
        "days_observed": days_observed,
        "segment_count": segment_count,
        "data_span_days": data_span_days,
    }

    goals = {
        "primary_goal": primary_goal,
        "daily_steps_goal": step_goal,
        "sleep_goal_hours": sleep_goal_hours,
        "active_minutes_goal": active_goal,
        "analysis_focus": "fatigue_management",
    }

    thresholds = {
        "fatigue_high_threshold": 0.7,
        "low_sleep_minutes_threshold": low_sleep_threshold,
        "low_activity_steps_threshold": low_activity_threshold,
        "high_sedentary_minutes_threshold": high_sedentary_threshold,
        "elevated_hr_threshold": elevated_hr_threshold,
    }

    baseline_stats = {
        "avg_daily_steps": round(avg_daily_steps, 2),
        "avg_daily_calories": round(avg_daily_calories, 2),
        "avg_daily_active_minutes": round(avg_daily_active, 2),
        "avg_daily_sedentary_minutes": round(avg_daily_sedentary, 2),
        "avg_daily_sleep_minutes": round(avg_daily_sleep_all_days, 2),
        "avg_daily_sleep_minutes_tracked_days": round(avg_daily_sleep_tracked, 2),
        "sleep_tracking_day_ratio": sleep_tracking_ratio,
        "heart_rate_coverage_ratio": heart_rate_coverage_ratio,
        "heart_rate_mean": heart_rate_mean,
        "resting_hr_proxy": resting_hr_proxy,
        "peak_activity_hour": peak_activity_hour,
        "data_start": first_segment.segment_start.isoformat(),
        "data_end": last_segment.segment_end.isoformat(),
    }

    system_prompt_prefix = (
        "你正在为一位 Fitbit 用户提供个性化疲劳与恢复分析。"
        f"该用户的历史基线显示其属于{_activity_level_cn(activity_level)}，"
        f"活动高峰通常出现在{_peak_window_cn(peak_activity_window)}，"
        f"当前主要目标是{_goal_cn(primary_goal)}。"
        "优先结合其步数、活动分钟、久坐时间、睡眠和心率基线解释模型输出，"
        "不要做医学诊断；如果睡眠追踪或心率覆盖不足，请明确说明不确定性。"
    )

    return ProfileSeed(
        profile=profile,
        goals=goals,
        thresholds=thresholds,
        baseline_stats=baseline_stats,
        system_prompt_prefix=system_prompt_prefix,
    )


def _as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _safe_mean(values: Iterable[float]) -> float:
    value_list = list(values)
    return mean(value_list) if value_list else 0.0


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * quantile))
    return ordered[index]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _round_to_step(value: float, step: int, minimum: float | None = None, maximum: float | None = None) -> int:
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return int(round(value / step) * step)


def _round_to_half(value: float) -> float:
    return round(value * 2) / 2


def _label_activity_level(avg_daily_steps: float) -> str:
    if avg_daily_steps < 5000:
        return "sedentary"
    if avg_daily_steps < 8000:
        return "lightly_active"
    if avg_daily_steps < 11000:
        return "moderately_active"
    return "highly_active"


def _label_consistency(daily_steps: list[float]) -> str:
    if len(daily_steps) < 2:
        return "insufficient_data"
    average = _safe_mean(daily_steps)
    if average <= 0:
        return "irregular"
    variance = sum((value - average) ** 2 for value in daily_steps) / len(daily_steps)
    cv = (variance ** 0.5) / average
    if cv <= 0.35:
        return "stable"
    if cv <= 0.65:
        return "mixed"
    return "irregular"


def _label_sleep_tracking(ratio: float) -> str:
    if ratio < 0.15:
        return "limited"
    if ratio < 0.5:
        return "partial"
    return "good"


def _label_coverage(ratio: float) -> str:
    if ratio < 0.05:
        return "none"
    if ratio < 0.35:
        return "partial"
    return "good"


def _label_peak_window(hour: int) -> str:
    if 5 <= hour <= 10:
        return "morning"
    if 11 <= hour <= 16:
        return "afternoon"
    if 17 <= hour <= 21:
        return "evening"
    return "overnight"


def _pick_primary_goal(
    *,
    avg_daily_steps: float,
    avg_daily_active: float,
    avg_daily_sleep_tracked: float,
    sleep_tracking_quality: str,
) -> str:
    if sleep_tracking_quality != "limited" and avg_daily_sleep_tracked < 390:
        return "sleep_improvement"
    if avg_daily_steps < 5500:
        return "activity_increase"
    if avg_daily_active < 30:
        return "endurance_building"
    return "fatigue_management"


def _activity_level_cn(label: str) -> str:
    mapping = {
        "sedentary": "久坐偏多型",
        "lightly_active": "轻度活跃型",
        "moderately_active": "中度活跃型",
        "highly_active": "高活跃型",
    }
    return mapping.get(label, "一般活跃型")


def _peak_window_cn(label: str) -> str:
    mapping = {
        "morning": "上午",
        "afternoon": "下午",
        "evening": "傍晚到夜间",
        "overnight": "夜间到凌晨",
    }
    return mapping.get(label, "白天")


def _goal_cn(label: str) -> str:
    mapping = {
        "sleep_improvement": "改善睡眠与恢复",
        "activity_increase": "提升日常活动量",
        "endurance_building": "增加稳定运动时长",
        "fatigue_management": "管理疲劳并维持稳定状态",
    }
    return mapping.get(label, "管理疲劳并维持稳定状态")
