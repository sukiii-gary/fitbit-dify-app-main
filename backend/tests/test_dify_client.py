from __future__ import annotations

import unittest

from app.dify.client import extract_workflow_outputs


class DifyClientTest(unittest.TestCase):
    def test_extract_workflow_outputs_prefers_nested_outputs(self) -> None:
        result = {
            "workflow_run_id": "wf_123",
            "data": {
                "outputs": {
                    "summary": "ok",
                    "explanation": "details",
                }
            },
        }

        outputs = extract_workflow_outputs(result)

        self.assertEqual(outputs["summary"], "ok")
        self.assertEqual(outputs["explanation"], "details")

    def test_extract_workflow_outputs_falls_back_to_raw_dict(self) -> None:
        result = {"message": "no nested outputs"}

        outputs = extract_workflow_outputs(result)

        self.assertEqual(outputs["message"], "no nested outputs")


if __name__ == "__main__":
    unittest.main()
