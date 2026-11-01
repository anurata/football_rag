# -*- coding: utf-8 -*-
"""
Tests for Layer 1 Accuracy & Layer 2 Stability in Tactical Data.
(tests/test_tactical_data_validation.py)
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.db import DEFAULT_DB_PATH
from pipeline.match_tactical_enricher import DeterministicTacticalEnricher
from scripts.verify_layer1_layer2_tactical import (
    verify_layer1_ground_truth,
    verify_layer2_stability,
)


class TestTacticalDataValidation(unittest.TestCase):
    """Test suite for Layer 1 & Layer 2 validation logic."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.enricher = DeterministicTacticalEnricher(db_path=DEFAULT_DB_PATH)

    def tearDown(self) -> None:
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_single_match_layer1_and_reproducibility(self) -> None:
        """Verify that enricher outputs identical result across runs and conforms to Layer 1 bounds."""
        dir1 = self.temp_dir / "run1"
        dir2 = self.temp_dir / "run2"
        dir1.mkdir()
        dir2.mkdir()

        # Run twice
        self.enricher.enrich_all_matches(output_dir=dir1)
        self.enricher.enrich_all_matches(output_dir=dir2)

        files1 = sorted(list(dir1.glob("*_tactical.json")))
        files2 = sorted(list(dir2.glob("*_tactical.json")))

        self.assertGreater(len(files1), 0, "At least one file must be generated")
        self.assertEqual(len(files1), len(files2), "Both runs should produce identical file counts")

        # Pick a sample match file and compare
        sample_name = files1[0].name
        data1 = json.loads((dir1 / sample_name).read_text(encoding="utf-8"))
        data2 = json.loads((dir2 / sample_name).read_text(encoding="utf-8"))

        # Layer 2 Deterministic Stability check: 100% exact match
        self.assertEqual(data1, data2, "Deterministic enricher must produce 100% identical JSON outputs")

        # Layer 1 Accuracy check on sample
        deep_metrics = data1.get("deep_metrics", {})
        conv = deep_metrics.get("conversion_rates", {})
        h_conv = conv.get("home", {})
        a_conv = conv.get("away", {})

        self.assertGreaterEqual(
            h_conv.get("m30_entries", 0),
            h_conv.get("pa_entries", 0),
            "Home m30_entries must be >= pa_entries",
        )
        self.assertGreaterEqual(
            a_conv.get("m30_entries", 0),
            a_conv.get("pa_entries", 0),
            "Away m30_entries must be >= pa_entries",
        )

        intensity = deep_metrics.get("intensity", {})
        h_dist = intensity.get("home_distance_km")
        a_dist = intensity.get("away_distance_km")
        if h_dist is not None and a_dist is not None:
            self.assertTrue(80.0 <= h_dist <= 140.0, f"Home distance {h_dist} must be within realistic bounds")
            self.assertTrue(80.0 <= a_dist <= 140.0, f"Away distance {a_dist} must be within realistic bounds")


if __name__ == "__main__":
    unittest.main()

