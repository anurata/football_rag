"""tests/test_team_analytics_engine.py

pipeline/team_analytics_engine.py の単体テスト (unittest)。
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.team_analytics_engine import (
    compute_all_teams_clusters,
    get_goal_pattern_breakdown,
    get_style_adherence_matches,
    get_team_55_metrics_categorized,
    get_team_h2h_comparison,
    get_team_signature_metrics,
    get_team_squad_cbp,
    get_win_loss_pattern_analysis,
    load_all_matches_scores_map,
    load_all_teams_55_metrics,
)


class TestTeamAnalyticsEngine(unittest.TestCase):
    """Test suite for team_analytics_engine module."""

    def test_load_all_teams_55_metrics(self):
        """全20クラブの55指標サマリーがロードできること."""
        metrics = load_all_teams_55_metrics()
        self.assertEqual(len(metrics), 20)
        self.assertIn("FCT", metrics)
        self.assertGreaterEqual(len(metrics["FCT"]), 10)

    def test_load_all_matches_scores_map(self):
        """全試合スコアマップが取得できること."""
        scores = load_all_matches_scores_map()
        self.assertGreater(len(scores), 0)
        sample = scores.get("20260808_FCT_ZEL")
        self.assertIsNotNone(sample)
        self.assertEqual(sample["home_team_id"], "FCT")
        self.assertEqual(sample["away_team_id"], "ZEL")
        self.assertEqual(sample["score_str"], "1-5")

    def test_compute_all_teams_clusters(self):
        """動的クラスタ分析と戦術スタイルラベリングの検証."""
        res = compute_all_teams_clusters()
        self.assertIn("clusters", res)
        self.assertIn("team_profiles", res)

        clusters = res["clusters"]
        self.assertEqual(len(clusters), 4)

        team_profiles = res["team_profiles"]
        self.assertIn("FCT", team_profiles)
        fct_prof = team_profiles["FCT"]
        self.assertIn("style_label", fct_prof)
        self.assertIn("style_description", fct_prof)
        self.assertIn("radar_scores", fct_prof)

        radar = fct_prof["radar_scores"]
        expected_keys = [
            "ポゼッション支配力",
            "前進・推進突破力",
            "ハイプレス即時奪取",
            "フィジカル・走力強度",
            "ゴール期待創出度",
        ]
        for k in expected_keys:
            self.assertIn(k, radar)
            self.assertGreaterEqual(radar[k], 0.0)
            self.assertLessEqual(radar[k], 100.0)

    def test_get_team_signature_metrics(self):
        """シグネチャー指標（強み Top 3 & 課題 Bottom 3）の検証."""
        sig = get_team_signature_metrics("FCT")
        top_strengths = sig.get("top_strengths", [])
        bottom_weaknesses = sig.get("bottom_weaknesses", [])

        self.assertEqual(len(top_strengths), 3)
        self.assertEqual(len(bottom_weaknesses), 3)

        for item in top_strengths:
            self.assertIn("metric_name", item)
            self.assertIn("team_value", item)
            self.assertIn("league_average", item)
            self.assertIn("z_score", item)
            self.assertIn("rank", item)

    def test_get_win_loss_pattern_analysis(self):
        """勝敗パターン分析（勝ち筋・負け筋）の検証."""
        wl = get_win_loss_pattern_analysis("FCT")
        self.assertTrue(wl["has_data"])
        self.assertGreaterEqual(wl["win_count"], 1)
        self.assertIn("comparison_table", wl)
        self.assertGreaterEqual(len(wl["comparison_table"]), 5)
        self.assertGreaterEqual(len(wl["win_takeaways"]), 1)
        self.assertGreaterEqual(len(wl["loss_takeaways"]), 1)

    def test_get_goal_pattern_breakdown(self):
        """得点パターンおよび時間帯別ダイナミクスの検証."""
        goal_data = get_goal_pattern_breakdown("FCT")
        self.assertIn("time_segments", goal_data)
        self.assertIn("path_breakdown", goal_data)

        path = goal_data["path_breakdown"]
        self.assertGreaterEqual(len(path), 4)
        total_pct = sum(path.values())
        self.assertGreaterEqual(total_pct, 95.0)
        self.assertLessEqual(total_pct, 105.0)

    def test_get_style_adherence_matches(self):
        """スタイル合致試合（会心の試合 Top 3）の検証."""
        adhere_matches = get_style_adherence_matches("FCT")
        self.assertEqual(len(adhere_matches), 3)

        top1 = adhere_matches[0]
        self.assertIn("match_id", top1)
        self.assertIn("score", top1)
        self.assertIn("style_score", top1)
        self.assertGreaterEqual(top1["style_score"], 70.0)
        self.assertIn("reason", top1)

    def test_get_team_squad_cbp(self):
        """所属選手ロスター＆CBP集計の検証."""
        squad = get_team_squad_cbp("FCT")
        self.assertGreater(len(squad), 15)

        top_player = squad[0]
        self.assertIn("player_id", top_player)
        self.assertIn("player_name", top_player)
        self.assertIn("position", top_player)
        self.assertIn("total_cbp", top_player)
        self.assertGreaterEqual(top_player["total_cbp"], 0.0)

    def test_get_team_h2h_comparison(self):
        """他クラブ直接対比（Head-to-Head）の検証."""
        h2h = get_team_h2h_comparison("FCT", "ZEL")
        self.assertIn("team_a", h2h)
        self.assertIn("team_b", h2h)
        self.assertEqual(h2h["team_a"]["id"], "FCT")
        self.assertEqual(h2h["team_b"]["id"], "ZEL")

        self.assertIn("stat_comparisons", h2h)
        self.assertEqual(len(h2h["stat_comparisons"]), 10)
        self.assertGreaterEqual(len(h2h["direct_matches"]), 1)

    def test_get_team_55_metrics_categorized(self):
        """全55戦術指標の6大カテゴリ別集計の検証."""
        categorized = get_team_55_metrics_categorized("FCT")
        self.assertEqual(len(categorized), 6)

        expected_cats = [
            "⚽ ポゼッション & パス循環",
            "⚔️ チャンス創出 & 前進推進",
            "🛡️ 守備・プレッシング & 迎撃",
            "⚡ フィジカル & 運動量強度",
            "🎯 勝敗・期待値 & ゲーム管理",
            "📋 陣形・環境・セットプレー",
        ]
        for c in expected_cats:
            self.assertIn(c, categorized)
            self.assertGreater(len(categorized[c]), 0)


if __name__ == "__main__":
    unittest.main()
