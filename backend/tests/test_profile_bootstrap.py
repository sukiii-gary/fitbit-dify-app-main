from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.profile_bootstrap_service import build_fitabase_profile_seed


class ProfileBootstrapTest(unittest.TestCase):
    def test_build_fitabase_profile_seed_generates_goals_and_baselines(self) -> None:
        base = datetime(2016, 4, 12, 8, 0, 0)
        segments = [
            SimpleNamespace(
                segment_start=base,
                segment_end=base + timedelta(hours=1),
                raw_payload_json={
                    "steps": 800,
                    "calories": 90,
                    "sleep_minutes": 0,
                    "active_minutes": 25,
                    "sedentary_minutes": 35,
                    "heart_rate_series": [60, 62, 64],
                },
            ),
            SimpleNamespace(
                segment_start=base + timedelta(hours=1),
                segment_end=base + timedelta(hours=2),
                raw_payload_json={
                    "steps": 400,
                    "calories": 70,
                    "sleep_minutes": 0,
                    "active_minutes": 15,
                    "sedentary_minutes": 45,
                    "heart_rate_series": [58, 59, 61],
                },
            ),
            SimpleNamespace(
                segment_start=base + timedelta(days=1),
                segment_end=base + timedelta(days=1, hours=1),
                raw_payload_json={
                    "steps": 200,
                    "calories": 60,
                    "sleep_minutes": 420,
                    "active_minutes": 5,
                    "sedentary_minutes": 15,
                    "heart_rate_series": [],
                },
            ),
        ]

        seed = build_fitabase_profile_seed(segments=segments, external_user_id="fitabase_1001")

        self.assertEqual(seed.profile["source"], "fitabase_merged")
        self.assertEqual(seed.profile["source_user_id"], "1001")
        self.assertIn(seed.profile["activity_level"], {"sedentary", "lightly_active", "moderately_active", "highly_active"})
        self.assertIn("daily_steps_goal", seed.goals)
        self.assertIn("sleep_goal_hours", seed.goals)
        self.assertIn("fatigue_high_threshold", seed.thresholds)
        self.assertIn("avg_daily_steps", seed.baseline_stats)
        self.assertTrue(seed.system_prompt_prefix)


if __name__ == "__main__":
    unittest.main()
