from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.importers.fitabase_merged import load_fitabase_merged_export


class FitabaseMergedImportTest(unittest.TestCase):
    def test_load_fitabase_merged_export_groups_segments_by_source_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)

            (export_dir / "hourlySteps_merged.csv").write_text(
                "\n".join(
                    [
                        "Id,ActivityHour,StepTotal",
                        "1001,4/12/2016 8:00:00 AM,120",
                        "2002,4/12/2016 8:00:00 AM,80",
                    ]
                ),
                encoding="utf-8",
            )
            (export_dir / "hourlyCalories_merged.csv").write_text(
                "\n".join(
                    [
                        "Id,ActivityHour,Calories",
                        "1001,4/12/2016 8:00:00 AM,50",
                        "2002,4/12/2016 8:00:00 AM,40",
                    ]
                ),
                encoding="utf-8",
            )
            (export_dir / "minuteIntensitiesNarrow_merged.csv").write_text(
                "\n".join(
                    [
                        "Id,ActivityMinute,Intensity",
                        "1001,4/12/2016 8:00:00 AM,2",
                        "1001,4/12/2016 8:01:00 AM,0",
                        "2002,4/12/2016 8:00:00 AM,1",
                    ]
                ),
                encoding="utf-8",
            )
            (export_dir / "minuteSleep_merged.csv").write_text(
                "\n".join(
                    [
                        "Id,date,value,logId",
                        "1001,4/12/2016 8:30:00 AM,1,1",
                        "2002,4/12/2016 8:40:00 AM,1,2",
                    ]
                ),
                encoding="utf-8",
            )

            result = load_fitabase_merged_export(export_dir, timezone="Asia/Shanghai")

        self.assertEqual(result.processed_sources, 4)
        self.assertEqual(sorted(result.user_segments), ["1001", "2002"])

        first = result.user_segments["1001"][0]
        second = result.user_segments["2002"][0]

        self.assertEqual(first.raw_payload["steps"], 120.0)
        self.assertEqual(first.raw_payload["calories"], 50.0)
        self.assertEqual(first.raw_payload["active_minutes"], 1.0)
        self.assertEqual(first.raw_payload["sleep_minutes"], 1.0)

        self.assertEqual(second.raw_payload["steps"], 80.0)
        self.assertEqual(second.raw_payload["calories"], 40.0)
        self.assertEqual(second.raw_payload["active_minutes"], 1.0)
        self.assertEqual(second.raw_payload["sleep_minutes"], 1.0)


if __name__ == "__main__":
    unittest.main()
