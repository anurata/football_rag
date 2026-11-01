"""Unit tests for live match forecaster."""

import unittest
from scripts.live_match_forecaster import (
    calculate_live_win_probability,
    format_key_player_stats,
    generate_live_forecasting_report,
    main,
    parse_match_status_text,
    poisson_prob,
    predict_tactical_substitutions,
)


class TestLiveMatchForecaster(unittest.TestCase):
    """Test suite for in-match live forecasting logic."""

    def test_parse_match_status_text(self) -> None:
        """Tests parsing of various match status strings."""
        stage, minute = parse_match_status_text("試合前")
        self.assertEqual(stage, "BEFORE")
        self.assertEqual(minute, 0)

        stage, minute = parse_match_status_text("前半15分")
        self.assertEqual(stage, "1ST_HALF")
        self.assertEqual(minute, 15)

        stage, minute = parse_match_status_text("ハーフタイム")
        self.assertEqual(stage, "HT")
        self.assertEqual(minute, 45)

        stage, minute = parse_match_status_text("前半終了")
        self.assertEqual(stage, "HT")
        self.assertEqual(minute, 45)

        stage, minute = parse_match_status_text("後半20分")
        self.assertEqual(stage, "2ND_HALF")
        self.assertEqual(minute, 65)

        stage, minute = parse_match_status_text("試合終了")
        self.assertEqual(stage, "END")
        self.assertEqual(minute, 90)

    def test_poisson_prob(self) -> None:
        """Tests Poisson calculation."""
        p_zero = poisson_prob(0, 0.0)
        self.assertAlmostEqual(p_zero, 1.0, places=4)

        p1 = poisson_prob(1, 1.0)
        p0 = poisson_prob(0, 1.0)
        self.assertAlmostEqual(p1, p0, places=4)

    def test_calculate_live_win_probability_initial(self) -> None:
        """Tests initial win probabilities at 0 minutes."""
        probs = calculate_live_win_probability(0, 0, 0)
        total = (
            probs["home_win_prob"]
            + probs["draw_prob"]
            + probs["away_win_prob"]
        )
        self.assertAlmostEqual(total, 100.0, delta=1.0)
        self.assertGreater(probs["away_win_prob"], probs["home_win_prob"])

    def test_calculate_live_win_probability_late_game(self) -> None:
        """Tests win probabilities when away team is leading at 85 min."""
        probs = calculate_live_win_probability(85, 0, 1)
        self.assertGreater(probs["away_win_prob"], 80.0)

    def test_predict_tactical_substitutions_early(self) -> None:
        """Tests that no tactical subs are recommended too early."""
        subs = predict_tactical_substitutions(15, 0)
        self.assertEqual(len(subs["okayama_subs"]), 0)
        self.assertEqual(len(subs["fctokyo_subs"]), 0)

    def test_predict_tactical_substitutions_late_trailing(self) -> None:
        """Tests substitution recommendations when Tokyo is trailing at 60 min."""
        subs = predict_tactical_substitutions(60, 1)  # score_diff = 1 (Tokyo trailing)
        self.assertGreater(len(subs["fctokyo_subs"]), 0)

    def test_generate_live_forecasting_report(self) -> None:
        """Tests report string formatting."""
        mock_state = {
            "game_id": "2026103109",
            "home_team": "ファジアーノ岡山",
            "away_team": "FC東京",
            "stage": "1ST_HALF",
            "minute": 20,
            "raw_status": "前半20分",
            "home_score": 0,
            "away_score": 0,
            "recent_events": ["前半10分 FC東京 シュートを放つもGKがセーブ"],
            "timestamp": "LIVE",
        }
        report = generate_live_forecasting_report(mock_state)
        self.assertIn("ライブ戦況", report)
        self.assertIn("ファジアーノ岡山", report)
        self.assertIn("FC東京", report)
        self.assertIn("リアルタイム勝率", report)
        self.assertIn("直近のピッチ速報", report)

    def test_main_cli_execution(self) -> None:
        """Tests main CLI execution with simulated fallback."""
        ret = main(["--game-id", "9999999999", "--hashtag", "#testclub", "--json"])
        self.assertEqual(ret, 0)

    def test_format_key_player_stats(self) -> None:
        """Tests filtering and formatting of player stats from SPAIA."""
        mock_raw = [
            {
                "NameS": "永野",
                "HV": 2,
                "Pos": "MF",
                "PassCount": "41",
                "PassRate": "90.2",
                "OpponentAreaPassCount": "24",
                "OpponentAreaPassRate": "91.7",
                "Shoot": "1",
                "ShootOnTarget": "1",
                "Score": "0",
                "ClearCount": "2",
                "TackleCount": "1",
            },
            {
                "NameS": "テスト外選手",
                "HV": 1,
                "Pos": "DF",
            },
        ]
        res = format_key_player_stats(mock_raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "永野")
        self.assertEqual(res[0]["pass_count"], 41)
        self.assertEqual(res[0]["clear_count"], 2)


if __name__ == "__main__":
    unittest.main()
