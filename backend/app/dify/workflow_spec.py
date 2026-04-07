from __future__ import annotations

INPUT_VARIABLES = [
    "user_id",
    "segment_id",
    "profile_prompt_prefix",
    "profile_json",
    "goals_json",
    "thresholds_json",
    "baseline_stats_json",
    "rolling_memory_summary",
    "feature_summary",
    "probability_json",
    "top_label",
    "user_query",
]

EXPECTED_OUTPUT_FIELDS = [
    "summary",
    "explanation",
    "personalized_advice",
    "confidence_note",
]

RECOMMENDED_NODE_ORDER = [
    "Start",
    "Template or Code",
    "LLM",
    "End",
]

SYSTEM_PROMPT_TEMPLATE = """{{profile_prompt_prefix}}

你会收到四类信息：
1. 用户长期画像与目标
2. 最近滚动窗口的记忆摘要
3. 当前 Fitbit 数据片段的特征摘要
4. 模型输出的类别概率

要求：
- 先解释模型结果，再结合用户画像给出建议
- 不做医学诊断
- 如果证据不足，要明确说明不确定性
- 输出 JSON，字段包含 summary、explanation、personalized_advice、confidence_note
"""

USER_MESSAGE_TEMPLATE = """用户画像: {{profile_json}}
目标: {{goals_json}}
阈值: {{thresholds_json}}
基线: {{baseline_stats_json}}

近期记忆: {{rolling_memory_summary}}

当前特征: {{feature_summary}}

模型结果:
top_label={{top_label}}
probabilities={{probability_json}}

用户问题:
{{user_query}}
"""


def build_workflow_blueprint(sample_payload: dict | None = None) -> dict:
    blueprint = {
        "app_type": "workflow",
        "input_variables": INPUT_VARIABLES,
        "expected_output_fields": EXPECTED_OUTPUT_FIELDS,
        "recommended_node_order": RECOMMENDED_NODE_ORDER,
        "system_prompt_template": SYSTEM_PROMPT_TEMPLATE,
        "user_message_template": USER_MESSAGE_TEMPLATE,
        "integration_notes": [
            "后端通过 /workflows/run 以 blocking 模式调用该 workflow。",
            "Workflow 必须先发布，否则 API 无法执行。",
            "End/Output 节点必须暴露 summary、explanation、personalized_advice、confidence_note 这几个字段。",
        ],
    }
    if sample_payload is not None:
        blueprint["sample_api_payload"] = sample_payload
    return blueprint
