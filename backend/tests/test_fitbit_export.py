from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.importers.fitbit_export import load_fitbit_export


class FitbitExportImportTest(unittest.TestCase):
    def test_load_fitbit_export_builds_hourly_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)

            steps_csv = "\n".join(
                [
                    "date,time,steps",
                    "2026-04-04,08:00:00,100",
                    "2026-04-04,08:01:00,25",
                    "2026-04-04,09:05:00,50",
                ]
            )
            (export_dir / "steps.csv").write_text(steps_csv, encoding="utf-8")

            heart_rate = {
                "activities-heart": [{"dateTime": "2026-04-04"}],
                "activities-heart-intraday": {
                    "dataset": [
                        {"time": "08:00:00", "value": 80},
                        {"time": "08:01:00", "value": 82},
                        {"time": "09:05:00", "value": 78},
                    ]
                },
            }
            (export_dir / "heart_rate-2026-04-04.json").write_text(
                json.dumps(heart_rate),
                encoding="utf-8",
            )

            sleep = {
                "sleep": [
                    {
                        "startTime": "2026-04-04T08:30:00",
                        "endTime": "2026-04-04T09:15:00",
                        "minutesAsleep": 45,
                    }
                ]
            }
            (export_dir / "sleep-2026-04-04.json").write_text(json.dumps(sleep), encoding="utf-8")

            result = load_fitbit_export(export_dir, timezone="Asia/Shanghai")

        self.assertEqual(result.processed_sources, 3)
        self.assertEqual(len(result.segments), 2)

        first, second = result.segments
        self.assertEqual(first.raw_payload["steps"], 125.0)
        self.assertEqual(first.raw_payload["sleep_minutes"], 30.0)
        self.assertEqual(first.raw_payload["heart_rate_series"], [80.0, 82.0])

        self.assertEqual(second.raw_payload["steps"], 50.0)
        self.assertEqual(second.raw_payload["sleep_minutes"], 15.0)
        self.assertEqual(second.raw_payload["heart_rate_series"], [78.0])


if __name__ == "__main__":
    unittest.main()
