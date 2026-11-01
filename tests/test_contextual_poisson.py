"""Unit tests for empirical contextual Poisson live probability engine.

Verifies that empirical team comeback resilience, closing power, home advantage,
2nd half goal timing, and bench impact are properly reflected in dynamic in-match win probabilities.
"""

import unittest
from unittest.mock import patch
from scripts.live_match_forecaster import (
    calculate_live_win_probability,
    DEFAULT_HOME_ADVANTAGE,
    TEAM_TACTICAL_PROFILES,
)


class TestContextualPoisson(unittest.TestCase):
    """Test suite for empirical and game-state adjusted Poisson model."""

    def test_halftime_trailing_with_home_advantage(self) -> None:
        """Tests that at HT (0-1), trailing home team gets empirical resilience & home advantage."""
        probs = calculate_live_win_probability(
            minute=45,
            home_score=0,
            away_score=1,
            home_team="ファジアーノ岡山",
            away_team="FC東京",
            home_advantage=DEFAULT_HOME_ADVANTAGE,
        )
        # Verify home win prob is in realistic range (~7.5% - 11.0%)
        self.assertGreater(probs["home_win_prob"], 7.0)
        self.assertLess(probs["home_win_prob"], 12.0)
        self.assertGreater(probs["draw_prob"], 18.0)

        # FC Tokyo closing power (72.7%) keeps away win chance solid (>65%)
        self.assertGreater(probs["away_win_prob"], 65.0)

    def test_empirical_home_advantage_impact(self) -> None:
        """Tests that empirical home advantage (1.19x) boosts home team win probability."""
        probs_with_adv = calculate_live_win_probability(
            minute=0,
            home_score=0,
            away_score=0,
            home_advantage=1.19,
        )
        probs_neutral = calculate_live_win_probability(
            minute=0,
            home_score=0,
            away_score=0,
            home_advantage=1.00,
        )
        self.assertGreater(
            probs_with_adv["home_win_prob"],
            probs_neutral["home_win_prob"],
        )

    def test_resilient_team_comeback_difference(self) -> None:
        """Tests that a team with high empirical resilience (Machida: 0.667) has higher comeback chances than Okayama."""
        probs_machida = calculate_live_win_probability(
            minute=45,
            home_score=0,
            away_score=1,
            home_team="町田",
            away_team="FC東京",
        )
        probs_okayama = calculate_live_win_probability(
            minute=45,
            home_score=0,
            away_score=1,
            home_team="岡山",
            away_team="FC東京",
        )
        # Machida's comeback resilience (0.667) produces higher comeback chance than Okayama (0.12)
        self.assertGreater(
            probs_machida["home_win_prob"],
            probs_okayama["home_win_prob"],
        )
        self.assertGreater(
            probs_machida["draw_prob"],
            probs_okayama["draw_prob"],
        )

    def test_closing_power_suppression(self) -> None:
        """Tests that a team with higher closing power reduces opponent comeback chances."""
        probs_fct = calculate_live_win_probability(
            minute=60,
            home_score=0,
            away_score=1,
            home_team="ファジアーノ岡山",
            away_team="FC東京",
        )

        with patch.dict(
            TEAM_TACTICAL_PROFILES,
            {"FragileTeam": {"closing_power": 0.45, "comeback_resilience": 0.20, "second_half_ratio": 0.50, "bench_impact": 1.0}},
        ):
            probs_fragile = calculate_live_win_probability(
                minute=60,
                home_score=0,
                away_score=1,
                home_team="ファジアーノ岡山",
                away_team="FragileTeam",
            )
            self.assertGreater(probs_fragile["home_win_prob"], probs_fct["home_win_prob"])
            self.assertGreater(probs_fragile["draw_prob"], probs_fct["draw_prob"])

    def test_two_goal_lead_closing(self) -> None:
        """Tests win probability when leading by 2 goals in 2nd half (0-2 at 50 min)."""
        probs = calculate_live_win_probability(
            minute=50,
            home_score=0,
            away_score=2,
            home_team="ファジアーノ岡山",
            away_team="FC東京",
        )
        self.assertGreater(probs["away_win_prob"], 84.0)
        self.assertLess(probs["home_win_prob"], 5.0)


if __name__ == "__main__":
    unittest.main()
