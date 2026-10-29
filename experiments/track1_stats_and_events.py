"""
Track 1: Stats, Momentum, and Goal/Conceded Causal Structure Verification
- (12) Player Season Average Ratings (Top 5 / Worst) and MOM Count
- (8) 12 Matches Trend: Points, Goals/Conceded, xG, Field Tilt, Distance
- (9) 37 Goal/Conceded Events Structural Causal Classification
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DB_PATH = ROOT_DIR / "data" / "football.db"
STRUCTURED_DIR = ROOT_DIR / "data" / "structured"
RAW_SPAIA_DIR = ROOT_DIR / "data" / "raw" / "spaia"
RAW_FLAB_DIR = ROOT_DIR / "data" / "raw" / "football_lab"
RAW_YAHOO_DIR = ROOT_DIR / "data" / "raw" / "yahoo"

FCT_MATCHES_2026 = [
    {"match_id": "20260808_FCT_ZEL", "date": "2026-08-08", "home": "FCT", "away": "ZEL", "h_score": 1, "a_score": 5, "round": 1},
    {"match_id": "20260815_VOB_FCT", "date": "2026-08-15", "home": "VOB", "away": "FCT", "h_score": 2, "a_score": 2, "round": 2},
    {"match_id": "20260821_FCT_JEF", "date": "2026-08-21", "home": "FCT", "away": "JEF", "h_score": 2, "a_score": 0, "round": 3},
    {"match_id": "20260829_VVN_FCT", "date": "2026-08-29", "home": "VVN", "away": "FCT", "h_score": 0, "a_score": 3, "round": 4},
    {"match_id": "20260902_PUL_FCT", "date": "2026-09-02", "home": "PUL", "away": "FCT", "h_score": 1, "a_score": 1, "round": 5},
    {"match_id": "20260906_FCT_SAN", "date": "2026-09-06", "home": "FCT", "away": "SAN", "h_score": 2, "a_score": 0, "round": 6},
    {"match_id": "20260912_GAM_FCT", "date": "2026-09-12", "home": "GAM", "away": "FCT", "h_score": 0, "a_score": 2, "round": 7},
    {"match_id": "20260919_FCT_NAG", "date": "2026-09-19", "home": "FCT", "away": "NAG", "h_score": 1, "a_score": 0, "round": 8},
    {"match_id": "20261010_FCT_URA", "date": "2026-10-10", "home": "FCT", "away": "URA", "h_score": 3, "a_score": 0, "round": 9},
    {"match_id": "20261017_VER_FCT", "date": "2026-10-17", "home": "VER", "away": "FCT", "h_score": 0, "a_score": 4, "round": 10},
    {"match_id": "20261021_FCT_REY", "date": "2026-10-21", "home": "FCT", "away": "REY", "h_score": 0, "a_score": 0, "round": 11},
    {"match_id": "20261025_FCT_MIT", "date": "2026-10-25", "home": "FCT", "away": "MIT", "h_score": 6, "a_score": 0, "round": 12},
]


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def calculate_match_player_ratings(match_info: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Calculate deterministic player ratings and MOM for FC Tokyo based on Specification Chapter 6."""
    mid = match_info["match_id"]
    is_home = (match_info["home"] == "FCT")
    fct_score = match_info["h_score"] if is_home else match_info["a_score"]
    opp_score = match_info["a_score"] if is_home else match_info["h_score"]
    clean_sheet = (opp_score == 0)

    spaia_path = RAW_SPAIA_DIR / f"{mid}_player_stats.json"
    spaia_players = []
    if spaia_path.exists():
        with open(spaia_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            spaia_players = data.get("player_stats", [])

    flab_path = RAW_FLAB_DIR / f"{mid}.json"
    cbp_matrix = []
    if flab_path.exists():
        with open(flab_path, "r", encoding="utf-8") as f:
            fdata = json.load(f)
            cbp_matrix = fdata.get("data", {}).get("cbp", {}).get("player_matrix", [])

    cbp_lookup = {}
    for p in cbp_matrix:
        pname = p.get("player_name", "").replace(" ", "").replace("　", "")
        cbp_lookup[pname] = {
            "attack": _safe_float(p.get("attack")),
            "defense": _safe_float(p.get("defense")),
            "gain": _safe_float(p.get("gain")),
            "pass": _safe_float(p.get("pass")),
            "save": _safe_float(p.get("save")),
            "total": _safe_float(p.get("attack")) + _safe_float(p.get("defense")) + _safe_float(p.get("gain")),
        }

    target_hv = 1 if is_home else 2
    fct_spaia = [p for p in spaia_players if p.get("TeamID") == 270 or p.get("HV") == target_hv]
    if not fct_spaia:
        fct_spaia = [p for p in spaia_players if str(p.get("HV")) == str(target_hv)]

    if not fct_spaia:
        return [], None

    max_attack_cbp = 0.0
    max_defense_cbp = 0.0
    max_gain_cbp = 0.0
    for p in fct_spaia:
        clean_name = p.get("Name", "").replace(" ", "").replace("　", "")
        cbp_info = cbp_lookup.get(clean_name, {})
        if cbp_info.get("attack", 0.0) > max_attack_cbp:
            max_attack_cbp = cbp_info.get("attack", 0.0)
        if cbp_info.get("defense", 0.0) > max_defense_cbp:
            max_defense_cbp = cbp_info.get("defense", 0.0)
        if cbp_info.get("gain", 0.0) > max_gain_cbp:
            max_gain_cbp = cbp_info.get("gain", 0.0)

    rated_players = []
    for p in fct_spaia:
        pname = p.get("Name", "")
        clean_name = pname.replace(" ", "").replace("　", "")
        pos = p.get("Pos", "")
        play_time = _safe_int(p.get("Time", 0))

        if play_time < 15:
            continue

        base_score = 6.0
        bonus = 0.0
        penalty = 0.0

        goals = _safe_int(p.get("Score", 0))
        pk_goals = _safe_int(p.get("PKScore", 0))
        normal_goals = goals - pk_goals
        bonus += normal_goals * 1.0 + pk_goals * 0.75

        assists = _safe_int(p.get("Assist", 0))
        bonus += assists * 0.5

        if clean_sheet and pos in ["DF", "GK"] and play_time >= 60:
            bonus += 0.5

        cbp_info = cbp_lookup.get(clean_name, {})
        if max_attack_cbp > 0 and cbp_info.get("attack", 0.0) == max_attack_cbp:
            bonus += 0.5
        if max_defense_cbp > 0 and cbp_info.get("defense", 0.0) == max_defense_cbp:
            bonus += 0.5
        if max_gain_cbp > 0 and cbp_info.get("gain", 0.0) == max_gain_cbp:
            bonus += 0.5

        save_count = _safe_int(p.get("SaveCount", 0))
        save_cbp = cbp_info.get("save", 0.0)
        if pos == "GK" and (save_count >= 3 or save_cbp >= 3.0):
            bonus += 0.5

        yellows = _safe_int(p.get("Yellow", 0))
        reds = _safe_int(p.get("Red", 0))
        if reds > 0:
            penalty += 1.5
        elif yellows > 0:
            penalty += 0.5 * yellows

        pass_count = _safe_int(p.get("PassCount", 0))
        pass_rate = _safe_float(p.get("PassRate", 100.0))
        if pos in ["DF", "MF"] and pass_count >= 20 and pass_rate < 65.0:
            penalty += 0.5

        bonus = min(3.0, bonus)
        penalty = min(3.0, penalty)
        raw_rating = base_score + bonus - penalty
        clipped_rating = max(3.0, min(9.0, raw_rating))
        final_rating = round(clipped_rating * 2) / 2.0

        rated_players.append({
            "match_id": mid,
            "round": match_info["round"],
            "date": match_info["date"],
            "player_name": pname,
            "position": pos,
            "play_time": play_time,
            "goals": goals,
            "assists": assists,
            "rating": final_rating,
            "cbp_total": cbp_info.get("total", 0.0),
            "attack_cbp": cbp_info.get("attack", 0.0),
            "defense_cbp": cbp_info.get("defense", 0.0),
            "gain_cbp": cbp_info.get("gain", 0.0),
        })

    mom = None
    if rated_players and fct_score >= opp_score:
        sorted_players = sorted(
            rated_players,
            key=lambda x: (x["rating"], x["cbp_total"]),
            reverse=True,
        )
        mom = sorted_players[0]

    return rated_players, mom


def extract_accurate_goals() -> List[Dict[str, Any]]:
    """
    Extract accurate goal events from Yahoo text timeline for all 12 matches.
    """
    all_goals = []
    for m in FCT_MATCHES_2026:
        mid = m["match_id"]
        is_home = (m["home"] == "FCT")
        ypath = RAW_YAHOO_DIR / f"{mid}_text.json"
        if not ypath.exists():
            continue

        with open(ypath, "r", encoding="utf-8") as f:
            ydata = json.load(f)

        timeline = ydata.get("timeline", [])
        for item in timeline:
            text = item.get("text", "")
            # True goal indicators in Japanese timeline
            is_true_goal = ("GOOOOOAL!!" in text) or ("ゴールに決める" in text) or ("ゴール左に決める" in text) or ("ゴール右に決める" in text) or ("ゴール中央に決める" in text) or ("オウンゴール" in text)
            if not is_true_goal:
                continue

            team_label = item.get("team", "")
            is_fct = ("FC" in team_label)

            # Classify tactical trigger / causality
            cause = "遅攻・組織崩し(サイド/中央)"
            if any(k in text for k in ["CK", "コーナーキック", "FK", "フリーキック", "PK", "ペナルティキック"]):
                cause = "セットプレー(CK/FK/PK)"
            elif any(k in text for k in ["カウンター", "速攻", "抜け出し", "ロングボール", "縦パス一本", "スルーパスに抜け出し"]):
                cause = "速攻・カウンター"
            elif any(k in text for k in ["クロス", "サイド", "ポケット", "折り返し"]):
                cause = "サイド崩し・クロス/ポケット"
            elif any(k in text for k in ["パスカット", "インターセプト", "ミス", "こぼれ球", "プレスで奪い", "ボールを奪い"]):
                cause = "相手ミス・プレス奪取" if is_fct else "自陣ミス・被プレス"
            elif any(k in text for k in ["中央", "コンビネーション", "ワンツー", "ミドル"]):
                cause = "中央突破・ミドルシュート"

            all_goals.append({
                "match_id": mid,
                "round": m["round"],
                "date": m["date"],
                "time": item.get("time", ""),
                "team": "FCT" if is_fct else "OPPONENT",
                "cause": cause,
                "text": text[:80],
            })

    return all_goals


def run_track1_verification() -> Dict[str, Any]:
    print("=" * 60)
    print("TRACK 1: スタッツ・モーメンタム・得失点因果の検証 開始")
    print("=" * 60)

    # 1. Player Ratings & MOM
    all_player_ratings = []
    mom_counts = {}
    mom_records = []

    for m in FCT_MATCHES_2026:
        players, mom = calculate_match_player_ratings(m)
        all_player_ratings.extend(players)
        if mom:
            pname = mom["player_name"]
            mom_counts[pname] = mom_counts.get(pname, 0) + 1
            mom_records.append({
                "round": m["round"],
                "match_id": m["match_id"],
                "player_name": pname,
                "rating": mom["rating"],
                "goals": mom["goals"],
                "assists": mom["assists"],
            })

    player_summary = {}
    for p in all_player_ratings:
        pname = p["player_name"]
        if pname not in player_summary:
            player_summary[pname] = {
                "name": pname,
                "position": p["position"],
                "matches": 0,
                "total_minutes": 0,
                "total_goals": 0,
                "total_assists": 0,
                "ratings": [],
                "moms": 0,
            }
        player_summary[pname]["matches"] += 1
        player_summary[pname]["total_minutes"] += p["play_time"]
        player_summary[pname]["total_goals"] += p["goals"]
        player_summary[pname]["total_assists"] += p["assists"]
        player_summary[pname]["ratings"].append(p["rating"])

    for pname, d in player_summary.items():
        d["moms"] = mom_counts.get(pname, 0)
        d["avg_rating"] = round(sum(d["ratings"]) / len(d["ratings"]), 2)

    eligible_players = [d for d in player_summary.values() if d["matches"] >= 3]
    top_5 = sorted(eligible_players, key=lambda x: (x["avg_rating"], x["moms"], x["total_goals"]), reverse=True)[:5]
    worst_5 = sorted(eligible_players, key=lambda x: (x["avg_rating"], -x["matches"]))[:5]
    mom_ranked = sorted([d for d in player_summary.values() if d["moms"] > 0], key=lambda x: x["moms"], reverse=True)

    print("\n[1] シーズン通算 選手平均採点ランキング（トップ5 & ワースト5）")
    print("--- トップ5 選手 (3試合以上出場) ---")
    for idx, p in enumerate(top_5, 1):
        print(f" {idx}位: {p['name']} ({p['position']}) - 平均採点: {p['avg_rating']} (出場: {p['matches']}試合, 得点: {p['total_goals']}, MOM: {p['moms']}回)")

    print("\n--- ワースト 選手 (3試合以上出場) ---")
    for idx, p in enumerate(worst_5, 1):
        print(f" {idx}位: {p['name']} ({p['position']}) - 平均採点: {p['avg_rating']} (出場: {p['matches']}試合, 得点: {p['total_goals']})")

    print("\n--- MOM（マン・オブ・ザ・マッチ）獲得数集計 ---")
    for p in mom_ranked:
        print(f" {p['name']}: {p['moms']}回獲得 (平均採点: {p['avg_rating']})")

    # 2. 12 Matches Trend
    print("\n[2] 12試合の勝点・得失点・xG・Field Tilt・走行距離の推移データ算出")
    trends = []
    cumulative_points = 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for m in FCT_MATCHES_2026:
        mid = m["match_id"]
        is_home = (m["home"] == "FCT")
        fct_score = m["h_score"] if is_home else m["a_score"]
        opp_score = m["a_score"] if is_home else m["h_score"]

        if fct_score > opp_score:
            pts = 3
            res = "WIN"
        elif fct_score == opp_score:
            pts = 1
            res = "DRAW"
        else:
            pts = 0
            res = "LOSS"
        cumulative_points += pts

        tjson_path = STRUCTURED_DIR / f"{mid}_tactical.json"
        field_tilt = 50.0
        if tjson_path.exists():
            with open(tjson_path, "r", encoding="utf-8") as f:
                tdata = json.load(f)
                dmetrics = tdata.get("deep_metrics", {})
                ft_info = dmetrics.get("field_tilt", {})
                if is_home:
                    field_tilt = _safe_float(ft_info.get("home_field_tilt", 50.0))
                else:
                    field_tilt = _safe_float(ft_info.get("away_field_tilt", 50.0))

        cur.execute(
            "SELECT team_id, SUM(xg) FROM match_events WHERE match_id = ? AND xg IS NOT NULL GROUP BY team_id",
            (mid,),
        )
        xg_rows = dict(cur.fetchall())
        fct_xg = _safe_float(xg_rows.get("FCT"))
        opp_team_id = m["away"] if is_home else m["home"]
        opp_xg = _safe_float(xg_rows.get(opp_team_id))

        if fct_xg == 0.0 or opp_xg == 0.0:
            spaia_path = RAW_SPAIA_DIR / f"{mid}_player_stats.json"
            if spaia_path.exists():
                with open(spaia_path, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                    h_shots, a_shots = 0, 0
                    h_on_target, a_on_target = 0, 0
                    h_pa, a_pa = 0, 0
                    for p in sdata.get("player_stats", []):
                        sh = _safe_int(p.get("Shoot", 0))
                        sot = _safe_int(p.get("ShootOnTarget", 0))
                        pa = _safe_int(p.get("PAPlayCount", 0))
                        if p.get("HV") == 1:
                            h_shots += sh
                            h_on_target += sot
                            h_pa += pa
                        else:
                            a_shots += sh
                            a_on_target += sot
                            a_pa += pa
                    h_est = h_on_target * 0.28 + max(0, h_shots - h_on_target) * 0.06 + h_pa * 0.02
                    a_est = a_on_target * 0.28 + max(0, a_shots - a_on_target) * 0.06 + a_pa * 0.02
                    if fct_xg == 0.0:
                        fct_xg = h_est if is_home else a_est
                    if opp_xg == 0.0:
                        opp_xg = a_est if is_home else h_est

        cur.execute(
            "SELECT total_distance_km FROM team_match_stats WHERE match_id = ? AND team_id = 'FCT'",
            (mid,),
        )
        dist_row = cur.fetchone()
        fct_dist = _safe_float(dist_row[0]) if dist_row and dist_row[0] else 0.0

        if fct_dist == 0.0:
            ypath = RAW_YAHOO_DIR / f"{mid}_stats.json"
            if ypath.exists():
                with open(ypath, "r", encoding="utf-8") as f:
                    ydata = json.load(f)
                    total_d = 0.0
                    for py in ydata.get("player_stats", []):
                        if "FC" in py.get("team_name", ""):
                            dstr = py.get("distance", {}).get("total", "0km").replace("km", "")
                            total_d += _safe_float(dstr)
                    if total_d > 0:
                        fct_dist = round(total_d, 2)

        trends.append({
            "round": m["round"],
            "date": m["date"],
            "opponent": m["away"] if is_home else m["home"],
            "result": res,
            "score": f"{fct_score}-{opp_score}",
            "points": pts,
            "cum_points": cumulative_points,
            "fct_score": fct_score,
            "opp_score": opp_score,
            "fct_xg": round(fct_xg, 2),
            "opp_xg": round(opp_xg, 2),
            "field_tilt": round(field_tilt, 1),
            "distance_km": fct_dist,
        })

    conn.close()

    print(f"{'節':<3} | {'日付':<10} | {'対戦':<5} | {'結果':<4} | {'スコア':<5} | {'勝点(累計)':<8} | {'xG (得/失)':<12} | {'FieldTilt':<9} | {'走行距離(km)':<10}")
    print("-" * 80)
    for t in trends:
        print(f"R{t['round']:<2} | {t['date']:<10} | {t['opponent']:<5} | {t['result']:<4} | {t['score']:<5} | {t['points']}({t['cum_points']:<2})     | {t['fct_xg']:.2f} / {t['opp_xg']:.2f}  | {t['field_tilt']:>5.1f}%   | {t['distance_km']:>8.1f}")

    # 3. Accurate 37 Goals/Conceded Causal Classification
    print("\n[3] 全得失点イベントの構造的因果分類（セットプレー/速攻/遅攻/エラー等の集計）")
    accurate_goals = extract_accurate_goals()

    fct_goals = [g for g in accurate_goals if g["team"] == "FCT"]
    opp_goals = [g for g in accurate_goals if g["team"] == "OPPONENT"]

    fct_causes = {}
    for g in fct_goals:
        c = g["cause"]
        fct_causes[c] = fct_causes.get(c, 0) + 1

    opp_causes = {}
    for g in opp_goals:
        c = g["cause"]
        opp_causes[c] = opp_causes.get(c, 0) + 1

    print(f"集計対象: FC東京 得点 {len(fct_goals)} 点 / 被失点 {len(opp_goals)} 点 (合計 {len(accurate_goals)} 得失点イベント)")
    print("\n--- FC東京 得点パターン因果集計 ---")
    for k, v in sorted(fct_causes.items(), key=lambda x: x[1], reverse=True):
        pct = (v / len(fct_goals) * 100) if fct_goals else 0
        print(f" ・{k}: {v}点 ({pct:.1f}%)")

    print("\n--- FC東京 被失点パターン因果集計 ---")
    for k, v in sorted(opp_causes.items(), key=lambda x: x[1], reverse=True):
        pct = (v / len(opp_goals) * 100) if opp_goals else 0
        print(f" ・{k}: {v}点 ({pct:.1f}%)")

    return {
        "top_5": top_5,
        "worst_5": worst_5,
        "mom_ranked": mom_ranked,
        "trends": trends,
        "total_fct_goals": len(fct_goals),
        "total_opp_goals": len(opp_goals),
        "fct_causes": fct_causes,
        "opp_causes": opp_causes,
        "accurate_goals": accurate_goals,
    }


if __name__ == "__main__":
    run_track1_verification()
