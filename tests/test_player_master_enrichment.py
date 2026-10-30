"""Unit tests for Step 1: scrapers/transfermarkt_jleague.py & pipeline/player_master_enricher.py."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jleague_player_scraper import J1_CLUBS_2026
from pipeline.player_master_enricher import (
    apply_tm_attributes_to_player,
    build_db_player_record_with_tm,
    match_player_with_tm_squad,
    normalize_legacy_player_files,
    sync_clean_entity_master_db,
    sync_injuries_and_loans_configs,
    tokenize_en_name,
)
from scrapers.transfermarkt_jleague import (
    parse_tm_birthdate,
    parse_tm_detailed_position,
    parse_tm_foot,
    parse_tm_height_cm,
    parse_tm_injuries_html,
    parse_tm_market_value_eur,
    parse_tm_squad_html,
    parse_tm_suspensions_html,
    parse_wiki_wikitext_profile,
)


SAMPLE_TM_SQUAD_HTML = """
<table class="items">
  <thead>
    <tr>
      <th>#</th>
      <th>選手</th>
      <th>生年月日/年齢</th>
      <th>国籍</th>
      <th>身長</th>
      <th>利き足</th>
      <th>加入日</th>
      <th>前所属</th>
      <th>契約</th>
      <th>市場価値</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>4</td>
      <td class="hauptlink">
        <table class="inline-table">
          <tr><td><a href="/hayato-inamura/profil/spieler/999001">Hayato Inamura</a></td></tr>
          <tr><td>センターバック</td></tr>
        </table>
      </td>
      <td>2002/05/06 (24)</td>
      <td><img title="Japan" /></td>
      <td>1,82m</td>
      <td>左</td>
      <td>2026/07/01</td>
      <td><a title="セルティックFC: Ablöse ?"><img title="セルティックFC" /></a></td>
      <td>2028/06/30</td>
      <td>€450K</td>
    </tr>
    <tr>
      <td>71</td>
      <td class="hauptlink">
        <table class="inline-table">
          <tr>
            <td>
              <a href="/ryotaro-araki/profil/spieler/999002">Ryotaro Araki</a>
              <span class="verletzt-table" title="Hamstring injury - 2026/11/10"></span>
            </td>
          </tr>
          <tr><td>攻撃的ミッドフィルダー</td></tr>
        </table>
      </td>
      <td>2002/01/29 (24)</td>
      <td><img title="Japan" /></td>
      <td>1,70m</td>
      <td>右</td>
      <td>2026/02/01</td>
      <td><a title="On loan from 鹿島アントラーズ until 2027/01/31"><img title="鹿島アントラーズ: Ablöse -" /></a></td>
      <td>2027/01/31</td>
      <td>€1.2M</td>
    </tr>
  </tbody>
</table>
"""

SAMPLE_TM_INJURIES_HTML = """
<table class="items">
  <thead>
    <tr><th>選手/ポジション</th><th>クラブ</th><th>年齢</th><th>Nation</th><th>Injury</th><th>since</th><th>until</th><th>市場価値</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>
        <table class="inline-table">
          <tr><td><a href="/tae-hyeon-kim/profil/spieler/888001">Tae-hyeon Kim</a></td></tr>
          <tr><td>センターバック</td></tr>
        </table>
      </td>
      <td><a href="/kashima-antlers/startseite/verein/2241" title="鹿島アントラーズ"></a></td>
      <td>26</td>
      <td><img title="Korea, South" /></td>
      <td>脛骨骨折</td>
      <td>2026/10/24</td>
      <td>2026/12/15</td>
      <td>€1.2M</td>
    </tr>
  </tbody>
</table>
"""

SAMPLE_TM_SUSPENSIONS_HTML = """
<table class="items">
  <thead><tr><th>選手</th><th>クラブ</th><th>年齢</th><th>Reason</th><th>since</th><th>until</th><th>試合数</th></tr></thead>
  <tbody>
    <tr>
      <td>
        <table class="inline-table">
          <tr><td><a href="/kyo-sato/profil/spieler/777001">Kyo Sato</a></td></tr>
          <tr><td>左サイドバック</td></tr>
        </table>
      </td>
      <td><a href="/kyoto-sanga/startseite/verein/593" title="京都サンガF.C."></a></td>
      <td>26</td>
      <td>累積警告による出場停止</td>
      <td>2026/10/26</td>
      <td>2026/11/02</td>
      <td>1</td>
    </tr>
  </tbody>
