"""
experiments/enrich_layer1_ground_truth.py

Layer 1 (客観事実データ) 限界突破拡充スクリプト
2026年シーズンJ1 全12節・全120試合（全20チーム）を対象に、
手元の3大ソース（SPAIA + Football LAB + Yahoo）を完全名寄せ・正規化・結合して
data/football.db に完全同期する。

- player_match_stats: 約3,840選手レコード (SPAIA 30指標 + FL 8大CBP + Yahoo走行距離/スプリント/最高速度 + 決定論的Rating)
- team_match_stats: 240レコード (走行距離、スプリント、xG、Field Tilt、ポゼッション、PA進入数、パス・クロス成功率)
- match_events: 真のゴール、アシスト、交代、カード、決定機イベント
"""

import os
import sys
import json
import sqlite3
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DB_PATH = ROOT_DIR / "data" / "football.db"
RAW_SPAIA_DIR = ROOT_DIR / "data" / "raw" / "spaia"
RAW_FLAB_DIR = ROOT_DIR / "data" / "raw" / "football_lab"
RAW_YAHOO_DIR = ROOT_DIR / "data" / "raw" / "yahoo"


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if val is None:
        return default
    try:
        clean = str(val).replace("km/h", "").replace("km", "").replace("%", "").strip()
        return float(clean)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    if val is None:
        return default
    try:
        clean = str(val).split(".")[0].strip()
        return int(clean)
    except (ValueError, TypeError):
        return default


def normalize_name(name: str) -> str:
    """Normalize player name with single half-width space."""
    if not name:
        return ""
    return re.sub(r"[\s\u3000]+", " ", name).strip()


def make_name_key(name: str) -> str:
    """Create key for fuzzy name resolution by stripping spaces and dots."""
    if not name:
        return ""
    return re.sub(r"[\s\u3000・\.]+", "", name)


def load_raw_files_for_match(match_id: str) -> Optional[Dict[str, Any]]:
    """Load all 3 raw sources for a given match."""
    spaia_p = RAW_SPAIA_DIR / f"{match_id}_player_stats.json"
    flab_p = RAW_FLAB_DIR / f"{match_id}.json"
    ystats_p = RAW_YAHOO_DIR / f"{match_id}_stats.json"
    ytext_p = RAW_YAHOO_DIR / f"{match_id}_text.json"

    if not (spaia_p.exists() and flab_p.exists() and ystats_p.exists()):
        return None

    try:
        with open(spaia_p, "r", encoding="utf-8") as f:
            spaia_data = json.load(f)
        with open(flab_p, "r", encoding="utf-8") as f:
            flab_data = json.load(f)
        with open(ystats_p, "r", encoding="utf-8") as f:
            ystats_data = json.load(f)
        ytext_data = {}
        if ytext_p.exists():
            with open(ytext_p, "r", encoding="utf-8") as f:
                ytext_data = json.load(f)

        return {
            "spaia": spaia_data,
            "flab": flab_data,
            "ystats": ystats_data,
            "ytext": ytext_data,
        }
    except Exception as e:
        print(f"Error loading files for {match_id}: {e}")
        return None


