"""
Unit tests for tactical knowledge YAML dictionaries.
Validates syntax, schema conformity, and content requirements.
"""

import unittest
from pathlib import Path
import yaml


class TestTacticalKnowledge(unittest.TestCase):
    """Test suite for knowledge/*.yaml tactical domain dictionaries."""

    def setUp(self):
        self.base_dir = Path(__file__).resolve().parent.parent / "knowledge"

    def _load_yaml(self, filename: str) -> dict:
        """Helper to load and parse a YAML file."""
        file_path = self.base_dir / filename
        self.assertTrue(file_path.exists(), f"File {filename} does not exist in {self.base_dir}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIsInstance(data, dict, f"{filename} root must be a dictionary")
        return data

    def test_metric_causal_trees_schema(self):
        """Verify metric_causal_trees.yaml format and required fields."""
        data = self._load_yaml("metric_causal_trees.yaml")
        self.assertIn("trees", data)
        trees = data["trees"]
        self.assertIsInstance(trees, list)
        self.assertGreaterEqual(len(trees), 4, "Must define at least 4 metric trees")

        for tree in trees:
            self._validate_metric_tree_item(tree)

    def _validate_metric_tree_item(self, tree: dict) -> None:
        """Validate individual metric tree item."""
        self.assertIn("metric_id", tree)
        self.assertIn("metric_name", tree)
        self.assertIn("phenomenon", tree)
        self.assertIn("hypotheses", tree)
        hypotheses = tree["hypotheses"]
        self.assertIsInstance(hypotheses, list)
        self.assertGreaterEqual(len(hypotheses), 3, "Each tree must define at least 3 hypotheses")

        for h in hypotheses:
            self.assertIn("hypothesis_id", h)
            self.assertIn("name", h)
            self.assertIn("description", h)
            self.assertIn("verification_metrics", h)
            self.assertIsInstance(h["verification_metrics"], list)

    def test_tactical_tradeoffs_schema(self):
        """Verify tactical_tradeoffs.yaml format and required fields."""
        data = self._load_yaml("tactical_tradeoffs.yaml")
        self.assertIn("tradeoffs", data)
        tradeoffs = data["tradeoffs"]
        self.assertIsInstance(tradeoffs, list)
        self.assertGreaterEqual(len(tradeoffs), 4, "Must define at least 4 tradeoffs")

        for t in tradeoffs:
            self._validate_tradeoff_item(t)

    def _validate_tradeoff_item(self, t: dict) -> None:
        """Validate individual tradeoff item."""
        self.assertIn("tactic_id", t)
        self.assertIn("tactic_name", t)
        self.assertIn("category", t)
        self.assertIn("core_mechanism", t)
        self.assertIn("main_effects", t)
        self.assertIn("side_effects", t)
        self.assertIn("vulnerability_conditions", t)
        self.assertIn("countermeasures", t)

        self.assertGreaterEqual(len(t["main_effects"]), 1)
        self.assertGreaterEqual(len(t["side_effects"]), 1)

    def test_system_matrix_schema(self):
        """Verify system_matrix.yaml format and required fields."""
        data = self._load_yaml("system_matrix.yaml")
        self.assertIn("matchups", data)
        matchups = data["matchups"]
        self.assertIsInstance(matchups, list)
        self.assertGreaterEqual(len(matchups), 4, "Must define at least 4 matchups")

        for m in matchups:
            self._validate_matchup_item(m)

    def _validate_matchup_item(self, m: dict) -> None:
        """Validate individual formation matchup item."""
        self.assertIn("matchup_id", m)
        self.assertIn("home_formation", m)
        self.assertIn("away_formation", m)
        self.assertIn("structural_advantages_for_home", m)
        self.assertIn("structural_advantages_for_away", m)
        self.assertIn("pinning_mechanisms", m)
        self.assertIn("half_space_dynamics", m)
        self.assertIn("sliding_and_shift_triggers", m)
        self.assertIn("watching_perspective_guide", m)


if __name__ == "__main__":
    unittest.main()
