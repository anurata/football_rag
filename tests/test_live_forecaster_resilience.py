"""Resilience and fault-tolerance unit tests for live match forecaster."""

import unittest
from unittest.mock import MagicMock, patch
import requests

from scripts.live_match_forecaster import (
    _build_fallback_state,
    calculate_live_win_probability,
    fetch_live_match_state,
    fetch_realtime_x_buzz,
    fetch_recent_text_events,
    fetch_spaia_live_player_stats,
    format_key_player_stats,
    generate_live_forecasting_report,
    predict_tactical_substitutions,
)


class TestLiveForecasterResilience(unittest.TestCase):
    """Test suite for error handling, network drops, and malformed inputs."""

    def test_full_failure_fallback(self) -> None:
        """Tests complete network drop returns safe fallback and valid report."""
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Offline")):
            state = fetch_live_match_state("9999999999")
            self.assertEqual(state["timestamp"], "FALLBACK")
            self.assertIn("Offline", state["raw_status"])
            self.assertEqual(state["home_score"], 0)
            self.assertEqual(state["away_score"], 0)

            # Ensure report generation does not raise exceptions
            report = generate_live_forecasting_report(state)
            self.assertIn("ライブ戦況", report)
            self.assertIn("ファジアーノ岡山", report)

    def test_spaia_api_down(self) -> None:
        """Tests that SPAIA API failure does not break the entire pipeline."""
        with patch("requests.get", side_effect=requests.exceptions.Timeout("SPAIA Timeout")):
            stats = fetch_spaia_live_player_stats("2026103109")
            self.assertEqual(stats, [])
            formatted = format_key_player_stats(stats)
            self.assertEqual(formatted, [])

    def test_x_buzz_failure(self) -> None:
        """Tests that X search failure returns empty list safely."""
        with patch("requests.get", side_effect=requests.exceptions.HTTPError("Rate Limited")):
            buzz = fetch_realtime_x_buzz("#fctokyo")
            self.assertEqual(buzz, [])

    def test_recent_text_events_404(self) -> None:
        """Tests that 404 response on text live returns empty list safely."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("requests.get", return_value=mock_resp):
            events = fetch_recent_text_events("invalid_game_id")
            self.assertEqual(events, [])

    def test_malformed_scoreboard_html(self) -> None:
        """Tests handling of completely empty or unexpected HTML body."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><div>No scoreboard here</div></body></html>"
        with patch("requests.get", return_value=mock_resp):
            state = fetch_live_match_state("2026103109")
            self.assertEqual(state["timestamp"], "FALLBACK")
            self.assertEqual(state["raw_status"], "SCOREBOARD_NOT_FOUND")

    def test_extreme_minutes_and_scores(self) -> None:
        """Tests extreme values (e.g. 120 minutes, 15-0 score) do not crash calculation."""
        probs = calculate_live_win_probability(
            minute=120,
            home_score=15,
            away_score=0,
        )
        self.assertEqual(probs["home_win_prob"], 100.0)
        self.assertEqual(probs["away_win_prob"], 0.0)
        self.assertEqual(probs["remaining_home_xg"], 0.0)

        subs = predict_tactical_substitutions(
            minute=95,
            score_diff=15,
        )
        self.assertIsInstance(subs["okayama_subs"], list)
        self.assertIsInstance(subs["fctokyo_subs"], list)

    def test_partial_degradation_report(self) -> None:
        """Tests report rendering when player stats and social buzz are empty."""
        partial_state = {
            "game_id": "2026103109",
            "home_team": "ファジアーノ岡山",
            "away_team": "FC東京",
            "stage": "2ND_HALF",
            "minute": 70,
            "raw_status": "後半25分",
            "home_score": 0,
            "away_score": 1,
            "scorers": ["仲川 輝人 前 49'"],
            "recent_events": [],
            "key_player_stats": [],
            "social_buzz": [],
            "timestamp": "LIVE",
        }
        report = generate_live_forecasting_report(partial_state)
        self.assertIn("後半25分", report)
        self.assertNotIn("ピッチ上のキーマン個人スタッツ", report)
        self.assertNotIn("X(Twitter) サポーターのリアルタイム反響", report)
        self.assertIn("リアルタイム勝率", report)


if __name__ == "__main__":
    unittest.main()