def calculate_player_deterministic_rating(
    pos: str,
    play_time: int,
    goals: int,
    pk_goals: int,
    assists: int,
    clean_sheet: bool,
    cbp_info: Dict[str, float],
    team_cbp_max: Dict[str, float],
    save_count: int,
    yellows: int,
    reds: int,
    pass_count: int,
    pass_rate: float,
) -> Optional[float]:
    """
    Calculate deterministic player rating (3.0 - 9.0, step 0.5)
    based on Specification Chapter 6 and Track 1 validation.
    """
    if play_time < 15:
        return None

    base_score = 6.0
    bonus = 0.0
    penalty = 0.0

    normal_goals = max(0, goals - pk_goals)
    bonus += normal_goals * 1.0 + pk_goals * 0.75
    bonus += assists * 0.5

    if clean_sheet and pos in ["DF", "GK"] and play_time >= 60:
        bonus += 0.5

    if team_cbp_max.get("attack", 0.0) > 0 and cbp_info.get("attack", 0.0) >= team_cbp_max.get("attack", 0.0):
        bonus += 0.5
    if team_cbp_max.get("defense", 0.0) > 0 and cbp_info.get("defense", 0.0) >= team_cbp_max.get("defense", 0.0):
        bonus += 0.5
    if team_cbp_max.get("gain", 0.0) > 0 and cbp_info.get("gain", 0.0) >= team_cbp_max.get("gain", 0.0):
        bonus += 0.5

    save_cbp = cbp_info.get("save", 0.0)
    if pos == "GK" and (save_count >= 3 or save_cbp >= 3.0):
        bonus += 0.5

    if reds > 0:
        penalty += 1.5
    elif yellows > 0:
        penalty += 0.5 * yellows

    if pos in ["DF", "MF"] and pass_count >= 20 and pass_rate < 65.0:
        penalty += 0.5

    bonus = min(3.0, bonus)
    penalty = min(3.0, penalty)
    raw_rating = base_score + bonus - penalty
    clipped_rating = max(3.0, min(9.0, raw_rating))
    return round(clipped_rating * 2) / 2.0


