"""
Unit tests for pipeline.phase_calculator.
"""

import unittest
from datetime import datetime, timedelta

from pipeline.phase_calculator import (
    JST,
    PREVIEW_DRAFT,
    PREVIEW_FINAL,
    STAGE1,
    STAGE2,
    compute_phase_schedule,
    done_phases_from_stage,
    parse_kickoff,
    pending_phases,
    plan_matches,
)

KO = datetime(2026, 10, 31, 14, 0, tzinfo=JST)


class TestParseKickoff(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_kickoff("2026-10-31", "14:00"), KO)

    def test_invalid_time(self):
        self.assertIsNone(parse_kickoff("2026-10-31", ""))

    def test_invalid_date(self):
        self.assertIsNone(parse_kickoff("bad", "14:00"))


class TestSchedule(unittest.TestCase):
    def test_offsets(self):
        s = compute_phase_schedule(KO)
        self.assertEqual(s[PREVIEW_DRAFT], KO - timedelta(hours=72))
        self.assertEqual(s[PREVIEW_FINAL], KO - timedelta(hours=24))
        self.assertEqual(s[STAGE1], KO + timedelta(hours=3))
        self.assertEqual(s[STAGE2], KO + timedelta(hours=36))

    def test_weekday_night_kickoff(self):
        ko = datetime(2026, 11, 4, 19, 0, tzinfo=JST)
        s = compute_phase_schedule(ko)
        self.assertEqual(s[STAGE1], datetime(2026, 11, 4, 22, 0, tzinfo=JST))


class TestPendingPhases(unittest.TestCase):
    def test_too_early(self):
        now = KO - timedelta(hours=100)
        self.assertEqual(pending_phases(KO, now, set()), [])

    def test_draft_window(self):
        now = KO - timedelta(hours=60)
        self.assertEqual(pending_phases(KO, now, set()), [PREVIEW_DRAFT])

    def test_draft_done(self):
        now = KO - timedelta(hours=60)
        self.assertEqual(pending_phases(KO, now, {PREVIEW_DRAFT}), [])

    def test_catch_up_both_previews(self):
        now = KO - timedelta(hours=10)
        self.assertEqual(
            pending_phases(KO, now, set()),
            [PREVIEW_DRAFT, PREVIEW_FINAL],
        )

    def test_during_match_nothing(self):
        now = KO + timedelta(hours=1)
        self.assertEqual(pending_phases(KO, now, set()), [])

    def test_after_kickoff_skips_preview(self):
        now = KO + timedelta(hours=4)
        self.assertEqual(pending_phases(KO, now, set()), [STAGE1])

    def test_stage2_catch_up_after_long_delay(self):
        now = KO + timedelta(hours=100)
        self.assertEqual(pending_phases(KO, now, set()), [STAGE1, STAGE2])

    def test_stage2_only(self):
        now = KO + timedelta(hours=40)
        self.assertEqual(pending_phases(KO, now, {STAGE1}), [STAGE2])

    def test_all_done(self):
        now = KO + timedelta(hours=100)
        self.assertEqual(pending_phases(KO, now, {STAGE1, STAGE2}), [])

    def test_exact_boundary(self):
        now = KO + timedelta(hours=3)
        self.assertEqual(pending_phases(KO, now, set()), [STAGE1])


class TestDonePhasesFromStage(unittest.TestCase):
    def test_values(self):
        self.assertEqual(done_phases_from_stage(None), set())
        self.assertEqual(done_phases_from_stage(0), set())
        self.assertEqual(done_phases_from_stage(1), {STAGE1})
        self.assertEqual(done_phases_from_stage(2), {STAGE1, STAGE2})


class TestPlanMatches(unittest.TestCase):
    def test_plan(self):
        matches = [
            {"match_id": "A", "matchweek": 38, "date": "2026-10-31", "time": "14:00"},
            {"match_id": "B", "matchweek": 38, "date": "2026-10-31", "time": "bad"},
            {"match_id": "C", "matchweek": 38, "date": "2026-12-01", "time": "14:00"},
        ]
        now = KO + timedelta(hours=4)
        plan = plan_matches(matches, now, {"A": set()})
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["match_id"], "A")
        self.assertEqual(plan[0]["phases"], [STAGE1])

    def test_done_lookup(self):
        matches = [
            {"match_id": "A", "matchweek": 38, "date": "2026-10-31", "time": "14:00"},
        ]
        now = KO + timedelta(hours=4)
        self.assertEqual(plan_matches(matches, now, {"A": {STAGE1}}), [])


if __name__ == "__main__":
    unittest.main()

