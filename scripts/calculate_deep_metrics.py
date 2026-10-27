"""
Deep Tactical Metrics Calculator (scripts/calculate_deep_metrics.py).

Calculates deterministic deep tactical metrics according to data_analysis_specification.md:
1. Conversion Rates (30m -> PA, PA -> Shot)
2. Field Tilt (Attacking 3rd Share %)
3. Box vs Outside Middle Shot Ratio (%)
4. CBP Rankings & Bench Impact
5. Timeline Event Aggregations (Goals, Shots, Blocks, Crosses, Cards, Subs)
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import re


# 4.1 事象抽出正規表現パターン
EVENT_REGEX_PATTERNS = {
    "GOAL": r"(ゴール|得点|PK.*成功|直接FK.*決まる|ネットを揺らす)",
    "SHOT": r"(シュート|ヘディング|右足で狙う|左足で狙う|枠を捉える|枠を外れる)",
    "BLOCK": r"(ブロック|体を張って防ぐ|GK.*弾く|ファインセーブ|掻き出す|セーブ)",
    "CROSS": r"(クロス|センタリング|鋭いクロス|グラウンダーのパス)",
    "CORNER": r"(コーナーキック|CK)",
    "FREEKICK": r"(フリーキック|FK)",
    "FOUL": r"(ファウル|倒される|ハンド|激しいチャージ)",
    "CARD_YELLOW": r"(イエローカード|警告)",
    "CARD_RED": r"(レッドカード|一発退場|2枚目の警告|退場)",
    "SUBSTITUTION": r"(選手交代|交代|に代わって|退き、|がピッチへ)",
    "OFFSIDE": r"(オフサイド)",
}


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def calculate_conversion_rates(
    spaia_players: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Calculate 30m -> PA and PA -> Shot conversion rates.
    HV=1: Home, HV=2: Away
    """
    home_m30 = 0
    home_pa = 0
    home_shots = 0

    away_m30 = 0
    away_pa = 0
    away_shots = 0

    for p in spaia_players:
        hv = _safe_int(p.get("HV"))
        m30 = _safe_int(p.get("M30PlayCount"))
        pa = _safe_int(p.get("PAPlayCount"))
        shots = _safe_int(p.get("Shoot"))

        if hv == 1:
            home_m30 += m30
            home_pa += pa
            home_shots += shots
        elif hv == 2:
            away_m30 += m30
            away_pa += pa
            away_shots += shots

    # Home calculations
    home_30_to_pa = (home_pa / home_m30 * 100.0) if home_m30 > 0 else 0.0
    home_pa_to_shot = (home_shots / home_pa * 100.0) if home_pa > 0 else 0.0

    # Away calculations
    away_30_to_pa = (away_pa / away_m30 * 100.0) if away_m30 > 0 else 0.0
    away_pa_to_shot = (away_shots / away_pa * 100.0) if away_pa > 0 else 0.0

    def _eval_30_to_pa(rate: float) -> str:
        if rate >= 40.0:
            return "高効率侵入（ポケット攻略・相手最終ライン突破成功）"
        elif rate >= 25.0:
            return "標準水準（通常のブロック攻略推移）"
        else:
            return "外周停滞・封殺（PA手前で跳ね返され外回しに終始）"

    def _eval_pa_to_shot(rate: float) -> str:
        if rate >= 50.0:
            return "高脅威フィニッシュ（エリア侵入が確実に決定打へ直結）"
        elif rate >= 30.0:
            return "標準水準（平均的なフィニッシュ精度）"
        else:
            return "決定力欠如・ラストパス不全（PA内でのロストやクリア被弾が顕著）"

    return {
        "home": {
            "m30_count": home_m30,
            "pa_count": home_pa,
            "shot_count": home_shots,
            "rate_30_to_pa": round(home_30_to_pa, 2),
            "eval_30_to_pa": _eval_30_to_pa(home_30_to_pa),
            "rate_pa_to_shot": round(home_pa_to_shot, 2),
            "eval_pa_to_shot": _eval_pa_to_shot(home_pa_to_shot),
        },
        "away": {
            "m30_count": away_m30,
            "pa_count": away_pa,
            "shot_count": away_shots,
            "rate_30_to_pa": round(away_30_to_pa, 2),
            "eval_30_to_pa": _eval_30_to_pa(away_30_to_pa),
            "rate_pa_to_shot": round(away_pa_to_shot, 2),
            "eval_pa_to_shot": _eval_pa_to_shot(away_pa_to_shot),
        },
    }