</table>
<table class="items">
  <thead><tr><th>選手</th><th>クラブ</th><th>年齢</th><th>イエローカード</th></tr></thead>
  <tbody>
    <tr>
      <td>
        <table class="inline-table">
          <tr><td><a href="/kento-misao/profil/spieler/777002">Kento Misao</a></td></tr>
          <tr><td>守備的ミッドフィルダー</td></tr>
        </table>
      </td>
      <td><a href="/kashima-antlers/startseite/verein/2241" title="鹿島アントラーズ"></a></td>
      <td>30</td>
      <td>3</td>
    </tr>
  </tbody>
</table>
"""


class TestPlayerMasterEnrichment(unittest.TestCase):
    """Test suite for Step 1 Transfermarkt parser and player master normalization."""

    def test_j1_clubs_2026_ids_aligned(self) -> None:
        ids = {c["team_id"] for c in J1_CLUBS_2026}
        self.assertIn("HIR", ids)
        self.assertIn("SAN", ids)
        self.assertNotIn("KYO", ids)
        san_entry = next(c for c in J1_CLUBS_2026 if c["team_id"] == "SAN")
        hir_entry = next(c for c in J1_CLUBS_2026 if c["team_id"] == "HIR")
        self.assertIn("京都", san_entry["club_name"])
        self.assertIn("広島", hir_entry["club_name"])

    def test_tm_primitive_parsers(self) -> None:
        self.assertEqual(parse_tm_foot("右"), "右足")
        self.assertEqual(parse_tm_foot("左"), "左足")
        self.assertEqual(parse_tm_foot("両足"), "両足")
        self.assertIsNone(parse_tm_foot("-"))

        self.assertEqual(parse_tm_detailed_position("左サイドバック"), ("LSB", "左サイドバック"))
        self.assertEqual(parse_tm_detailed_position("守備的ミッドフィルダー"), ("DMF", "守備的ミッドフィルダー"))
        self.assertEqual(parse_tm_height_cm("1,84m"), 184)
        self.assertEqual(parse_tm_birthdate("1999/6/5 (27)"), "1999/06/05")
        self.assertEqual(parse_tm_market_value_eur("€1.2M"), 1_200_000)
        self.assertEqual(parse_tm_market_value_eur("€450K"), 450_000)

    def test_parse_tm_squad_html(self) -> None:
        rows = parse_tm_squad_html(SAMPLE_TM_SQUAD_HTML, "FCT")
        self.assertEqual(len(rows), 2)

        inamura = rows[0]
        self.assertEqual(inamura["number"], 4)
        self.assertEqual(inamura["en_name"], "Hayato Inamura")
        self.assertEqual(inamura["detailed_position_code"], "CB")
        self.assertEqual(inamura["dominant_foot"], "左足")
        self.assertEqual(inamura["height_cm"], 182)
        self.assertEqual(inamura["market_value_eur"], 450_000)
        self.assertEqual(inamura["previous_club"], "セルティックFC")

        araki = rows[1]
        self.assertEqual(araki["dominant_foot"], "右足")
        self.assertEqual(araki["detailed_position_code"], "OMF")
        self.assertEqual(araki["loan_from_club"], "鹿島アントラーズ")
        self.assertEqual(araki["loan_until"], "2027/01/31")
        self.assertIn("Hamstring", araki["injury_note"] or "")

    def test_parse_tm_injuries_and_suspensions(self) -> None:
        injs = parse_tm_injuries_html(SAMPLE_TM_INJURIES_HTML)
        self.assertEqual(len(injs), 1)
        self.assertEqual(injs[0]["team_id"], "KAS")
        self.assertEqual(injs[0]["injury_type"], "脛骨骨折")
        self.assertEqual(injs[0]["since_date"], "2026/10/24")

        disc = parse_tm_suspensions_html(SAMPLE_TM_SUSPENSIONS_HTML)
        self.assertEqual(len(disc["suspensions"]), 1)
        self.assertEqual(disc["suspensions"][0]["team_id"], "SAN")
        self.assertEqual(len(disc["yellow_reaches"]), 1)
        self.assertEqual(disc["yellow_reaches"][0]["team_id"], "KAS")
        self.assertEqual(disc["yellow_reaches"][0]["yellow_cards"], 3)

    def test_parse_wiki_wikitext(self) -> None:
        wt = """
        {{サッカー選手
        |名前 = 大迫敬介
        |身長 = 187cm
        |体重 = 86kg
        |利き足 = 右足
        }}
        """
        prof = parse_wiki_wikitext_profile(wt)
        self.assertEqual(prof["dominant_foot"], "右足")
        self.assertEqual(prof["height_cm"], 187)
        self.assertEqual(prof["weight_kg"], 86)

    def test_normalize_legacy_player_files_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp)
            (pdir / "SAN_players.json").write_text(
                json.dumps([{"team_id": "SAN", "name": "大迫 敬介", "club_name": "サンフレッチェ広島"}]),
                encoding="utf-8",
            )
            (pdir / "KYO_players.json").write_text(
                json.dumps([{"team_id": "KYO", "name": "佐藤 響", "club_name": "京都サンガF.C."}]),
                encoding="utf-8",
            )

            res1 = normalize_legacy_player_files(pdir)
            self.assertTrue(res1["migrated"])
            self.assertFalse((pdir / "KYO_players.json").exists())

            hir_data = json.loads((pdir / "HIR_players.json").read_text(encoding="utf-8"))
            san_data = json.loads((pdir / "SAN_players.json").read_text(encoding="utf-8"))
            self.assertEqual(hir_data[0]["team_id"], "HIR")
            self.assertEqual(hir_data[0]["name"], "大迫 敬介")
            self.assertEqual(san_data[0]["team_id"], "SAN")
            self.assertEqual(san_data[0]["name"], "佐藤 響")

            res2 = normalize_legacy_player_files(pdir)
            self.assertFalse(res2["migrated"])

    def test_match_and_sync_configs_and_db(self) -> None:
        tm_squad = parse_tm_squad_html(SAMPLE_TM_SQUAD_HTML, "FCT")
        player = {
            "player_id": "1650001",
            "team_id": "FCT",
            "name": "稲村 隼翔",
            "name_en": "INAMURA Hayato",
            "club_name": "ＦＣ東京",
            "position": "DF",
            "number": "4",
            "birthdate": "2002/5/6",
            "height_cm": "182",
            "weight_kg": "75",
            "dominant_foot": "",
        }
        matched = match_player_with_tm_squad(player, tm_squad)
        self.assertIsNotNone(matched)
        apply_tm_attributes_to_player(player, matched or {})
        self.assertEqual(player["dominant_foot"], "左足")
        self.assertEqual(player["detailed_position_code"], "CB")
        self.assertIn("hayato", tokenize_en_name(player["name_en"]))

        loan_player = {
            "player_id": "1650002",
            "team_id": "FCT",
            "name": "テスト レンタル選手",
            "name_en": "Ryotaro Araki",
            "club_name": "ＦＣ東京",
            "position": "MF",
            "number": "71",
            "birthdate": "2002/1/29",
            "dominant_foot": "",
        }
        matched_loan = match_player_with_tm_squad(loan_player, tm_squad)
        apply_tm_attributes_to_player(loan_player, matched_loan or {})

        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            inj_p = tpath / "inj.json"
            loan_p = tpath / "loan.json"
            db_p = tpath / "test.db"

            tm_injs = parse_tm_injuries_html(SAMPLE_TM_INJURIES_HTML)
            c_stats = sync_injuries_and_loans_configs([player, loan_player], tm_injs, inj_p, loan_p)
            self.assertEqual(c_stats["added_injuries"], 1)
            self.assertEqual(c_stats["added_loans"], 1)

            conn = sqlite3.connect(db_p)
            conn.execute(
                """
                CREATE TABLE entity_master_players (
                    player_id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    position TEXT,
                    number INTEGER,
                    en_name TEXT,
                    aliases_json TEXT
                );
                """,
            )
            conn.execute(
                "INSERT INTO entity_master_players VALUES ('P_KYO_1_旧選手', '旧選手', 'KYO', 'GK', 1, NULL, '[]');",
            )
            conn.execute(
                "INSERT INTO entity_master_players VALUES ('P_SAN_1_大迫敬介', '大迫 敬介', 'SAN', 'GK', 1, NULL, '[]');",
            )
            conn.commit()
            conn.close()

            san_real = {
                "player_id": "1600001",
                "team_id": "SAN",
                "name": "佐藤 響",
                "name_en": "Kyo Sato",
                "position": "DF",
                "number": "44",
                "dominant_foot": "左足",
            }
            db_res = sync_clean_entity_master_db([player, san_real], {}, db_path=db_p)
            self.assertEqual(db_res["deleted_kyo"], 1)
            self.assertEqual(db_res["deleted_stale_san"], 1)
            self.assertEqual(db_res["upserted"], 2)

            rec_check = build_db_player_record_with_tm(player, {})
            self.assertEqual(rec_check["dominant_foot"], "左足")
            prof_json = json.loads(rec_check["profile_json"])
            self.assertEqual(prof_json["detailed_position_code"], "CB")


if __name__ == "__main__":
    unittest.main()

