"""Unit tests for scripts/export_all_teams_sheets.py."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.export_all_teams_sheets import export_all_teams


class TestExportAllTeams(unittest.TestCase):
    """Test suite for batch exporting team player spreadsheets."""

    def test_export_subset_teams(self) -> None:
        """Verify batch export for a subset of teams."""
        sample_teams = ["CER", "ZEL"]
        results = export_all_teams(sample_teams)
        self.assertEqual(len(results), 2)

        for res in results:
            self.assertIn(res["team_id"], sample_teams)
            self.assertGreater(res["player_count"], 0)
            self.assertTrue(Path(res["excel_path"]).exists())
            self.assertGreater(len(res["csv_paths"]), 0)


if __name__ == "__main__":
    unittest.main()
