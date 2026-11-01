"""Unit tests for dry-fact policy and subjective hallucination guardrail."""

import unittest
from scripts.live_match_forecaster import (
    detect_subjective_hallucinations,
    enforce_dry_fact_policy,
    generate_live_forecasting_report,
    main,
)


class TestFactualGuardrail(unittest.TestCase):
    """Test suite for strict factual integrity and anti-hallucination guardrail."""

    def test_detect_subjective_hallucinations(self) -> None:
        """Tests that unobserved subjective adjectives are correctly detected."""
        hallucinated_text = "岡山のプレスをいなし、ズバッと通した神がかったラストパスから冷静に流し込んだ。"
        found = detect_subjective_hallucinations(hallucinated_text)
        self.assertIn("いなし", found)
        self.assertIn("ズバッと", found)
        self.assertIn("神がかった", found)
        self.assertIn("冷静に流し込", found)

    def test_detect_clean_factual_text(self) -> None:
        """Tests that pure factual text contains no subjective embellishments."""
        clean_text = "ペナルティエリア中央から右足でゴール右下に決める。"
        found = detect_subjective_hallucinations(clean_text)
        self.assertEqual(len(found), 0)

    def test_enforce_dry_fact_policy(self) -> None:
        """Tests that subjective words are removed cleanly."""
        text = "神がかった 縦パスを ズバッと 送る"
        cleaned = enforce_dry_fact_policy(text)
        self.assertNotIn("神がかった", cleaned)
        self.assertNotIn("ズバッと", cleaned)
        self.assertEqual(cleaned, "縦パスを 送る")

    def test_generate_report_dry_fact_mode(self) -> None:
        """Tests report output under strict dry-fact mode."""
        mock_state = {
            "game_id": "2026103109",
            "home_team": "ファジアーノ岡山",
            "away_team": "FC東京",
            "stage": "2ND_HALF",
            "minute": 63,
            "raw_status": "後半18分",
            "home_score": 0,
            "away_score": 3,
            "scorers": ["ダニ ゴメス 後 18'"],
            "recent_events": ["神がかったパスから冷静に流し込んだゴール"],
            "key_player_stats": [],
            "social_buzz": ["電光石火の追加点"],
            "timestamp": "LIVE",
        }
        report = generate_live_forecasting_report(mock_state, dry_fact=True)
        self.assertIn("DRY FACT", report)
        self.assertIn("【※状況推測】", report)
        self.assertNotIn("神がかった", report)
        self.assertNotIn("冷静に流し込", report)
        self.assertNotIn("電光石火", report)

    def test_cli_dry_fact_execution(self) -> None:
        """Tests running main CLI with --dry-fact flag."""
        ret = main(["--game-id", "9999999999", "--dry-fact"])
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()

