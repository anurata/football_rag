# -*- coding: utf-8 -*-
"""
Tests for Step 3 Preview Generation & Live Match Integration.
(tests/test_step3_preview_and_live_integration.py)
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pipeline.preview_curation_service import PreviewCurationService
from scripts import live_match_forecaster


class TestStep3PreviewAndLiveIntegration(unittest.TestCase):
    """Integration and validation tests for Step 3: Preview generation and live match forecasting."""

    def setUp(self) -> None:
        self.preview_service = PreviewCurationService()

    def test_preview_curation_workspace_generation_real_data(self) -> None:
        """Verify PreviewCurationService generates valid workspace for OKA vs FCT MW13."""
        workspace = self.preview_service.generate_curation_workspace(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )

        self.assertIn("facts", workspace)
        self.assertIn("branches", workspace)

        facts = workspace["facts"]
        self.assertIn("basic_info", facts)
        self.assertIn("home_team", facts)
        self.assertIn("away_team", facts)
        self.assertEqual(facts["basic_info"]["matchweek"], 13)

        branches = workspace["branches"]
        branch_ids = [b["branch_id"] for b in branches]
        self.assertIn("lineup_home", branch_ids)
        self.assertIn("lineup_away", branch_ids)
        self.assertIn("tactical_scenario", branch_ids)
        self.assertIn("matchup_focus", branch_ids)

        for branch in branches:
            self.assertTrue(len(branch["options"]) >= 2)
            for opt in branch["options"]:
                self.assertIn("fact_basis", opt)
                self.assertIn("inference", opt)
                self.assertTrue(opt["fact_basis"].startswith("【事実】"))
                self.assertTrue(opt["inference"].startswith("【推測】"))

    def test_preview_curation_markdown_build(self) -> None:
        """Verify curated preview markdown can be compiled with branch selections."""
        workspace = self.preview_service.generate_curation_workspace(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )
        facts = workspace["facts"]
        branches = workspace["branches"]

        selections = {}
        for b in branches:
            opt = b["options"][0]
            selections[b["title"]] = (
                f"**選択案 [{opt['option_id']}] {opt['label']}**\n"
                f"- {opt['fact_basis']}\n"
                f"- {opt['inference']}"
            )

        user_note = "FC東京のハイプレスと岡山のブロック守備の攻防が焦点。"
        md_content = self.preview_service.compile_curated_report(
            facts=facts,
            selections=selections,
            custom_insights=user_note,
        )

        self.assertIn("第13節 プレビューレポート", md_content)
        self.assertIn("ファジアーノ岡山", md_content)
        self.assertIn("FC東京", md_content)
        self.assertIn("Curated Focus", md_content)
        self.assertIn(user_note, md_content)

    def test_live_forecaster_mock_in_match_prediction(self) -> None:
        """Verify live forecaster correctly calculates dynamic probability in-match."""
        mock_raw_state = {
            "game_id": "2026103109",
            "home_team": "ファジアーノ岡山",
            "away_team": "FC東京",
            "stage": "2ND_HALF",
            "minute": 65,
            "raw_status": "後半20分",
            "home_score": 0,
            "away_score": 2,
            "scorers": ["仲川 輝人 前 49'", "仲川 輝人 後 2'"],
            "recent_events": ["後半2分 FC東京 仲川が追加点"],
            "key_player_stats": [
                {
                    "name": "仲川",
                    "team": "FC東京",
                    "pos": "FW",
                    "score": 2,
                    "shoot": 2,
                    "shoot_on_target": 2,
                    "pass_count": 15,
                    "pass_rate": 80.0,
                    "opp_pass_count": 10,
                    "opp_pass_rate": 75.0,
                    "clear_count": 0,
                    "tackle_count": 1,
                },
            ],
            "social_buzz": [],
            "timestamp": "LIVE",
        }

        with patch("scripts.live_match_forecaster.fetch_live_match_state", return_value=mock_raw_state):
            state = live_match_forecaster.fetch_live_match_state("2026103109")
            self.assertEqual(state["stage"], "2ND_HALF")
            self.assertEqual(state["home_score"], 0)
            self.assertEqual(state["away_score"], 2)

            probs = live_match_forecaster.calculate_live_win_probability(
                minute=state["minute"],
                home_score=state["home_score"],
                away_score=state["away_score"],
                home_team="ファジアーノ岡山",
                away_team="FC東京",
            )
            prob_sum = probs["home_win_prob"] + probs["draw_prob"] + probs["away_win_prob"]
            self.assertAlmostEqual(prob_sum, 100.0, places=1)
            self.assertGreater(probs["away_win_prob"], 80.0)

            score_diff = state["home_score"] - state["away_score"]
            subs = live_match_forecaster.predict_tactical_substitutions(
                minute=state["minute"],
                score_diff=score_diff,
            )
            self.assertIn("okayama_subs", subs)
            self.assertIn("fctokyo_subs", subs)
            self.assertTrue(len(subs["okayama_subs"]) > 0 or len(subs["fctokyo_subs"]) > 0)

    def test_live_forecaster_real_match_state(self) -> None:
        """Verify live forecaster retrieves real match state for Game ID 2026103109."""
        state = live_match_forecaster.fetch_live_match_state("2026103109")
        self.assertEqual(state["game_id"], "2026103109")
        self.assertEqual(state["home_team"], "ファジアーノ岡山")
        self.assertEqual(state["away_team"], "FC東京")
        self.assertIn(state["stage"], ["BEFORE", "1ST_HALF", "HT", "2ND_HALF", "END"])
        self.assertIsInstance(state["home_score"], int)
        self.assertIsInstance(state["away_score"], int)
        self.assertTrue(len(state["key_player_stats"]) > 0)

    def test_dry_fact_guardrail_enforcement(self) -> None:
        """Verify forbidden subjective terms are detected and scrubbed."""
        hallucinated_text = "仲川が神がかったドリブルで抜群の落ち着きを見せて冷静に流し込んだ。"
        found = live_match_forecaster.detect_subjective_hallucinations(hallucinated_text)
        self.assertIn("神がかった", found)
        self.assertIn("抜群の落ち着き", found)
        self.assertIn("冷静に流し込", found)

        cleaned_text = live_match_forecaster.enforce_dry_fact_policy(hallucinated_text)
        for forbidden in found:
            self.assertNotIn(forbidden, cleaned_text)

    def test_injury_roster_integrity_and_exclusion_of_transferred_players(self) -> None:
        """Verify transferred players (Araki, Koizumi, Trevisan) and active players (Nakagawa) are excluded."""
        workspace = self.preview_service.generate_curation_workspace(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )
        away_injuries = workspace["facts"]["away_team"].get("injuries", [])
        away_injury_names = [inj.get("player_name") for inj in away_injuries]

        # 移籍・退団選手および現役主力が出場不能負傷者欄に絶対に含まれないこと
        self.assertNotIn("荒木 遼太郎", away_injury_names)
        self.assertNotIn("小泉 慶", away_injury_names)
        self.assertNotIn("エンリケ トレヴィザン", away_injury_names)
        self.assertNotIn("仲川 輝人", away_injury_names)

        # 実在する現行離脱者（室屋、本間など）が含まれ、すべて status が OUT であること
        self.assertIn("室屋 成", away_injury_names)
        self.assertIn("本間 至恩", away_injury_names)
        for inj in away_injuries:
            self.assertEqual(inj.get("status"), "OUT")


if __name__ == "__main__":
    unittest.main()
