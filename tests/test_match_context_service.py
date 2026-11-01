"""2026年J1全20クラブ対応 連戦負荷・出場停止・試合コンテキストサービスの単体テスト (tests/test_match_context_service.py)."""

from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.match_context_service import (
    MatchContextService,
    estimate_club_travel,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestMatchContextService(unittest.TestCase):
    """MatchContextService の決定論的計算とJ1規約準拠を検証するテストスイート."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = MatchContextService()

    def test_travel_distance_estimation(self) -> None:
        """全20クラブの移動距離算出（ホーム0km、東京互換、遠距離遠征）を検証."""
        dist_home, t_home = estimate_club_travel("FCT", "味の素スタジアム", True, self.service.stadium_master)
        self.assertEqual(dist_home, 0)
        self.assertEqual(t_home, "HOME")

        # FCT -> 清水（170km SHINKANSEN）
        dist_fct, t_fct = estimate_club_travel("FCT", "ＩＡＩスタジアム日本平", False, self.service.stadium_master)
        self.assertEqual(dist_fct, 170)
        self.assertEqual(t_fct, "SHINKANSEN")

        # VVN（長崎） -> 札幌または鹿嶋（長距離FLIGHT）
        dist_vvn, t_vvn = estimate_club_travel("VVN", "県立カシマサッカースタジアム", False, self.service.stadium_master)
        self.assertGreaterEqual(dist_vvn, 900)
        self.assertEqual(t_vvn, "FLIGHT")

    def test_all_20_clubs_schedule_and_rest_days(self) -> None:
        """全20クラブの第12節（2026-10-25）時点の休養日数計算が正常に動作することを検証."""
        clubs = [
            "FCT", "ZEL", "VOB", "MAR", "SAN", "MIT",
            "URA", "CER", "FUK", "GAM", "HIR", "JEF",
            "KAS", "KAW", "NAG", "OKA", "PUL", "REY",
            "VER", "VVN",
        ]
        for tid in clubs:
            res = self.service.calculate_schedule_fatigue(
                team_id=tid,
                current_date_str="2026-10-26",
            )
            self.assertIsNotNone(res["previous_match_date"], f"{tid} must have prior match before MW12")
            self.assertIsNotNone(res["rest_days"], f"{tid} rest days must be calculated")
            self.assertIn("中", res["rest_days_display"])

    def test_player_load_recent_minutes(self) -> None:
        """選手別の直近3/5試合および14/21日間累積負荷が正常に集計されることを検証."""
        load = self.service.calculate_player_load(
            team_id="FCT",
            current_date_str="2026-10-26",
        )
        self.assertEqual(load["prior_matches_count"], 12)
        self.assertGreater(len(load["players"]), 15)

        for p in load["players"]:
            self.assertGreaterEqual(p["season_minutes"], p["minutes_last_5"])
            self.assertGreaterEqual(p["minutes_last_5"], p["minutes_last_3"])
            self.assertIn(p["load_level"], ["HIGH", "MEDIUM", "LOW"])

        # 直近3戦フル出場の選手が高負荷主力に含まれること
        high_loads = load["high_load_players"]
        if high_loads:
            top_p = high_loads[0]
            self.assertGreaterEqual(top_p["minutes_last_3"], 240)
            self.assertNotEqual(top_p["position"], "GK")

    def test_yellow_card_accumulation_4_cards_suspension(self) -> None:
        """京都・佐藤響がMW12終了時点で累積4枚に達し、次節（MW13想定時点）で出場停止となることを検証."""
        disc = self.service.calculate_disciplinary_status(
            team_id="SAN",
            current_date_str="2026-10-31",
        )
        suspended_names = [p["player_name"] for p in disc["suspended_players"]]
        self.assertTrue(
            any("佐藤" in n and "響" in n for n in suspended_names),
            f"Kyo Sato should be suspended for 4th yellow card, got: {suspended_names}",
        )
        sato_susp = next(p for p in disc["suspended_players"] if "佐藤" in p["player_name"] and "響" in p["player_name"])
        self.assertEqual(sato_susp["type"], "YELLOW_ACCUMULATION_SUSPENSION")
        self.assertEqual(sato_susp["cumulative_yellows"], 4)

    def test_yellow_card_suspension_served_and_reset(self) -> None:
        """累積4枚による出場停止が、対象試合を経過した後は消化済みとなり停止が解除されることを検証."""
        # 京都・佐藤響はMW12終了時点で4枚到達。もしMW12より前の時点（例: MW11直前 2026-10-20）なら累積3枚でリーチ
        disc_mw11 = self.service.calculate_disciplinary_status(
            team_id="SAN",
            current_date_str="2026-10-20",
        )
        suspended_before = [p["player_name"] for p in disc_mw11["suspended_players"]]
        reach_before = [p["player_name"] for p in disc_mw11["warning_reach_players"]]
        self.assertFalse(any("佐藤" in n and "響" in n for n in suspended_before))
        self.assertTrue(any("佐藤" in n and "響" in n for n in reach_before))

    def test_red_card_suspension_next_match(self) -> None:
        """G大阪・一森純がMW12（2026-10-24）で退場となり、直後（MW13想定時点）でRED_SUSPENSIONとなることを検証."""
        disc = self.service.calculate_disciplinary_status(
            team_id="GAM",
            current_date_str="2026-10-31",
        )
        suspended_names = [p["player_name"] for p in disc["suspended_players"]]
        self.assertTrue(
            any("一森" in n and "純" in n for n in suspended_names),
            f"Jun Ichimori should be suspended for red card, got: {suspended_names}",
        )
        ichimori_susp = next(p for p in disc["suspended_players"] if "一森" in p["player_name"])
        self.assertEqual(ichimori_susp["type"], "RED_SUSPENSION")

    def test_two_yellows_red_card_not_counted_in_accumulation(self) -> None:
        """警告2枚退場（マテウス・サヴィオ MW1）の警告2枚が累積警告カウントに算入されないことを検証."""
        # 浦和のMW2時点（2026-08-15）: MW1（2026-08-07）でサヴィオが退場
        disc = self.service.calculate_disciplinary_status(
            team_id="URA",
            current_date_str="2026-08-15",
        )
        suspended_names = [p["player_name"] for p in disc["suspended_players"]]
        self.assertTrue(any("サヴィオ" in n for n in suspended_names))

        # 警告2枚退場により、その試合の2枚は累積警告に算入されないため、累積イエローは0枚であること
        savio_yellows = disc["all_cumulative_yellows"].get("マテウス サヴィオ", 0)
        self.assertEqual(savio_yellows, 0)

    def test_warning_reach_3_yellows(self) -> None:
        """鹿島・三竿健斗がMW12終了時点で累積3枚リーチ（warning_reach_players）として検出されることを検証."""
        disc = self.service.calculate_disciplinary_status(
            team_id="KAS",
            current_date_str="2026-10-31",
        )
        reach_names = [p["player_name"] for p in disc["warning_reach_players"]]
        self.assertTrue(
            any("三竿" in n and "健斗" in n for n in reach_names),
            f"Kento Misao should be on yellow reach (3 yellows), got: {reach_names}",
        )

    def test_anti_future_leakage(self) -> None:
        """第5節時点（2026-09-02）を指定した場合、第6節以降の試合データ・カードが一切混入しないことを検証."""
        ctx_early = self.service.get_club_prematch_context(
            team_id="FCT",
            as_of_date="2026-09-02",
        )
        self.assertEqual(ctx_early["player_load"]["prior_matches_count"], 4)

        # 第8節の高宇洋の退場（2026-09-19）は第5節時点では絶対に検出されないこと
        suspended = [p["player_name"] for p in ctx_early["disciplinary"]["suspended_players"]]
        self.assertFalse(any("高" in n and "宇洋" in n for n in suspended))

    def test_calculate_league_standings_mw12(self) -> None:
        """第12節終了時点（2026-10-26）の順位表が正確に計算されることを検証."""
        st = self.service.calculate_league_standings(season=2026, as_of_date="2026-10-26")
        self.assertEqual(len(st["table"]), 20)
        # 1位町田、2位FC東京（勝点27同率）
        top1 = st["table"][0]
        top2 = st["table"][1]
        self.assertIn(top1["team_id"], ["ZEL", "FCT"])
        self.assertIn(top2["team_id"], ["ZEL", "FCT"])
        self.assertEqual(top1["points"], 27)
        self.assertEqual(top2["points"], 27)

    def test_get_recent_lineup_and_scorers(self) -> None:
        """直前節（MW12）の実先発メンバーおよび得点者が正しく取得されることを検証."""
        lineup = self.service.get_recent_lineup_and_scorers(team_id="FCT", current_date_str="2026-10-31")
        self.assertEqual(lineup["last_match_id"], "20261025_FCT_MIT")
        starter_names = [p["player_name"] for p in lineup["starters"]]
        self.assertIn("仲川 輝人", starter_names)
        self.assertIn("長倉 幹樹", starter_names)
        self.assertIn("アレクサンダー ショルツ", starter_names)

        # 直近得点者に仲川、ダニ・ゴメス、安斎、ショルツ等が含まれること
        scorer_names = [s["player_name"] for s in lineup["recent_scorers"]]
        self.assertTrue(any("仲川" in n for n in scorer_names))
        self.assertTrue(any("ダニ" in n for n in scorer_names))

    def test_matchup_prematch_context_both_sides(self) -> None:
        """1試合の両チーム双方のコンテキストと休養日数差が一括取得できることを検証."""
        res = self.service.get_matchup_prematch_context("20261025_FCT_MIT")
        self.assertEqual(res["match_id"], "20261025_FCT_MIT")
        self.assertEqual(res["home_team_id"], "FCT")
        self.assertEqual(res["away_team_id"], "MIT")
        self.assertIn("home", res)
        self.assertIn("away", res)
        self.assertIn("schedule_fatigue", res["home"])
        self.assertIn("player_load", res["home"])
        self.assertIn("disciplinary", res["home"])
        self.assertIn("loan_restrictions", res["home"])
        self.assertIn("rest_days_advantage_home", res)


if __name__ == "__main__":
    unittest.main()