def calculate_field_tilt(
    spaia_players: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate Field Tilt (Attacking 3rd Play Share %)."""
    home_at3rd = 0
    away_at3rd = 0

    for p in spaia_players:
        hv = _safe_int(p.get("HV"))
        at3rd = _safe_int(p.get("At3rdPlayCount"))
        if hv == 1:
            home_at3rd += at3rd
        elif hv == 2:
            away_at3rd += at3rd

    total = home_at3rd + away_at3rd
    if total > 0:
        home_tilt = (home_at3rd / total) * 100.0
        away_tilt = 100.0 - home_tilt
    else:
        home_tilt = 50.0
        away_tilt = 50.0

    def _eval_tilt(tilt: float) -> str:
        if tilt >= 60.0:
            return "敵陣圧倒（相手を自陣深くに釘付けにしハーフコート展開）"
        elif tilt >= 45.0:
            return "互角・拮抗（中盤での主導権争いが交互に発生）"
        else:
            return "自陣防戦（押し込まれロングボール依存の展開）"

    return {
        "home_at3rd_count": home_at3rd,
        "away_at3rd_count": away_at3rd,
        "home_field_tilt": round(home_tilt, 2),
        "away_field_tilt": round(away_tilt, 2),
        "home_eval": _eval_tilt(home_tilt),
        "away_eval": _eval_tilt(away_tilt),
    }


def calculate_cbp_rankings(
    fl_player_matrix: List[Dict[str, Any]],
    spaia_players: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Calculate top CBP players by category and bench impact.
    """
    home_players = [p for p in fl_player_matrix if p.get("team_side") == "HOME"]
    away_players = [p for p in fl_player_matrix if p.get("team_side") == "AWAY"]

    def _top_players(players: List[Dict[str, Any]], key: str, n: int = 3) -> List[Dict[str, Any]]:
        sorted_p = sorted(players, key=lambda x: _safe_float(x.get(key)), reverse=True)
        return [
            {
                "name": p.get("player_name", ""),
                "value": round(_safe_float(p.get(key)), 2),
            }
            for p in sorted_p[:n]
        ]

    # Bench impact calculation from SPAIA players
    home_sub_impact = 0.0
    away_sub_impact = 0.0

    sub_names_home = set()
    sub_names_away = set()

    if spaia_players:
        for p in spaia_players:
            start_f = _safe_int(p.get("StartF"))
            play_time = _safe_int(p.get("Time"))
            hv = _safe_int(p.get("HV"))
            name = (p.get("Name") or "").replace("　", " ").strip()
            if start_f == 0 and play_time > 0:
                if hv == 1:
                    sub_names_home.add(name)
                else:
                    sub_names_away.add(name)

        for p in fl_player_matrix:
            p_name = (p.get("player_name") or "").replace("　", " ").strip()
            atk = _safe_float(p.get("attack"))
            sht = _safe_float(p.get("shoot"))
            combined = atk + sht
            if any(s in p_name or p_name in s for s in sub_names_home):
                home_sub_impact += combined
            elif any(s in p_name or p_name in s for s in sub_names_away):
                away_sub_impact += combined

    def _eval_sub_impact(val: float) -> str:
        if val >= 3.0:
            return "采配大的中（投入選手が得点や決定機に直結し流れを決定づけた）"
        elif val >= 1.0:
            return "標準・維持（強度低下を防ぐ守備的維持、または限定的な関与）"
        else:
            return "交代不発・沈黙（交代組がボールに絡めずピッチ上で孤立）"

    return {
        "home": {
            "top_attack": _top_players(home_players, "attack"),
            "top_defense": _top_players(home_players, "defense"),
            "top_gain": _top_players(home_players, "gain"),
            "top_pass": _top_players(home_players, "pass"),
            "bench_impact": round(home_sub_impact, 2),
            "bench_eval": _eval_sub_impact(home_sub_impact),
        },
        "away": {
            "top_attack": _top_players(away_players, "attack"),
            "top_defense": _top_players(away_players, "defense"),
            "top_gain": _top_players(away_players, "gain"),
            "top_pass": _top_players(away_players, "pass"),
            "bench_impact": round(away_sub_impact, 2),
            "bench_eval": _eval_sub_impact(away_sub_impact),
        },
    }


def aggregate_timeline_events(
    yahoo_timeline: List[Dict[str, Any]],
    home_team_name: str = "FC東京",
) -> Dict[str, Any]:
    """
    Deterministic event counting using Yahoo structured flags and regex.
    """
    home_counts = {
        "goals": 0,
        "shots": 0,
        "blocks": 0,
        "crosses": 0,
        "corners": 0,
        "fouls": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        "subs": 0,
    }
    away_counts = {
        "goals": 0,
        "shots": 0,
        "blocks": 0,
        "crosses": 0,
        "corners": 0,
        "fouls": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        "subs": 0,
    }

    key_plays = []

    for item in yahoo_timeline:
        text = item.get("text") or ""
        team = item.get("team") or ""
        time_str = item.get("time") or ""

        # Determine target team
        is_home = (home_team_name in team) if team else True
        target = home_counts if is_home else away_counts

        # 1. Goal
        if item.get("is_goal") or re.search(EVENT_REGEX_PATTERNS["GOAL"], text):
            target["goals"] += 1
            key_plays.append(f"{time_str} 【ゴール】{text[:60]}")
            continue

        # 2. Substitution
        if item.get("is_substitution") or re.search(EVENT_REGEX_PATTERNS["SUBSTITUTION"], text):
            target["subs"] += 1
            continue

        # 3. Card
        if item.get("is_card"):
            if re.search(EVENT_REGEX_PATTERNS["CARD_RED"], text):
                target["red_cards"] += 1
                key_plays.append(f"{time_str} 【退場】{text[:60]}")
            else:
                target["yellow_cards"] += 1
            continue

        # 4. Shot
        if re.search(EVENT_REGEX_PATTERNS["SHOT"], text):
            target["shots"] += 1
            if "決定機" in text or "惜しい" in text or "枠を捉える" in text:
                key_plays.append(f"{time_str} 【決定機】{text[:60]}")

        # 5. Block
        if re.search(EVENT_REGEX_PATTERNS["BLOCK"], text):
            target["blocks"] += 1

        # 6. Cross
        if re.search(EVENT_REGEX_PATTERNS["CROSS"], text):
            target["crosses"] += 1

        # 7. Corner
        if re.search(EVENT_REGEX_PATTERNS["CORNER"], text):
            target["corners"] += 1

        # 8. Foul
        if re.search(EVENT_REGEX_PATTERNS["FOUL"], text):
            target["fouls"] += 1

    total_events = len(yahoo_timeline)

    return {
        "total_events": total_events,
        "home_counts": home_counts,
        "away_counts": away_counts,
        "key_plays_sample": key_plays[:8],
    }


def calculate_match_deep_metrics(
    match_id_or_game_id: str,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load raw files for a given match and compute all deep tactical metrics.
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent / "data" / "raw"

    # Search for files with match_id or game_id
    spaia_stat_path = None
    fl_path = None
    yahoo_text_path = None
    yahoo_stat_path = None

    for p in (base_dir / "spaia").glob(f"*{match_id_or_game_id}*_player_stats.json"):
        spaia_stat_path = p
        break

    for p in (base_dir / "football_lab").glob(f"*{match_id_or_game_id}*.json"):
        fl_path = p
        break

    for p in (base_dir / "yahoo").glob(f"*{match_id_or_game_id}*_text.json"):
        yahoo_text_path = p
        break

    for p in (base_dir / "yahoo").glob(f"*{match_id_or_game_id}*_stats.json"):
        yahoo_stat_path = p
        break

    if not (spaia_stat_path and fl_path and yahoo_text_path and yahoo_stat_path):
        raise FileNotFoundError(
            f"Missing required raw files for {match_id_or_game_id} in {base_dir}"
        )

    spaia_stat = json.loads(spaia_stat_path.read_text(encoding="utf-8"))
    fl_data = json.loads(fl_path.read_text(encoding="utf-8"))
    yahoo_text = json.loads(yahoo_text_path.read_text(encoding="utf-8"))
    yahoo_stat = json.loads(yahoo_stat_path.read_text(encoding="utf-8"))

    spaia_players = spaia_stat.get("player_stats", [])
    fl_cbp_players = (
        fl_data.get("data", {}).get("cbp", {}).get("player_matrix", [])
    )
    yahoo_timeline = yahoo_text.get("timeline", [])
    home_name = (
        yahoo_stat.get("match_info", {}).get("home_team", "FC東京")
    )

    conv_rates = calculate_conversion_rates(spaia_players)
    field_tilt = calculate_field_tilt(spaia_players)
    cbp_rankings = calculate_cbp_rankings(fl_cbp_players, spaia_players)
    timeline_events = aggregate_timeline_events(yahoo_timeline, home_name)

    return {
        "match_id": match_id_or_game_id,
        "conversion_rates": conv_rates,
        "field_tilt": field_tilt,
        "cbp_rankings": cbp_rankings,
        "timeline_events": timeline_events,
    }
