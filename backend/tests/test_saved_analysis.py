from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
import unittest

from app.services.analysis_service import build_saved_analysis_response


class SavedAnalysisResponseTest(unittest.TestCase):
    def test_build_saved_analysis_response_extracts_outputs_and_model_output(self) -> None:
        run = SimpleNamespace(
            id="run_001",
            workflow_run_id="workflow_001",
            created_at=datetime(2026, 4, 4, 18, 0, 0),
            segment_id="segment_001",
            user_id="user_001",
            status="sent",
            dify_inputs_json={
                "inputs": {
                    "top_label": "fatigue_high",
                    "probability_json": '{"fatigue_low": 0.1, "fatigue_high": 0.9}',
                }
            },
            dify_outputs_json={
                "data": {
                    "outputs": {
                        "summary": "high fatigue",
                        "explanation": "explanation text",
                    }
                }
            },
        )

        response = build_saved_analysis_response(run)

        self.assertEqual(response.dify_run_id, "run_001")
        self.assertEqual(response.workflow_run_id, "workflow_001")
        self.assertEqual(response.model_output["top_label"], "fatigue_high")
        self.assertEqual(response.model_output["probabilities"]["fatigue_high"], 0.9)
        self.assertEqual(response.llm_output["summary"], "high fatigue")
        self.assertEqual(response.status, "sent")


if __name__ == "__main__":
    unittest.main()
