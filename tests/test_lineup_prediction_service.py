"""スタメン予想＆交代シミュレーションサービスの単体テスト (tests/test_lineup_prediction_service.py)."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from pipeline.lineup_prediction_service import LineupPredictionService

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"


class TestLineupPredictionService(unittest.TestCase):
    """LineupPredictionService の決定論的計算と厳格なホワイトリスト制を検証する."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = LineupPredictionService()
        conn = sqlite3.connect(DB_PATH)
        try:
            # FC東京の現所属全選手名セット
            cls.fct_roster_names = {
                r[0]
                for r in conn.execute(
                    "SELECT canonical_name FROM entity_master_players WHERE team_id = 'FCT'",
                ).fetchall()
            }
            # 岡山の現所属全選手名セット
            cls.oka_roster_names = {
                r[0]
                for r in conn.execute(
                    "SELECT canonical_name FROM entity_master_players WHERE team_id = 'OKA'",
                ).fetchall()
            }
        finally:
            conn.close()

    def test_roster_whitelist_strict_fct(self) -> None:
        """FC東京のホワイトリストに遠藤渓太（柏レイソル所属）が絶対に存在しないことを検証."""
        self.assertNotIn("遠藤 渓太", self.fct_roster_names)
        self.assertNotIn("遠藤渓太", self.fct_roster_names)

        roster = self.service.get_club_active_roster_whitelist("FCT")
        roster_names = {p["canonical_name"] for p in roster}
        self.assertNotIn("遠藤 渓太", roster_names)
        self.assertIn("仲川 輝人", roster_names)
        self.assertIn("長倉 幹樹", roster_names)
        self.assertIn("アレクサンダー ショルツ", roster_names)

    def test_predict_lineup_fct_contains_no_past_or_external_players(self) -> None:
        """FC東京の予想スタメン・対抗・交代枠に現所属以外の選手が1人も含まれないことを検証."""
        pred = self.service.predict_starting_lineup(
            team_id="FCT",
            opponent_team_id="OKA",
            as_of_date="2026-10-31",
            formation="4-4-2",
        )

        all_mentioned_players = set()
        for sp in pred["slots"]:
            all_mentioned_players.add(sp.primary.player_name)
            if sp.contender:
                all_mentioned_players.add(sp.contender.player_name)

        for sub in pred["impact_subs"]:
            all_mentioned_players.add(sub["player_out"])
            all_mentioned_players.add(sub["player_in"])

        # 過去選手や他クラブ選手が絶対に混入していないこと
        self.assertNotIn("遠藤 渓太", all_mentioned_players)
        self.assertNotIn("ディエゴ オリヴェイラ", all_mentioned_players)
        self.assertNotIn("渡邊 凌磨", all_mentioned_players)

        # 登場したすべての選手名が、FC東京の現所属ホワイトリスト内に100%存在すること
        for name in all_mentioned_players:
            self.assertIn(
                name,
                self.fct_roster_names,
                f"Player '{name}' is not in FCT active roster!",
            )

    def test_predict_lineup_oka_contains_no_external_players(self) -> None:
        """岡山の予想スタメン・対抗・交代枠に現所属以外の選手が1人も含まれないことを検証."""
        pred = self.service.predict_starting_lineup(
            team_id="OKA",
            opponent_team_id="FCT",
            as_of_date="2026-10-31",
            formation="3-4-2-1",
        )

        all_mentioned_players = set()
        for sp in pred["slots"]:
            all_mentioned_players.add(sp.primary.player_name)
            if sp.contender:
                all_mentioned_players.add(sp.contender.player_name)

        for sub in pred["impact_subs"]:
            all_mentioned_players.add(sub["player_out"])
            all_mentioned_players.add(sub["player_in"])

        for name in all_mentioned_players:
            self.assertIn(
                name,
                self.oka_roster_names,
                f"Player '{name}' is not in OKA active roster!",
            )

    def test_suspended_players_completely_excluded(self) -> None:
        """出場停止の選手（京都・佐藤響、G大阪・一森純）が予想候補から完全除外されることを検証."""
        # 京都・佐藤響はMW12終了時点で累積4枚停止
        pred_san = self.service.predict_starting_lineup(
            team_id="SAN",
            opponent_team_id="PUL",
            as_of_date="2026-10-31",
        )
        san_starters = [sp.primary.player_name for sp in pred_san["slots"]]
        san_contenders = [sp.contender.player_name for sp in pred_san["slots"] if sp.contender]
        self.assertNotIn("佐藤 響", san_starters)
        self.assertNotIn("佐藤 響", san_contenders)

        # G大阪・一森純は前節退場による出場停止
        pred_gam = self.service.predict_starting_lineup(
            team_id="GAM",
            opponent_team_id="ZEL",
            as_of_date="2026-10-31",
        )
        gam_starters = [sp.primary.player_name for sp in pred_gam["slots"]]
        gam_contenders = [sp.contender.player_name for sp in pred_gam["slots"] if sp.contender]
        self.assertNotIn("一森 純", gam_starters)
        self.assertNotIn("一森 純", gam_contenders)

    def test_fct_mw12_starters_and_in_form_recognition(self) -> None:
        """前節2ゴールの仲川輝人および今季7ゴールの長倉幹樹がFC東京スタメン候補に選ばれることを検証."""
        pred = self.service.predict_starting_lineup(
            team_id="FCT",
            opponent_team_id="OKA",
            as_of_date="2026-10-31",
            formation="4-4-2",
        )
        primary_names = [sp.primary.player_name for sp in pred["slots"]]
        self.assertIn("仲川 輝人", primary_names)
        self.assertIn("長倉 幹樹", primary_names)
        self.assertIn("キム スンギュ", primary_names)

    def test_display_text_formatting(self) -> None:
        """本命＋カッコ付き対抗、および想定交代プランの表示テキストが仕様通り出力されることを検証."""
        # ファジアーノ岡山ではCF枠で江坂（本命）と河野（対抗）の競合が発生する
        pred_oka = self.service.predict_starting_lineup(
            team_id="OKA",
            opponent_team_id="FCT",
            as_of_date="2026-10-31",
            formation="3-4-2-1",
        )
        text_oka = pred_oka["display_text"]

        self.assertIn("【予想スタメン：3-4-2-1】", text_oka)
        self.assertIn("GK:", text_oka)
        self.assertIn("DF:", text_oka)
        self.assertIn("MF:", text_oka)
        self.assertIn("FW:", text_oka)
        self.assertIn("対抗:", text_oka)
        self.assertIn("【想定交代プラン（Impact Subs）】", text_oka)
        self.assertIn("狙い:", text_oka)

    def test_no_primary_in_contenders(self) -> None:
        """スタメン本命（11名）に選ばれた選手が、他ポジションの対抗馬として重複出現しないことを検証."""
        pred = self.service.predict_starting_lineup(
            team_id="FCT",
            opponent_team_id="OKA",
            as_of_date="2026-10-31",
            formation="4-4-2",
        )
        primary_ids = {sp.primary.player_id for sp in pred["slots"]}
        self.assertEqual(len(primary_ids), 11)

        # 全スロットの対抗馬について、スタメン11名に含まれていないことを検証
        for sp in pred["slots"]:
            if sp.contender:
                self.assertNotIn(
                    sp.contender.player_id,
                    primary_ids,
                    f"Contender {sp.contender.player_name} should not be among primary starters",
                )


if __name__ == "__main__":
    unittest.main()

