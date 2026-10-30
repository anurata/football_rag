"""2026年J1全120試合 個人別・チーム別テレメトリ統合格納パイプライン (pipeline/player_stats_ingester.py).

3大一次データソース（Yahoo `/stats` + SPAIA `live_player_detail_stats` + Football LAB `CBP`）を
正規化された `entity_master_players.player_id` に名寄せして結合し、
`football.db` の `player_match_stats` および `team_match_stats` に非破壊UPSERTする。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from experiments.enrich_layer1_ground_truth import (
    calculate_player_deterministic_rating,
    make_name_key,
    normalize_name,
    safe_float,
    safe_int,
)

logger = logging.getLogger("player_stats_ingester")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_YAHOO_DIR = ROOT_DIR / "data" / "raw" / "yahoo"
DEFAULT_SPAIA_DIR = ROOT_DIR / "data" / "raw" / "spaia"
DEFAULT_FLAB_DIR = ROOT_DIR / "data" / "raw" / "football_lab"

EMPTY_CBP_DICT: Dict[str, float] = {
    "attack": 0.0,
    "defense": 0.0,
    "gain": 0.0,
    "pass": 0.0,
    "cross": 0.0,
    "dribble": 0.0,
    "shoot": 0.0,
    "save": 0.0,
    "total": 0.0,
}


class CanonicalPlayerResolver:
    """entity_master_players に対して (team_id, player_name, number) から正規 player_id を解決する."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.by_name: Dict[Tuple[str, str], str] = {}
        self.by_num: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._load(conn)

    def _load(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(entity_master_players)").fetchall()}
        has_aliases = "aliases_json" in cols
        sql = (
            "SELECT player_id, team_id, number, canonical_name, aliases_json FROM entity_master_players"
            if has_aliases
            else "SELECT player_id, team_id, number, canonical_name, NULL FROM entity_master_players"
        )
        for pid, tid, num, cname, aliases_raw in cur.execute(sql).fetchall():
            ckey = make_name_key(cname or "")
            if tid and num is not None:
                self.by_num[(tid, str(num))] = (pid, ckey)
            if tid and ckey:
                self.by_name[(tid, ckey)] = pid
            if tid and aliases_raw:
                try:
                    for al in json.loads(aliases_raw):
                        akey = make_name_key(str(al))
                        if akey and (tid, akey) not in self.by_name:
                            self.by_name[(tid, akey)] = pid
                except Exception:
                    pass

    def resolve(self, team_id: str, player_name: str, number: int) -> str:
        """正規 player_id を返す。マスタ未登録時のみ標準フォーマットIDを動的生成する."""
        ckey = make_name_key(player_name)
        if ckey and (team_id, ckey) in self.by_name:
            return self.by_name[(team_id, ckey)]

        num_key = (team_id, str(number))
        if number and num_key in self.by_num:
            cand_pid, cand_ckey = self.by_num[num_key]
            if not ckey or not cand_ckey:
                return cand_pid
            if ckey in cand_ckey or cand_ckey in ckey or ckey[:2] == cand_ckey[:2]:
                return cand_pid

        return f"P_{team_id}_{number}_{ckey[:8]}"


def _parse_count_from_cell(raw_val: Any) -> int:
    """'12(85.7%)' や '3' のようなYahooセル文字列から先頭の整数回数を抽出する."""
    if raw_val is None:
        return 0
    head = str(raw_val).split("(")[0].strip()
    return safe_int(head, 0)


def build_yahoo_player_lookup(ystats_players: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Yahoo `/stats` の個人スタッツ配列を name_key 辞書に構造化する."""
    lookup: Dict[str, Dict[str, Any]] = {}
    for p in ystats_players:
        k = make_name_key(p.get("player_name", ""))
        if not k:
            continue
        dist = p.get("distance", {})
        spr = p.get("sprint", {})
        att = p.get("attack", {})
        defense = p.get("defense", {})
        pass_info = p.get("pass", {})
        area = p.get("plays_by_area", {})
        set_p = p.get("set_pieces", {})
        disc = p.get("discipline", {})

        lookup[k] = {
            "player_name": normalize_name(p.get("player_name", "")),
            "team_name": p.get("team_name", ""),
            "position": p.get("position", ""),
            "distance_km": safe_float(dist.get("total")),
            "distance_1h": safe_float(dist.get("first_half")),
            "distance_2h": safe_float(dist.get("second_half")),
            "sprints": safe_int(spr.get("total")),
            "sprints_1h": safe_int(spr.get("first_half")),
            "sprints_2h": safe_int(spr.get("second_half")),
            "max_speed_kmh": safe_float(spr.get("max_speed")),
            "shoots": _parse_count_from_cell(att.get("shoot")),
            "shoots_on_target": _parse_count_from_cell(att.get("shoot_on_target")),
            "goals": _parse_count_from_cell(att.get("goals")),
            "dribble_success": _parse_count_from_cell(att.get("dribble_success")),
            "tackles": _parse_count_from_cell(defense.get("tackle_success")),
            "loose_ball_recoveries": _parse_count_from_cell(defense.get("loose_ball_recovery")),
            "blocks": _parse_count_from_cell(defense.get("block")),
            "clears": _parse_count_from_cell(defense.get("clear")),
            "passes": _parse_count_from_cell(pass_info.get("pass_success")),
            "attacking_third_passes": _parse_count_from_cell(pass_info.get("attacking_third_pass")),
            "through_passes": _parse_count_from_cell(pass_info.get("through_pass")),
            "crosses": _parse_count_from_cell(pass_info.get("cross")),
            "assists": _parse_count_from_cell(pass_info.get("assist")),
            "touches": _parse_count_from_cell(area.get("total")),
            "plays_attacking_third": _parse_count_from_cell(area.get("attacking_third")),
            "plays_middle_third": _parse_count_from_cell(area.get("middle_third")),
            "plays_defensive_third": _parse_count_from_cell(area.get("defensive_third")),
            "fk_count": _parse_count_from_cell(set_p.get("fk")),
            "ck_count": _parse_count_from_cell(set_p.get("ck")),
            "fouls": _parse_count_from_cell(disc.get("foul")),
            "suffer_fouls": _parse_count_from_cell(disc.get("suffer_foul")),
            "yellows": _parse_count_from_cell(disc.get("yellow_card")),
            "reds": _parse_count_from_cell(disc.get("red_card")),
        }
    return lookup


def build_flab_cbp_lookup(
    flab_matrix: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    """Football LAB player_matrix から個人CBP辞書とチーム別最大値辞書を返す."""
    cbp_lookup: Dict[str, Dict[str, float]] = {}
    team_max: Dict[str, Dict[str, float]] = {
        "HOME": {"attack": 0.0, "defense": 0.0, "gain": 0.0},
        "AWAY": {"attack": 0.0, "defense": 0.0, "gain": 0.0},
    }

    for p in flab_matrix:
        k = make_name_key(p.get("player_name", ""))
        if not k:
            continue
        pts = p.get("points", {})
        att = safe_float(p.get("attack", pts.get("攻撃", 0.0)))
        dfn = safe_float(p.get("defense", pts.get("守備", 0.0)))
        gain = safe_float(p.get("gain", pts.get("奪取", 0.0)))
        pas = safe_float(p.get("pass", pts.get("パス", 0.0)))
        crs = safe_float(p.get("cross", pts.get("クロス", 0.0)))
        drb = safe_float(p.get("dribble", pts.get("ドリブル", 0.0)))
        sht = safe_float(p.get("shoot", pts.get("シュート", 0.0)))
        sav = safe_float(p.get("save", pts.get("セーブ", 0.0)))

        cbp_lookup[k] = {
            "attack": att,
            "defense": dfn,
            "gain": gain,
            "pass": pas,
            "cross": crs,
            "dribble": drb,
            "shoot": sht,
            "save": sav,
            "total": round(att + dfn + gain, 3),
        }

        side = str(p.get("team_side", "HOME")).upper()
        if side not in team_max:
            side = "HOME"
        for m_key, m_val in (("attack", att), ("defense", dfn), ("gain", gain)):
            if m_val > team_max[side][m_key]:
                team_max[side][m_key] = m_val

    return (cbp_lookup, team_max)


def _build_spaia_compact_dict(sp: Dict[str, Any]) -> Dict[str, Any]:
    """SPAIA個人スタッツ1件から戦術分析・カード集計用の構造化辞書を生成する."""
    return {
        "pa_entries": safe_int(sp.get("PAPlayCount")),
        "pa_side_left_entries": safe_int(sp.get("PASidePlayLCount")),
        "pa_side_right_entries": safe_int(sp.get("PASidePlayRCount")),
        "m30_entries": safe_int(sp.get("M30PlayCount")),
        "at_3rd_entries": safe_int(sp.get("At3rdPlayCount")),
        "at_play_rate": safe_float(sp.get("AtPlayRate")),
        "mt_play_rate": safe_float(sp.get("MtPlayRate")),
        "dt_play_rate": safe_float(sp.get("DtPlayRate")),
        "pass_count": safe_int(sp.get("PassCount")),
        "pass_rate": safe_float(sp.get("PassRate")),
        "pass_forward": {
            "count": safe_int(sp.get("PassDirection1Count")),
            "success_rate": safe_float(sp.get("PassDirection1Success")),
        },
        "pass_crossway": {
            "count": safe_int(sp.get("PassDirection2Count")),
            "success_rate": safe_float(sp.get("PassDirection2Success")),
        },
        "pass_backward": {
            "count": safe_int(sp.get("PassDirection3Count")),
            "success_rate": safe_float(sp.get("PassDirection3Success")),
        },
        "opp_area_pass_count": safe_int(sp.get("OpponentAreaPassCount")),
        "opp_area_pass_rate": safe_float(sp.get("OpponentAreaPassRate")),
        "cross_count": safe_int(sp.get("CrossCount")),
        "cross_rate": safe_float(sp.get("CrossRate")),
        "dribble_count": safe_int(sp.get("DribbleCount")),
        "dribble_rate": safe_float(sp.get("DribbleRate")),
        "clear_count": safe_int(sp.get("ClearCount")),
        "tackle_count": safe_int(sp.get("TackleCount")),
        "at_3rd_tackle": safe_int(sp.get("At3rdTackleCount")),
        "opp_area_tackle": safe_int(sp.get("OpponentAreaTackleCount")),
        "save_count": safe_int(sp.get("SaveCount")),
        "save_rate": safe_float(sp.get("SaveRate")),
        "foul_count": safe_int(sp.get("Foul")),
        "yellow_cards": safe_int(sp.get("Yellow")),
        "red_cards": safe_int(sp.get("Red")),
    }


def _merge_from_spaia_primary(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    home_score: int,
    away_score: int,
    spaia_pstats: List[Dict[str, Any]],
    yahoo_lookup: Dict[str, Dict[str, Any]],
    cbp_lookup: Dict[str, Dict[str, float]],
    team_cbp_max: Dict[str, Dict[str, float]],
    resolver: CanonicalPlayerResolver,
) -> List[Dict[str, Any]]:
    """SPAIAを主軸にYahooトラッキングとFootball LAB CBPを統合する."""
    records: List[Dict[str, Any]] = []
    for sp in spaia_pstats:
        pname = normalize_name(sp.get("Name", ""))
        pkey = make_name_key(pname)
        if not pkey:
            continue

        hv = safe_int(sp.get("HV", 1))
        team_id = home_team_id if hv == 1 else away_team_id
        side_label = "HOME" if hv == 1 else "AWAY"
        opp_score = away_score if hv == 1 else home_score
        clean_sheet = opp_score == 0

        pos = str(sp.get("Pos", "")).strip()
        number = safe_int(sp.get("Uni", 0))
        is_starter = 1 if str(sp.get("StartF", "0")) == "1" else 0
        minutes_played = safe_int(sp.get("Time", 0))
        goals = safe_int(sp.get("Score", 0))
        pk_goals = safe_int(sp.get("PKScore", 0))
        assists = safe_int(sp.get("Assist", 0))
        save_count = safe_int(sp.get("SaveCount", 0))

        yinfo = yahoo_lookup.get(pkey, {})
        cbp = cbp_lookup.get(pkey, dict(EMPTY_CBP_DICT))
        spaia_compact = _build_spaia_compact_dict(sp)

        yellows = max(spaia_compact["yellow_cards"], yinfo.get("yellows", 0))
        reds = max(spaia_compact["red_cards"], yinfo.get("reds", 0))

        rating = calculate_player_deterministic_rating(
            pos=pos,
            play_time=minutes_played,
            goals=goals,
            pk_goals=pk_goals,
            assists=assists,
            clean_sheet=clean_sheet,
            cbp_info=cbp,
            team_cbp_max=team_cbp_max[side_label],
            save_count=save_count,
            yellows=yellows,
            reds=reds,
            pass_count=spaia_compact["pass_count"],
            pass_rate=spaia_compact["pass_rate"],
        )

        raw_stats = {
            "rating": rating,
            "max_speed_kmh": yinfo.get("max_speed_kmh"),
            "distance_first_half": yinfo.get("distance_1h"),
            "distance_second_half": yinfo.get("distance_2h"),
            "sprints_first_half": yinfo.get("sprints_1h"),
            "sprints_second_half": yinfo.get("sprints_2h"),
            "plays_by_area": {
                "total": yinfo.get("touches", 0),
                "attacking_third": yinfo.get("plays_attacking_third", 0),
                "middle_third": yinfo.get("plays_middle_third", 0),
                "defensive_third": yinfo.get("plays_defensive_third", 0),
            },
            "discipline": {
                "yellow_cards": yellows,
                "red_cards": reds,
                "fouls": max(spaia_compact["foul_count"], yinfo.get("fouls", 0)),
                "suffer_fouls": yinfo.get("suffer_fouls", 0),
            },
            "cbp": cbp,
            "spaia": spaia_compact,
            "yahoo": yinfo,
        }

        player_id = resolver.resolve(team_id, pname, number)
        records.append(
            {
                "match_id": match_id,
                "player_id": player_id,
                "player_name": pname,
                "team_id": team_id,
                "is_starter": is_starter,
                "minutes_played": minutes_played,
                "position": pos or yinfo.get("position", ""),
                "number": number,
                "goals": goals,
                "assists": assists,
                "xg": None,
                "xa": None,
                "touches": yinfo.get("touches") if yinfo else None,
                "duels_won": yinfo.get("tackles", spaia_compact["tackle_count"]),
                "distance_km": yinfo.get("distance_km"),
                "sprints": yinfo.get("sprints"),
                "avg_x": None,
                "avg_y": None,
                "cbp_points": cbp.get("total", 0.0),
                "raw_stats_json": json.dumps(raw_stats, ensure_ascii=False),
            },
        )
    return records


def _merge_from_yahoo_fallback(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    summary_data: Dict[str, Any],
    yahoo_lookup: Dict[str, Dict[str, Any]],
    cbp_lookup: Dict[str, Dict[str, float]],
    resolver: CanonicalPlayerResolver,
    pos_minutes_lookup: Dict[Tuple[str, str], Tuple[int, int]],
) -> List[Dict[str, Any]]:
    """SPAIA欠損時のフォールバック: Yahoo `/summary` メンバー表 + Yahoo `/stats` + FL CBP で構築する."""
    records: List[Dict[str, Any]] = []
    lineup = summary_data.get("lineup", {})
    for side_key, tid in (("home", home_team_id), ("away", away_team_id)):
        side_obj = lineup.get(side_key, {})
        starters = side_obj.get("starters", [])
        bench = side_obj.get("bench", [])
        for is_st, p_list in ((1, starters), (0, bench)):
            for m in p_list:
                pname = normalize_name(m.get("player_name", ""))
                pkey = make_name_key(pname)
                if not pkey:
                    continue
                number = safe_int(m.get("number", 0))
                pos = str(m.get("registered_pos", "")).strip()
                yinfo = yahoo_lookup.get(pkey, {})
                cbp = cbp_lookup.get(pkey, dict(EMPTY_CBP_DICT))

                est_st, est_min = pos_minutes_lookup.get((tid, pkey), (is_st, 90 if is_st else 0))
                if not is_st and est_min == 0 and yinfo.get("touches", 0) > 0:
                    est_min = 15

                raw_stats = {
                    "rating": None,
                    "max_speed_kmh": yinfo.get("max_speed_kmh"),
                    "distance_first_half": yinfo.get("distance_1h"),
                    "distance_second_half": yinfo.get("distance_2h"),
                    "sprints_first_half": yinfo.get("sprints_1h"),
                    "sprints_second_half": yinfo.get("sprints_2h"),
                    "plays_by_area": {
                        "total": yinfo.get("touches", 0),
                        "attacking_third": yinfo.get("plays_attacking_third", 0),
                        "middle_third": yinfo.get("plays_middle_third", 0),
                        "defensive_third": yinfo.get("plays_defensive_third", 0),
                    },
                    "discipline": {
                        "yellow_cards": yinfo.get("yellows", 0),
                        "red_cards": yinfo.get("reds", 0),
                        "fouls": yinfo.get("fouls", 0),
                        "suffer_fouls": yinfo.get("suffer_fouls", 0),
                    },
                    "cbp": cbp,
                    "spaia": {},
                    "yahoo": yinfo,
                }
                player_id = resolver.resolve(tid, pname, number)
                records.append(
                    {
                        "match_id": match_id,
                        "player_id": player_id,
                        "player_name": pname,
                        "team_id": tid,
                        "is_starter": est_st,
                        "minutes_played": est_min,
                        "position": pos or yinfo.get("position", ""),
                        "number": number,
                        "goals": yinfo.get("goals", 0),
                        "assists": yinfo.get("assists", 0),
                        "xg": None,
                        "xa": None,
                        "touches": yinfo.get("touches"),
                        "duels_won": yinfo.get("tackles", 0),
                        "distance_km": yinfo.get("distance_km"),
                        "sprints": yinfo.get("sprints"),
                        "avg_x": None,
                        "avg_y": None,
                        "cbp_points": cbp.get("total", 0.0),
                        "raw_stats_json": json.dumps(raw_stats, ensure_ascii=False),
                    },
                )
    return records


def build_match_player_and_team_records(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    home_score: int,
    away_score: int,
    spaia_data: Dict[str, Any],
    ystats_data: Dict[str, Any],
    flab_data: Dict[str, Any],
    summary_data: Dict[str, Any],
    resolver: CanonicalPlayerResolver,
    pos_minutes_lookup: Optional[Dict[Tuple[str, str], Tuple[int, int]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """1試合分の3ソースJSONから (player_records, team_records) を構築する."""
    yahoo_lookup = build_yahoo_player_lookup(ystats_data.get("player_stats", []))
    flab_matrix = flab_data.get("data", {}).get("cbp", {}).get("player_matrix", [])
    cbp_lookup, team_cbp_max = build_flab_cbp_lookup(flab_matrix)
    spaia_pstats = spaia_data.get("player_stats", [])

    if spaia_pstats:
        player_records = _merge_from_spaia_primary(
            match_id=match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_score=home_score,
            away_score=away_score,
            spaia_pstats=spaia_pstats,
            yahoo_lookup=yahoo_lookup,
            cbp_lookup=cbp_lookup,
            team_cbp_max=team_cbp_max,
            resolver=resolver,
        )
    else:
        player_records = _merge_from_yahoo_fallback(
            match_id=match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            summary_data=summary_data,
            yahoo_lookup=yahoo_lookup,
            cbp_lookup=cbp_lookup,
            resolver=resolver,
            pos_minutes_lookup=pos_minutes_lookup or {},
        )

    team_records = _build_team_stats_records(
        match_id=match_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        ystats_data=ystats_data,
        flab_data=flab_data,
        player_records=player_records,
    )
    return (player_records, team_records)


def _extract_yahoo_team_metric(metrics: Dict[str, Any], metric_key: str, team_label: str, is_home: bool) -> str:
    """Yahoo team_stats.metrics からホーム/アウェイ側の文字列値を取得する."""
    entry = metrics.get(metric_key, {})
    if not isinstance(entry, dict):
        return ""
    if team_label and team_label in entry:
        return str(entry[team_label])
    vals = list(entry.values())
    if is_home and len(vals) >= 1:
        return str(vals[0])
    if not is_home and len(vals) >= 2:
        return str(vals[1])
    return ""


def _build_team_stats_records(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    ystats_data: Dict[str, Any],
    flab_data: Dict[str, Any],
    player_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Yahooチームスタッツ + Football LAB xG/ヒートマップ + SPAIA進入数から team_match_stats 行を構築する."""
    ystats = ystats_data.get("team_stats", {})
    metrics = ystats.get("metrics", {}) if isinstance(ystats, dict) else {}
    h_label = ystats.get("home_team", "") if isinstance(ystats, dict) else ""
    a_label = ystats.get("away_team", "") if isinstance(ystats, dict) else ""

    flab_inner = flab_data.get("data", {})
    flab_stats = {s.get("name", ""): s for s in flab_inner.get("stats", []) if isinstance(s, dict)}
    xg_entry = flab_stats.get("ゴール期待値", {})
    home_xg = safe_float(xg_entry.get("home_val")) if xg_entry else None
    away_xg = safe_float(xg_entry.get("away_val")) if xg_entry else None

    timeline_blocks = flab_inner.get("timeline_blocks", [])
    heatmaps = flab_inner.get("heatmaps", [])

    out: List[Dict[str, Any]] = []
    for is_home, tid, tlabel in ((True, home_team_id, h_label), (False, away_team_id, a_label)):
        possession = safe_float(_extract_yahoo_team_metric(metrics, "保持率", tlabel, is_home))
        shots = safe_int(_extract_yahoo_team_metric(metrics, "シュート", tlabel, is_home))
        shots_ot = safe_int(_extract_yahoo_team_metric(metrics, "枠内シュート", tlabel, is_home))
        dist_km = safe_float(_extract_yahoo_team_metric(metrics, "走行距離", tlabel, is_home))
        sprints = safe_int(_extract_yahoo_team_metric(metrics, "スプリント", tlabel, is_home))

        pass_raw = _extract_yahoo_team_metric(metrics, "パス（成功率）", tlabel, is_home)
        pass_rate = 0.0
        m_pct = re.search(r"\(([0-9.]+)%\)", pass_raw)
        if m_pct:
            pass_rate = safe_float(m_pct.group(1))

        t_players = [p for p in player_records if p["team_id"] == tid]
        pa_total = 0
        m30_total = 0
        for p in t_players:
            sp_d = json.loads(p["raw_stats_json"]).get("spaia", {})
            pa_total += safe_int(sp_d.get("pa_entries"))
            m30_total += safe_int(sp_d.get("m30_entries"))

        heat_obj = heatmaps[0] if (is_home and len(heatmaps) >= 1) else (heatmaps[1] if (not is_home and len(heatmaps) >= 2) else {})
        raw_team = {
            "pa_entries": pa_total,
            "m30_entries": m30_total,
            "pass_success_rate": pass_rate,
            "timeline_blocks": timeline_blocks,
            "heatmaps": heat_obj,
        }
        out.append(
            {
                "match_id": match_id,
                "team_id": tid,
                "period": "ALL",
                "game_state": "ALL",
                "possession": possession,
                "xg": home_xg if is_home else away_xg,
                "shots": shots,
                "shots_on_target": shots_ot,
                "big_chances": 0,
                "final_third_passes": m30_total,
                "total_distance_km": dist_km,
                "sprints": sprints,
                "raw_stats_json": json.dumps(raw_team, ensure_ascii=False),
            },
        )
    return out


def _load_json_or_empty(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ingest_all_2026_player_and_team_stats(
    db_path: Path = DEFAULT_DB_PATH,
    yahoo_dir: Path = DEFAULT_YAHOO_DIR,
    spaia_dir: Path = DEFAULT_SPAIA_DIR,
    flab_dir: Path = DEFAULT_FLAB_DIR,
) -> Dict[str, Any]:
    """2026年J1全120試合の3ソース生JSONを統合し、player_match_stats & team_match_stats にUPSERTする."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        resolver = CanonicalPlayerResolver(conn)

        pos_minutes_lookup: Dict[Tuple[str, str, str], Tuple[int, int]] = {}
        pmp_exists = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='player_match_positions'",
        ).fetchone()
        if pmp_exists:
            for mid_r, tid_r, pname_r, st_r, min_r in cur.execute(
                "SELECT match_id, team_id, player_name, is_starter, minutes_estimated FROM player_match_positions",
            ).fetchall():
                pos_minutes_lookup[(mid_r, tid_r, make_name_key(pname_r))] = (int(st_r), int(min_r))

        matches = cur.execute(
            """
            SELECT match_id, home_team_id, away_team_id, COALESCE(home_score, 0), COALESCE(away_score, 0)
            FROM matches
            WHERE season = 2026
            ORDER BY matchweek, date, match_id
            """,
        ).fetchall()

        insert_player_sql = """
        INSERT INTO player_match_stats (
            match_id, player_id, player_name, team_id, is_starter, minutes_played,
            position, number, goals, assists, xg, xa, touches, duels_won,
            distance_km, sprints, avg_x, avg_y, cbp_points, raw_stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id, player_name, team_id) DO UPDATE SET
            player_id = excluded.player_id,
            is_starter = excluded.is_starter,
            minutes_played = excluded.minutes_played,
            position = excluded.position,
            number = excluded.number,
            goals = excluded.goals,
            assists = excluded.assists,
            touches = excluded.touches,
            duels_won = excluded.duels_won,
            distance_km = excluded.distance_km,
            sprints = excluded.sprints,
            cbp_points = excluded.cbp_points,
            raw_stats_json = excluded.raw_stats_json;
        """

        insert_team_sql = """
        INSERT INTO team_match_stats (
            match_id, team_id, period, game_state, possession, xg, shots,
            shots_on_target, big_chances, final_third_passes, total_distance_km,
            sprints, raw_stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id, team_id, period, game_state) DO UPDATE SET
            possession = excluded.possession,
            xg = COALESCE(excluded.xg, team_match_stats.xg),
            shots = excluded.shots,
            shots_on_target = excluded.shots_on_target,
            final_third_passes = excluded.final_third_passes,
            total_distance_km = excluded.total_distance_km,
            sprints = excluded.sprints,
            raw_stats_json = excluded.raw_stats_json;
        """

        ingested_matches = 0
        total_players = 0
        total_teams = 0

        for match_id, h_id, a_id, h_score, a_score in matches:
            spaia_d = _load_json_or_empty(spaia_dir / f"{match_id}_player_stats.json")
            ystats_d = _load_json_or_empty(yahoo_dir / f"{match_id}_stats.json")
            flab_d = _load_json_or_empty(flab_dir / f"{match_id}.json")
            sum_d = _load_json_or_empty(yahoo_dir / f"{match_id}_summary.json")

            if not spaia_d.get("player_stats") and not ystats_d.get("player_stats"):
                continue

            match_pos_lookup = {
                (tid_k, nkey): val
                for (m_k, tid_k, nkey), val in pos_minutes_lookup.items()
                if m_k == match_id
            }
            p_recs, t_recs = build_match_player_and_team_records(
                match_id=match_id,
                home_team_id=h_id,
                away_team_id=a_id,
                home_score=int(h_score),
                away_score=int(a_score),
                spaia_data=spaia_d,
                ystats_data=ystats_d,
                flab_data=flab_d,
                summary_data=sum_d,
                resolver=resolver,
                pos_minutes_lookup=match_pos_lookup,
            )

            if not p_recs:
                continue

            cur.execute("DELETE FROM player_match_stats WHERE match_id = ?;", (match_id,))
            cur.executemany(
                insert_player_sql,
                [
                    (
                        r["match_id"],
                        r["player_id"],
                        r["player_name"],
                        r["team_id"],
                        r["is_starter"],
                        r["minutes_played"],
                        r["position"],
                        r["number"],
                        r["goals"],
                        r["assists"],
                        r["xg"],
                        r["xa"],
                        r["touches"],
                        r["duels_won"],
                        r["distance_km"],
                        r["sprints"],
                        r["avg_x"],
                        r["avg_y"],
                        r["cbp_points"],
                        r["raw_stats_json"],
                    )
                    for r in p_recs
                ],
            )

            if ystats_d.get("team_stats", {}).get("metrics"):
                cur.executemany(
                    insert_team_sql,
                    [
                        (
                            tr["match_id"],
                            tr["team_id"],
                            tr["period"],
                            tr["game_state"],
                            tr["possession"],
                            tr["xg"],
                            tr["shots"],
                            tr["shots_on_target"],
                            tr["big_chances"],
                            tr["final_third_passes"],
                            tr["total_distance_km"],
                            tr["sprints"],
                            tr["raw_stats_json"],
                        )
                        for tr in t_recs
                    ],
                )
                total_teams += len(t_recs)

            ingested_matches += 1
            total_players += len(p_recs)

        conn.commit()
    finally:
        conn.close()

    return {
        "ingested_matches": ingested_matches,
        "total_player_rows": total_players,
        "total_team_rows": total_teams,
    }