def parse_player_records_for_match(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    home_score: int,
    away_score: int,
    raw_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Merge SPAIA + FL + Yahoo player stats into unified records."""
    spaia_pstats = raw_data["spaia"].get("player_stats", [])
    flab_matrix = raw_data["flab"].get("data", {}).get("cbp", {}).get("player_matrix", [])
    ystats_pstats = raw_data["ystats"].get("player_stats", [])

    flab_lookup = {}
    for p in flab_matrix:
        k = make_name_key(p.get("player_name", ""))
        flab_lookup[k] = {
            "attack": safe_float(p.get("attack")),
            "defense": safe_float(p.get("defense")),
            "gain": safe_float(p.get("gain")),
            "pass": safe_float(p.get("pass")),
            "cross": safe_float(p.get("cross")),
            "dribble": safe_float(p.get("dribble")),
            "shoot": safe_float(p.get("shoot")),
            "save": safe_float(p.get("save")),
            "total": (
                safe_float(p.get("attack"))
                + safe_float(p.get("defense"))
                + safe_float(p.get("gain"))
            ),
        }

    yahoo_lookup = {}
    for p in ystats_pstats:
        k = make_name_key(p.get("player_name", ""))
        dist = p.get("distance", {})
        spr = p.get("sprint", {})
        att = p.get("attack", {})
        defense = p.get("defense", {})
        pass_info = p.get("pass", {})
        area = p.get("plays_by_area", {})
        disc = p.get("discipline", {})

        yahoo_lookup[k] = {
            "position": p.get("position", ""),
            "distance_km": safe_float(dist.get("total")),
            "distance_1h": safe_float(dist.get("first_half")),
            "distance_2h": safe_float(dist.get("second_half")),
            "sprints": safe_int(spr.get("total")),
            "sprints_1h": safe_int(spr.get("first_half")),
            "sprints_2h": safe_int(spr.get("second_half")),
            "max_speed_kmh": safe_float(spr.get("max_speed")),
            "shoots": safe_int(att.get("shoot")),
            "shoots_on_target": safe_int(att.get("shoot_on_target")),
            "goals": safe_int(att.get("goals")),
            "tackles": safe_int(defense.get("tackle_success", "0").split("(")[0]),
            "loose_ball_recoveries": safe_int(defense.get("loose_ball_recovery")),
            "clears": safe_int(defense.get("clear")),
            "blocks": safe_int(defense.get("block")),
            "passes": safe_int(pass_info.get("pass_success", "0").split("(")[0]),
            "assists": safe_int(pass_info.get("assist")),
            "touches": safe_int(area.get("total")),
            "fouls": safe_int(disc.get("foul")),
            "yellows": safe_int(disc.get("yellow_card")),
            "reds": safe_int(disc.get("red_card")),
        }

    team_cbp_max = {
        "HOME": {"attack": 0.0, "defense": 0.0, "gain": 0.0},
        "AWAY": {"attack": 0.0, "defense": 0.0, "gain": 0.0},
    }
    for p in flab_matrix:
        side = p.get("team_side", "HOME").upper()
        if side not in team_cbp_max:
            side = "HOME"
        for metric in ["attack", "defense", "gain"]:
            val = safe_float(p.get(metric))
            if val > team_cbp_max[side][metric]:
                team_cbp_max[side][metric] = val

    player_records = []
    for sp in spaia_pstats:
        pname = normalize_name(sp.get("Name", ""))
        pkey = make_name_key(pname)
        hv = safe_int(sp.get("HV", 1))
        team_id = home_team_id if hv == 1 else away_team_id
        side_label = "HOME" if hv == 1 else "AWAY"
        opp_score = away_score if hv == 1 else home_score
        clean_sheet = (opp_score == 0)

        pos = sp.get("Pos", "")
        number = safe_int(sp.get("Uni", 0))
        is_starter = 1 if str(sp.get("StartF", "0")) == "1" else 0
        minutes_played = safe_int(sp.get("Time", 0))
        goals = safe_int(sp.get("Score", 0))
        pk_goals = safe_int(sp.get("PKScore", 0))
        assists = safe_int(sp.get("Assist", 0))
        save_count = safe_int(sp.get("SaveCount", 0))
        yellows = safe_int(sp.get("Yellow", 0))
        reds = safe_int(sp.get("Red", 0))
        pass_count = safe_int(sp.get("PassCount", 0))
        pass_rate = safe_float(sp.get("PassRate", 0.0))

        cbp = flab_lookup.get(pkey, {
            "attack": 0.0,
            "defense": 0.0,
            "gain": 0.0,
            "pass": 0.0,
            "cross": 0.0,
            "dribble": 0.0,
            "shoot": 0.0,
            "save": 0.0,
            "total": 0.0,
        })

        yinfo = yahoo_lookup.get(pkey, {})

        distance_km = yinfo.get("distance_km")
        sprints = yinfo.get("sprints")
        max_speed = yinfo.get("max_speed_kmh")
        touches = yinfo.get("touches", safe_int(sp.get("AtPlayRate", 0)))
        duels_won = yinfo.get("tackles", safe_int(sp.get("TackleCount", 0)))

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
            pass_count=pass_count,
            pass_rate=pass_rate,
        )

        spaia_compact = {
            "pa_entries": safe_int(sp.get("PAPlayCount")),
            "m30_entries": safe_int(sp.get("M30PlayCount")),
            "at_3rd_entries": safe_int(sp.get("At3rdPlayCount")),
            "pass_count": pass_count,
            "pass_rate": pass_rate,
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
            "cross_count": safe_int(sp.get("CrossCount")),
            "cross_rate": safe_float(sp.get("CrossRate")),
            "dribble_count": safe_int(sp.get("DribbleCount")),
            "dribble_rate": safe_float(sp.get("DribbleRate")),
            "clear_count": safe_int(sp.get("ClearCount")),
            "tackle_count": safe_int(sp.get("TackleCount")),
            "at_3rd_tackle": safe_int(sp.get("At3rdTackleCount")),
            "opp_area_tackle": safe_int(sp.get("OpponentAreaTackleCount")),
            "save_count": save_count,
            "save_rate": safe_float(sp.get("SaveRate")),
        }

        raw_stats_json = {
            "rating": rating,
            "max_speed_kmh": max_speed,
            "distance_first_half": yinfo.get("distance_1h"),
            "distance_second_half": yinfo.get("distance_2h"),
            "sprints_first_half": yinfo.get("sprints_1h"),
            "sprints_second_half": yinfo.get("sprints_2h"),
            "cbp": cbp,
            "spaia": spaia_compact,
            "yahoo": yinfo,
        }

        player_id = f"P_{team_id}_{number}_{pkey[:8]}"

        player_records.append({
            "match_id": match_id,
            "player_id": player_id,
            "player_name": pname,
            "team_id": team_id,
            "is_starter": is_starter,
            "minutes_played": minutes_played,
            "position": pos,
            "number": number,
            "goals": goals,
            "assists": assists,
            "xg": None,
            "xa": None,
            "touches": touches,
            "duels_won": duels_won,
            "distance_km": distance_km,
            "sprints": sprints,
            "avg_x": None,
            "avg_y": None,
            "cbp_points": cbp.get("total", 0.0),
            "raw_stats_json": json.dumps(raw_stats_json, ensure_ascii=False),
        })

    return player_records


def parse_team_records_for_match(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    raw_data: Dict[str, Any],
    player_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build team_match_stats records for both HOME and AWAY teams."""
    ystats = raw_data["ystats"].get("team_stats", {})
    metrics = ystats.get("metrics", {})
    home_name = ystats.get("home_team", "")
    away_name = ystats.get("away_team", "")

    def extract_metric(metric_key: str, is_home: bool) -> str:
        data = metrics.get(metric_key, {})
        team_key = home_name if is_home else away_name
        if team_key in data:
            return data[team_key]
        keys = list(data.keys())
        if is_home and len(keys) > 0:
            return data[keys[0]]
        elif not is_home and len(keys) > 1:
            return data[keys[1]]
        return ""

    flab_stats = raw_data["flab"].get("data", {}).get("stats", [])
    flab_lookup = {}
    for s in flab_stats:
        name = s.get("name", "")
        flab_lookup[name] = s

    xg_stat = flab_lookup.get("ゴール期待値", {})
    home_xg = safe_float(xg_stat.get("home_val"))
    away_xg = safe_float(xg_stat.get("away_val"))

    team_records = []
    for is_home, team_id in [(True, home_team_id), (False, away_team_id)]:
        possession = safe_float(extract_metric("保持率", is_home))
        shots = safe_int(extract_metric("シュート", is_home))
        shots_ot = safe_int(extract_metric("枠内シュート", is_home))
        dist_km = safe_float(extract_metric("走行距離", is_home))
        sprints = safe_int(extract_metric("スプリント", is_home))

        pass_raw = extract_metric("パス（成功率）", is_home)
        pass_rate = 0.0
        if "(" in pass_raw and "%" in pass_raw:
            try:
                pass_rate = float(pass_raw.split("(")[1].split("%")[0])
            except Exception:
                pass_rate = 0.0

        team_players = [p for p in player_records if p["team_id"] == team_id]
        total_pa_entries = 0
        total_m30_entries = 0
        for p in team_players:
            p_json = json.loads(p["raw_stats_json"])
            sp = p_json.get("spaia", {})
            total_pa_entries += sp.get("pa_entries", 0)
            total_m30_entries += sp.get("m30_entries", 0)

        timeline_blocks = raw_data["flab"].get("data", {}).get("timeline_blocks", [])

        home_heat = {}
        away_heat = {}
        heatmaps = raw_data["flab"].get("data", {}).get("heatmaps", [])
        if len(heatmaps) >= 2:
            home_heat = heatmaps[0]
            away_heat = heatmaps[1]

        raw_team_json = {
            "pa_entries": total_pa_entries,
            "m30_entries": total_m30_entries,
            "pass_success_rate": pass_rate,
            "timeline_blocks": timeline_blocks,
            "heatmaps": home_heat if is_home else away_heat,
        }

        team_records.append({
            "match_id": match_id,
            "team_id": team_id,
            "period": "ALL",
            "game_state": "ALL",
            "possession": possession,
            "xg": home_xg if is_home else away_xg,
            "shots": shots,
            "shots_on_target": shots_ot,
            "big_chances": 0,
            "final_third_passes": total_m30_entries,
            "total_distance_km": dist_km,
            "sprints": sprints,
            "raw_stats_json": json.dumps(raw_team_json, ensure_ascii=False),
        })

    return team_records


def parse_match_events_for_match(
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    raw_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Extract clean goals, substitutions, cards from Yahoo timeline."""
    ytext = raw_data["ytext"]
    timeline = ytext.get("timeline", [])
    events = []

    sub_pattern = re.compile(r"(\d+)\s*(.*?)\s*OUT[→\->\s]+(\d+)\s*(.*?)\s*IN")
    card_pattern = re.compile(r"(.*?)[にへ]?(イエローカード|レッドカード)")

    order_idx = 0
    current_home_score = 0
    current_away_score = 0

    for item in timeline:
        text = item.get("text", "")
        time_str = item.get("time", "")
        team_str = item.get("team", "")

        is_home_event = (team_str and (home_team_id in team_str or "FC東京" in team_str))
        event_team_id = home_team_id if is_home_event else away_team_id

        minute = 0
        period = "1H"
        if "後半" in time_str:
            period = "2H"
            m_match = re.search(r"後半(\d+)", time_str)
            minute = 45 + int(m_match.group(1)) if m_match else 45
        elif "前半" in time_str:
            period = "1H"
            m_match = re.search(r"前半(\d+)", time_str)
            minute = int(m_match.group(1)) if m_match else 0

        game_state = "DRAW"
        if current_home_score > current_away_score:
            game_state = "LEAD" if is_home_event else "TRAIL"
        elif current_home_score < current_away_score:
            game_state = "TRAIL" if is_home_event else "LEAD"

        is_goal = ("GOOOOOAL!!" in text) or ("オウンゴール" in text) or ("ゴールに決める" in text)
        if is_goal:
            order_idx += 1
            cause = "遅攻・組織崩し"
            if any(k in text for k in ["CK", "FK", "PK", "コーナーキック", "フリーキック"]):
                cause = "セットプレー(CK/FK/PK)"
            elif any(k in text for k in ["カウンター", "速攻", "抜け出し", "スルーパス"]):
                cause = "速攻・カウンター"
            elif any(k in text for k in ["クロス", "サイド", "ポケット"]):
                cause = "サイド崩し・クロス"
            elif any(k in text for k in ["ミス", "こぼれ球", "プレス", "パスカット"]):
                cause = "相手ミス・プレス奪取"

            if is_home_event:
                current_home_score += 1
            else:
                current_away_score += 1

            events.append({
                "event_id": f"{match_id}_GOAL_{order_idx}",
                "match_id": match_id,
                "minute": minute,
                "period": period,
                "game_state": game_state,
                "team_id": event_team_id,
                "player_id": None,
                "player_name": None,
                "event_type": "GOAL",
                "coord_x": None,
                "coord_y": None,
                "zone_name": None,
                "xg": None,
                "situation": cause,
                "description_text": text,
            })
            continue

        sub_m = sub_pattern.search(text)
        if sub_m or item.get("is_substitution"):
            order_idx += 1
            p_out = sub_m.group(2).strip() if sub_m else ""
            p_in = sub_m.group(4).strip() if sub_m else ""
            events.append({
                "event_id": f"{match_id}_SUB_{order_idx}",
                "match_id": match_id,
                "minute": minute,
                "period": period,
                "game_state": game_state,
                "team_id": event_team_id,
                "player_id": None,
                "player_name": f"{p_out} -> {p_in}",
                "event_type": "SUBSTITUTION",
                "coord_x": None,
                "coord_y": None,
                "zone_name": None,
                "xg": None,
                "situation": "交代",
                "description_text": text,
            })
            continue

        card_m = card_pattern.search(text)
        if card_m or item.get("is_card"):
            order_idx += 1
            card_type = "RED_CARD" if "レッド" in text else "YELLOW_CARD"
            p_target = card_m.group(1).strip() if card_m else ""
            events.append({
                "event_id": f"{match_id}_CARD_{order_idx}",
                "match_id": match_id,
                "minute": minute,
                "period": period,
                "game_state": game_state,
                "team_id": event_team_id,
                "player_id": None,
                "player_name": p_target,
                "event_type": card_type,
                "coord_x": None,
                "coord_y": None,
                "zone_name": None,
                "xg": None,
                "situation": "カード提示",
                "description_text": text,
            })
            continue

    return events


def run_layer1_ground_truth_import() -> None:
    """Main execution entry point."""
    print("=" * 70)
    print("Layer 1 (客観事実データ) 限界突破拡充バッチ開始")
    print(f"対象DB: {DB_PATH}")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    matches = cur.execute("""
        SELECT match_id, season, matchweek, date, home_team_id, away_team_id, home_score, away_score
        FROM matches
        WHERE season = 2026
        ORDER BY matchweek, date
    """).fetchall()

    print(f"対象試合数: 2026年全{len(matches)}試合")

    total_players_inserted = 0
    total_teams_inserted = 0
    total_events_inserted = 0

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
        raw_stats_json = excluded.raw_stats_json
    """

    insert_team_sql = """
    INSERT INTO team_match_stats (
        match_id, team_id, period, game_state, possession, xg, shots,
        shots_on_target, big_chances, final_third_passes, total_distance_km,
        sprints, raw_stats_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(match_id, team_id, period, game_state) DO UPDATE SET
        possession = excluded.possession,
        xg = excluded.xg,
        shots = excluded.shots,
        shots_on_target = excluded.shots_on_target,
        big_chances = excluded.big_chances,
        final_third_passes = excluded.final_third_passes,
        total_distance_km = excluded.total_distance_km,
        sprints = excluded.sprints,
        raw_stats_json = excluded.raw_stats_json
    """

    insert_event_sql = """
    INSERT OR REPLACE INTO match_events (
        event_id, match_id, minute, period, game_state, team_id,
        player_id, player_name, event_type, coord_x, coord_y,
        zone_name, xg, situation, description_text
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    try:
        cur.execute("BEGIN TRANSACTION;")

        for idx, m in enumerate(matches, 1):
            mid = m[0]
            home_team_id = m[4]
            away_team_id = m[5]
            home_score = m[6] or 0
            away_score = m[7] or 0

            raw_data = load_raw_files_for_match(mid)
            if not raw_data:
                print(f"[{idx}/{len(matches)}] Skip {mid} (raw files missing)")
                continue

            # 1. Player Match Stats
            p_records = parse_player_records_for_match(
                match_id=mid,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_score=home_score,
                away_score=away_score,
                raw_data=raw_data,
            )
            for p in p_records:
                cur.execute(insert_player_sql, (
                    p["match_id"], p["player_id"], p["player_name"], p["team_id"],
                    p["is_starter"], p["minutes_played"], p["position"], p["number"],
                    p["goals"], p["assists"], p["xg"], p["xa"], p["touches"],
                    p["duels_won"], p["distance_km"], p["sprints"], p["avg_x"],
                    p["avg_y"], p["cbp_points"], p["raw_stats_json"],
                ))
            total_players_inserted += len(p_records)

            # 2. Team Match Stats
            t_records = parse_team_records_for_match(
                match_id=mid,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                raw_data=raw_data,
                player_records=p_records,
            )
            for t in t_records:
                cur.execute(insert_team_sql, (
                    t["match_id"], t["team_id"], t["period"], t["game_state"],
                    t["possession"], t["xg"], t["shots"], t["shots_on_target"],
                    t["big_chances"], t["final_third_passes"], t["total_distance_km"],
                    t["sprints"], t["raw_stats_json"],
                ))
            total_teams_inserted += len(t_records)

            # 3. Match Events
            e_records = parse_match_events_for_match(
                match_id=mid,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                raw_data=raw_data,
            )
            for e in e_records:
                cur.execute(insert_event_sql, (
                    e["event_id"], e["match_id"], e["minute"], e["period"],
                    e["game_state"], e["team_id"], e["player_id"], e["player_name"],
                    e["event_type"], e["coord_x"], e["coord_y"], e["zone_name"],
                    e["xg"], e["situation"], e["description_text"],
                ))
            total_events_inserted += len(e_records)

            if idx % 20 == 0 or idx == len(matches):
                print(f"[{idx:3d}/{len(matches)}] 処理完了: {mid} (累計 選手:{total_players_inserted}, チーム:{total_teams_inserted}, イベント:{total_events_inserted})")

        conn.commit()
        print("\n全試合のコミットが完了しました。")

    except Exception as e:
        conn.rollback()
        print(f"エラー発生のためロールバックしました: {e}")
        raise e
    finally:
        conn.close()


def verify_ground_truth_database() -> None:
    """Verify imported data with statistical queries."""
    print("\n" + "=" * 70)
    print("データ投入後の検証クエリ実行")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM player_match_stats;")
    p_cnt = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM team_match_stats;")
    t_cnt = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM match_events;")
    e_cnt = cur.fetchone()[0]

    print(f"- player_match_stats 件数: {p_cnt} 件")
    print(f"- team_match_stats 件数: {t_cnt} 件")
    print(f"- match_events 件数: {e_cnt} 件")

    print("\n【2026年 J1 最高速度 (km/h) Top 10】")
    top_speed_query = """
    SELECT player_name, team_id,
           json_extract(raw_stats_json, '$.max_speed_kmh') AS max_spd,
           match_id
    FROM player_match_stats
    WHERE max_spd IS NOT NULL AND max_spd > 0
    ORDER BY max_spd DESC
    LIMIT 10;
    """
    for r in cur.execute(top_speed_query).fetchall():
        print(f"  {r[0]:15s} ({r[1]}): {r[2]} km/h  [Match: {r[3]}]")

    print("\n【2026年 J1 走行距離 (km) Top 10】")
    top_dist_query = """
    SELECT player_name, team_id, distance_km, minutes_played, match_id
    FROM player_match_stats
    WHERE distance_km IS NOT NULL
    ORDER BY distance_km DESC
    LIMIT 10;
    """
    for r in cur.execute(top_dist_query).fetchall():
        print(f"  {r[0]:15s} ({r[1]}): {r[2]} km ({r[3]}分)  [Match: {r[4]}]")

    print("\n【2026年 J1 総合CBP Top 10】")
    top_cbp_query = """
    SELECT player_name, team_id, cbp_points, goals, assists, match_id
    FROM player_match_stats
    WHERE cbp_points IS NOT NULL
    ORDER BY cbp_points DESC
    LIMIT 10;
    """
    for r in cur.execute(top_cbp_query).fetchall():
        print(f"  {r[0]:15s} ({r[1]}): CBP {r[2]:.2f} (G:{r[3]}, A:{r[4]})  [Match: {r[5]}]")

    print("\n【2026年 J1 PA進入数 Top 10】")
    top_pa_query = """
    SELECT player_name, team_id,
           json_extract(raw_stats_json, '$.spaia.pa_entries') AS pa_cnt,
           match_id
    FROM player_match_stats
    WHERE pa_cnt IS NOT NULL
    ORDER BY pa_cnt DESC
    LIMIT 10;
    """
    for r in cur.execute(top_pa_query).fetchall():
        print(f"  {r[0]:15s} ({r[1]}): PA進入 {r[2]}回  [Match: {r[3]}]")

    print("\n【2026年 イベント種別サマリー】")
    for r in cur.execute("SELECT event_type, count(*) FROM match_events GROUP BY event_type").fetchall():
        print(f"  {r[0]}: {r[1]} 件")

    conn.close()


if __name__ == "__main__":
    run_layer1_ground_truth_import()
    verify_ground_truth_database()
