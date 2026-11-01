"""
Unit tests for scripts/plan_phases.py (done 判定ロジック).
"""

import tempfile
import unittest
from pathlib import Path

from pipeline.phase_calculator import PREVIEW_DRAFT, PREVIEW_FINAL, STAGE1, STAGE2
from scripts.plan_phases import build_done_lookup, detect_preview_done


class TestDetectPreviewDone(unittest.TestCase):
    def test_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(detect_preview_done("M1", Path(tmp)), set())

    def test_draft_and_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "M1_preview_auto.md").write_text("x", encoding="utf-8")
            (root / "notebooklm").mkdir()
            (root / "notebooklm" / "M1_export.md").write_text("x", encoding="utf-8")
            self.assertEqual(
                detect_preview_done("M1", root),
                {PREVIEW_DRAFT, PREVIEW_FINAL},
            )

    def test_plain_preview_counts_as_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "M1_preview.md").write_text("x", encoding="utf-8")
            self.assertEqual(detect_preview_done("M1", root), {PREVIEW_DRAFT})


class TestBuildDoneLookup(unittest.TestCase):
    def test_merge_stage_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "M1_preview.md").write_text("x", encoding="utf-8")
            matches = [{"match_id": "M1"}, {"match_id": "M2"}]
            lookup = build_done_lookup(matches, {"M1": 2}, root)
            self.assertEqual(lookup["M1"], {PREVIEW_DRAFT, STAGE1, STAGE2})
            self.assertEqual(lookup["M2"], set())


if __name__ == "__main__":
    unittest.main()

