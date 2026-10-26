"""
Unit tests for knowledge/player_archetypes.json and retriever integration.
"""

import json
import unittest
from pathlib import Path
from agent.retriever import TacticalHybridRetriever

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "player_archetypes.json"


class TestPlayerArchetypesKnowledge(unittest.TestCase):
    """Test suite for validating player archetype and team philosophy dictionaries."""

    def setUp(self):
        self.retriever = TacticalHybridRetriever()

    def test_json_file_validity(self):
        """Verify that player_archetypes.json exists and adheres to schema."""
        self.assertTrue(KNOWLEDGE_PATH.exists())
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("archetypes", data)
        self.assertIn("team_philosophies", data)
        self.assertTrue(len(data["archetypes"]) >= 10)
        self.assertTrue(len(data["team_philosophies"]) >= 3)

    def test_archetype_fields(self):
        """Verify each archetype defines tactical functions, metrics, and synergies."""
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        required_keys = ["archetype_id", "name", "position_group", "description", "tactical_functions", "key_metrics"]
        for arch in data["archetypes"]:
            for k in required_keys:
                self.assertIn(k, arch, f"Missing key {k} in {arch.get('archetype_id')}")

    def test_search_player_archetype_by_role(self):
        """Verify searching archetypes by role name or keyword."""
        # 1. 偽SB
        inverted_sb = self.retriever.search_player_archetype("偽SB")
        self.assertTrue(len(inverted_sb) > 0)
        self.assertEqual(inverted_sb[0]["archetype_id"], "inverted_fullback")

        # 2. 裏抜け
        sprinter = self.retriever.search_player_archetype("裏抜け")
        self.assertTrue(len(sprinter) > 0)
        self.assertEqual(sprinter[0]["archetype_id"], "line_breaker")

        # 3. ポケット侵入
        pocket = self.retriever.search_player_archetype("ポケット侵入")
        self.assertTrue(len(pocket) > 0)
        self.assertEqual(pocket[0]["archetype_id"], "pocket_infiltrator")

    def test_search_team_philosophy(self):
        """Verify searching team philosophies."""
        possession = self.retriever.search_team_philosophy("ポゼッション")
        self.assertTrue(len(possession) > 0)
        self.assertIn("ball_playing_defender", possession[0]["core_archetypes"])


if __name__ == "__main__":
    unittest.main()
