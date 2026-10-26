"""
Unit tests for config/entity_master.json integrity and alias lookup.
"""

import json
import os
import unittest


class TestEntityMaster(unittest.TestCase):
    """Verify entity master structure, team aliases, and uniqueness."""

    @classmethod
    def setUpClass(cls):
        config_path = os.path.join("config", "entity_master.json")
        with open(config_path, "r", encoding="utf-8") as f:
            cls.data = json.load(f)

    def test_teams_present(self):
        """Ensure teams list is present and contains J1 teams."""
        teams = self.data.get("teams", [])
        self.assertGreaterEqual(len(teams), 20)

    def test_team_ids_unique(self):
        """Ensure team_id values are unique."""
        team_ids = [t["team_id"] for t in self.data["teams"]]
        self.assertEqual(len(team_ids), len(set(team_ids)))

    def test_team_required_fields(self):
        """Ensure each team entry has all necessary fields."""
        required_fields = [
            "team_id",
            "canonical_name",
            "short_name",
            "jleague_name",
            "football_lab_slug",
            "aliases",
        ]
        for team in self.data["teams"]:
            for field in required_fields:
                self.assertIn(field, team, f"Missing {field} in {team.get('team_id')}")
                self.assertTrue(team[field], f"Empty {field} in {team.get('team_id')}")

    def test_fctokyo_aliases(self):
        """Verify aliases for FC Tokyo can resolve various notations."""
        team = next(t for t in self.data["teams"] if t["team_id"] == "FCT")
        aliases = team["aliases"]
        self.assertIn("FC東京", aliases)
        self.assertIn("ＦＣ東京", aliases)
        self.assertIn("FC Tokyo", aliases)

    def test_kashima_aliases(self):
        """Verify aliases for Kashima Antlers."""
        team = next(t for t in self.data["teams"] if t["team_id"] == "KAS")
        aliases = team["aliases"]
        self.assertIn("鹿島アントラーズ", aliases)
        self.assertIn("鹿島", aliases)

    def test_mito_presence(self):
        """Verify Mito Hollyhock is included for test dataset compatibility."""
        team = next((t for t in self.data["teams"] if t["team_id"] == "MIT"), None)
        self.assertIsNotNone(team)


if __name__ == "__main__":
    unittest.main()
