from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.models.user_profile import UserProfile

settings = get_settings()


def build_analysis_payload(
    user_id: str,
    segment_id: str,
    profile: UserProfile,
    raw_payload: dict[str, Any],
    feature_vector: dict[str, Any],
    model_output: dict[str, Any],
    rolling_memory_summary: dict[str, Any],
    user_query: str,
    analysis_type: str = "hour_level",
    daily_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    构建发送给 Dify 的 payload，支持两种分析模式。
    
    Args:
        analysis_type: "hour_level" 或 "day_level"
        daily_comparison: 日级分析时的当天数据与基线对比（仅当 analysis_type="day_level" 时使用）
    """
    feature_summary = _build_feature_summary(raw_payload, feature_vector)
    
    # 确保 profile 字段有默认值
    profile_json_safe = profile.profile_json or {}
    goals_json_safe = profile.goals_json or {}
    thresholds_json_safe = profile.thresholds_json or {}
    baseline_stats_json_safe = profile.baseline_stats_json or {}
    
    # ⭐ 根据分析类型生成不同的提示词前缀
    if analysis_type == "day_level":
        prompt_prefix = _build_day_level_prompt(profile_json_safe, goals_json_safe, baseline_stats_json_safe)
    else:
        prompt_prefix = _build_hour_level_prompt(profile_json_safe)
    
    inputs = {
        "user_id": user_id,
        "segment_id": segment_id,
        "profile_prompt_prefix": prompt_prefix,
        "profile_json": json.dumps(profile_json_safe, ensure_ascii=False),
        "goals_json": json.dumps(goals_json_safe, ensure_ascii=False),
        "thresholds_json": json.dumps(thresholds_json_safe, ensure_ascii=False),
        "baseline_stats_json": json.dumps(baseline_stats_json_safe, ensure_ascii=False),
        "rolling_memory_summary": json.dumps(rolling_memory_summary, ensure_ascii=False),
        "feature_summary": feature_summary,
        "probability_json": json.dumps(model_output["probabilities"], ensure_ascii=False),
        "top_label": model_output["top_label"],
        "user_query": user_query,
        "analysis_type": analysis_type,
    }
    
    # 日级分析时，添加当天数据与基线对比
    if analysis_type == "day_level" and daily_comparison:
        inputs["daily_comparison"] = json.dumps(daily_comparison, ensure_ascii=False)
    
    return {
        "inputs": inputs,
        "response_mode": settings.dify_response_mode,
        "user": user_id,
    }


def _build_hour_level_prompt(profile_json: dict[str, Any]) -> str:
    """
    构建小时级分析的提示词前缀。
    关注：当前的步数、心率、久坐、睡眠等指标
    """
    activity_level = profile_json.get("activity_level", "一般")
    primary_goal = profile_json.get("primary_goal", "整体健康")
    peak_window = profile_json.get("peak_activity_window", "未知")
    
    return f"""你正在为一位 Fitbit 用户提供实时的小时级健康分析。该用户的历史数据显示活跃水平为"{activity_level}"，主要目标是改善"{primary_goal}"，通常在"{peak_window}"时段活动最活跃。

基于当前这一小时的数据（步数、心率、久坐时间、睡眠时长等），请：
1. 分析用户当前的活动强度和疲劳水平
2. 根据当前的步数、心率变异性、久坐时间、睡眠质量等生理指标判断状态
3. 提供即时的、可操作的建议（例如是否应该起身活动、调整节奏等）

重点：这是对当前小时的独立分析，不需要与长期基线比较。关注当下的生理状态和实时变化。"""


def _build_day_level_prompt(
    profile_json: dict[str, Any], 
    goals_json: dict[str, Any],
    baseline_stats_json: dict[str, Any]
) -> str:
    """
    构建日级分析的提示词前缀。
    关注：与用户长期基线和个人目标的对比
    """
    activity_level = profile_json.get("activity_level", "一般")
    primary_goal = goals_json.get("primary_goal", "整体健康")
    steps_goal = goals_json.get("daily_steps_goal", "未设置")
    sleep_goal = goals_json.get("sleep_goal_hours", "未设置")
    avg_steps = baseline_stats_json.get("avg_daily_steps", "未知")
    avg_sleep = baseline_stats_json.get("avg_daily_sleep_minutes", "未知")
    
    return f"""你正在为一位 Fitbit 用户提供日级综合分析，并与该用户的长期基线数据对比。

用户背景：
- 活跃水平: {activity_level}
- 主要目标: {primary_goal}
- 日均步数目标: {steps_goal} 步
- 睡眠目标: {sleep_goal} 小时
- 用户长期平均步数: {avg_steps} 步/天
- 用户长期平均睡眠: {avg_sleep} 分钟/天

请分析今天的表现是否超出或低于用户的长期习惯：
1. 比较今天的总步数、活动分钟数与用户长期基线
2. 评估今天的睡眠质量或数量是否异常
3. 识别用户是否达成或超越了个人目标
4. 根据与基线的偏离程度（+/- 50% 等）提供针对性建议

重点：这是对整天表现的综合评价，强调与用户长期习惯的对比，帮助用户理解今天是否是一个"好日子"或需要调整的日子。"""


def _build_feature_summary(raw_payload: dict[str, Any], feature_vector: dict[str, Any]) -> str:
    """
    构建特征摘要字符串，优先使用已提取的特征向量数据。
    
    Args:
        raw_payload: 原始数据（steps, calories等）
        feature_vector: 已提取的特征向量（hr_mean, hr_std, hr_min, hr_max等）
    
    Returns:
        格式化的特征摘要字符串
    """
    parts = [
        f"steps={raw_payload.get('steps', 0)}",
        f"calories={raw_payload.get('calories', 0)}",
        f"sleep_minutes={raw_payload.get('sleep_minutes', 0)}",
        f"time_in_bed={raw_payload.get('time_in_bed', 0)}",
        f"sleep_quality={raw_payload.get('sleep_quality', 0)}",
        f"sedentary_minutes={raw_payload.get('sedentary_minutes', 0)}",
        f"active_minutes={raw_payload.get('active_minutes', 0)}",
    ]
    
    # 使用提取的特征向量数据（精确计算）
    if feature_vector:
        parts.extend([
            f"hr_mean={feature_vector.get('hr_mean', 0)}",
            f"hr_std={feature_vector.get('hr_std', 0)}",
            f"hr_min={feature_vector.get('hr_min', 0)}",
            f"hr_max={feature_vector.get('hr_max', 0)}",
            f"hr_range={feature_vector.get('hr_range', 0)}",
        ])
    else:
        # Fallback: 从原始数据计算（如果特征向量不可用）
        hr_series = raw_payload.get("heart_rate_series", [])
        if hr_series:
            parts.append(f"heart_rate_series_length={len(hr_series)}")
            parts.append(f"hr_mean={round(sum(hr_series) / len(hr_series), 2)}")
            parts.append(f"hr_min={round(min(hr_series), 2)}")
            parts.append(f"hr_max={round(max(hr_series), 2)}")
    
    return ", ".join(parts)


def build_local_fallback_output(
    raw_payload: dict[str, Any],
    feature_vector: dict[str, Any],
    model_output: dict[str, Any],
    memory_summary: dict[str, Any],
    *,
    status: str = "skipped",
    status_message: str | None = None,
) -> dict[str, Any]:
    fallback_reason = {
        "skipped": "当前还没有配置 Dify，系统返回本地回退说明。",
        "error": "Dify 请求失败，系统返回本地回退说明。",
    }.get(status, "系统返回本地回退说明。")

    if status_message:
        fallback_reason = f"{fallback_reason} 详情: {status_message}"

    # 使用特征向量中的数据
    hr_mean = feature_vector.get("hr_mean", 0) if feature_vector else 0
    hr_std = feature_vector.get("hr_std", 0) if feature_vector else 0
    
    return {
        "summary": f"当前片段的主要分类结果为 {model_output['top_label']}。",
        "explanation": (
            f"{fallback_reason}"
            f" steps={raw_payload.get('steps', 0)},"
            f" sleep_minutes={raw_payload.get('sleep_minutes', 0)},"
            f" hr_mean={hr_mean},"
            f" hr_std={hr_std},"
            f" avg_steps_recent={memory_summary.get('avg_steps')}."
        ),
        "personalized_advice": [
            "先确保 Dify 工作流已配置和上线。",
            "或根据实时心率、睡眠、步数数据，定制你的活动计划。",
        ],
        "probabilities": model_output["probabilities"],
        "confidence_note": "这是本地回退结果，不代表最终的 Dify 解释效果。",
    }
