"""2026年J1全選手 戦術アーキタイプ決定論的自動付与パイプライン (pipeline/player_archetype_assigner.py).

機能:
- `knowledge/player_archetypes.json` の13類型定義
- `entity_master_players`（利き足、身長、体重、登録ポジション）
- `player_match_positions`（実績ロール、主要レーン、流動性タグ）
- `player_match_stats`（90分あたりスプリント、最高時速、CBP、パス、タックル等）
から、全主力選手の戦術アーキタイプ（プライマリ／セカンダリ）を決定論的に算出し、
`knowledge/player_archetype_assignments.json` および `entity_master_players.profile_json` に反映する。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("player_archetype_assigner")

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("FOOTBALL_DB_PATH", ROOT_DIR / "data" / "football.db"))
ARCHETYPES_DEF_PATH = ROOT_DIR / "knowledge" / "player_archetypes.json"
OUTPUT_ASSIGNMENTS_PATH = ROOT_DIR / "knowledge" / "player_archetype_assignments.json"


def _load_archetype_definitions() -> Dict[str, Any]:
    if not ARCHETYPES_DEF_PATH.exists():
        raise FileNotFoundError(f"Archetype definitions not found at {ARCHETYPES_DEF_PATH}")
    return json.loads(ARCHETYPES_DEF_PATH.read_text(encoding="utf-8"))


def _score_archetype_for_player(
    p: Dict[str, Any],
) -> Tuple[str, Optional[str], Dict[str, float]]:
    """選手の属性とスタッツから各アーキタイプの適合スコアを算出し、(primary, secondary, scores) を返す."""
    role = str(p.get("primary_role") or p.get("registered_pos") or "").upper()
    lane = str(p.get("primary_lane") or "")
    foot = str(p.get("dominant_foot") or "")
    height = float(p.get("height_cm") or 178.0)
    mins = int(p.get("total_minutes") or 0)
    per90 = 90.0 / max(mins, 90)

    spr_p90 = float(p.get("total_sprints") or 0) * per90
    max_spd = float(p.get("max_speed_kmh") or 0.0)
    cbp_att = float(p.get("cbp_attack") or 0.0) * per90
    cbp_dfn = float(p.get("cbp_defense") or 0.0) * per90
    cbp_gain = float(p.get("cbp_gain") or 0.0) * per90
    cbp_pass = float(p.get("cbp_pass") or 0.0) * per90
    cbp_cross = float(p.get("cbp_cross") or 0.0) * per90
    cbp_drb = float(p.get("cbp_dribble") or 0.0) * per90
    cbp_sht = float(p.get("cbp_shoot") or 0.0) * per90
    tackles_p90 = float(p.get("total_tackles") or 0) * per90
    pa_entries_p90 = float(p.get("pa_entries") or 0) * per90

    scores: Dict[str, float] = {}

    # 1. GK
    if "GK" in role:
        scores["sweeper_keeper"] = 80.0 + (max_spd * 0.5)
        return ("sweeper_keeper", None, scores)

    # 2. CB / DF
    if "CB" in role or ("DF" in role and "S" not in role and "W" not in role):
        bpd_score = 40.0 + (cbp_pass * 2.0) + (cbp_att * 1.5)
        if foot == "左":
            bpd_score += 15.0
        scores["ball_playing_defender"] = bpd_score

        dst_score = 40.0 + (cbp_dfn * 2.0) + (cbp_gain * 1.5) + (tackles_p90 * 3.0)
        if height >= 185.0:
            dst_score += 10.0
        scores["destroyer_filter"] = dst_score

    # 3. SB / WB
    if any(k in role for k in ("SB", "WB", "LSB", "RSB", "LWB", "RWB")):
        # 偽SB: 内側レーン、パス高い
        inv_score = 30.0 + (cbp_pass * 2.0)
        if any(h in lane for h in ("HALF_SPACE", "CENTER")):
            inv_score += 30.0
        if (role in ("LSB", "LWB") and foot == "右") or (role in ("RSB", "RWB") and foot == "左"):
            inv_score += 15.0
        scores["inverted_fullback"] = inv_score

        # オーバーラップ: スプリント・クロス
        ovr_score = 30.0 + (spr_p90 * 1.5) + (cbp_cross * 4.0)
        if max_spd >= 32.0:
            ovr_score += 15.0
        scores["overlap_runner"] = ovr_score

        # タッチラインウイング型WB
        if "WB" in role:
            scores["touchline_winger"] = 25.0 + (cbp_cross * 3.0) + (cbp_drb * 2.0)

    # 4. DMF / CMF / ボランチ
    if any(k in role for k in ("DMF", "CMF", "VO", "MF")) and not any(k in role for k in ("SMF", "OMF", "WG")):
        # レジスタ: パス、展開
        dlp_score = 35.0 + (cbp_pass * 3.0)
        scores["deep_lying_playmaker"] = dlp_score

        # デストロイヤー: 奪取、守備
        dst_score = 35.0 + (cbp_gain * 2.5) + (cbp_dfn * 2.0) + (tackles_p90 * 4.0)
        scores["destroyer_filter"] = dst_score

        # ライン間レシーバー: 前進
        scores["between_the_lines_receiver"] = 20.0 + (cbp_att * 2.0) + (cbp_drb * 2.0)

    # 5. OMF / SMF / WG / シャドー
    if any(k in role for k in ("OMF", "SMF", "WG", "LWG", "RWG", "LSH", "RSH", "SH")):
        # カットイン (inside_forward): 逆足でシュート
        is_inverted = (("L" in role or "LEFT" in lane) and foot == "右") or (
            ("R" in role or "RIGHT" in lane) and foot == "左"
        )
        inf_score = 30.0 + (cbp_sht * 4.0) + (cbp_att * 2.0)
        if is_inverted:
            inf_score += 25.0
        scores["inside_forward"] = inf_score

        # 大外ウイング (touchline_winger): ドリブル・クロス
        tlw_score = 30.0 + (cbp_cross * 3.5) + (cbp_drb * 3.0) + (spr_p90 * 1.0)
        if not is_inverted and foot in ("右", "左"):
            tlw_score += 15.0
        scores["touchline_winger"] = tlw_score

        # ポケット侵入 (pocket_infiltrator): PA侵入
        pkt_score = 30.0 + (pa_entries_p90 * 5.0) + (cbp_att * 2.0)
        scores["pocket_infiltrator"] = pkt_score

        # ライン間レシーバー (between_the_lines_receiver):
        btl_score = 30.0 + (cbp_pass * 2.0) + (cbp_att * 2.0)
        scores["between_the_lines_receiver"] = btl_score

    # 6. CF / FW
    if any(k in role for k in ("CF", "FW", "ST")):
        # ターゲットマン: 身長、空中戦
        tgt_score = 25.0 + (cbp_att * 1.5)
        if height >= 185.0:
            tgt_score += 35.0
        elif height >= 181.0:
            tgt_score += 15.0
        scores["target_man"] = tgt_score

        # ラインブレイカー: スプリント、最高速度
        lnb_score = 25.0 + (spr_p90 * 1.8) + (cbp_sht * 3.0)
        if max_spd >= 32.5:
            lnb_score += 25.0
        elif max_spd >= 31.0:
            lnb_score += 12.0
        scores["line_breaker"] = lnb_score

        # 偽9番: パス、リンク
        fn_score = 20.0 + (cbp_pass * 3.0) + (cbp_att * 2.0)
        scores["false_nine"] = fn_score

    if not scores:
        scores["between_the_lines_receiver"] = 40.0

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_scores[0][0]
    secondary = sorted_scores[1][0] if len(sorted_scores) > 1 and sorted_scores[1][1] >= 35.0 else None

    return (primary, secondary, scores)


def assign_archetypes_all_players() -> Dict[str, Any]:
    """全20クラブの出場選手にアーキタイプを決定論的に割り当てる."""
    definitions = _load_archetype_definitions()
    arch_meta = {a["archetype_id"]: a["name"] for a in definitions.get("archetypes", [])}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # 選手の基本情報と集計スタッツを取得
        rows = conn.execute(
            """
            SELECT
                emp.player_id,
                emp.team_id,
                emp.canonical_name,
                emp.position AS registered_pos,
                emp.number,
                emp.height_cm,
                emp.weight_kg,
                emp.dominant_foot,
                emp.profile_json,
                COUNT(pms.match_id) AS total_matches,
                SUM(pms.minutes_played) AS total_minutes,
                SUM(pms.sprints) AS total_sprints,
                MAX(json_extract(pms.raw_stats_json, '$.max_speed_kmh')) AS max_speed_kmh,
                SUM(json_extract(pms.raw_stats_json, '$.cbp.attack')) AS cbp_attack,
                SUM(json_extract(pms.raw_stats_json, '$.cbp.defense')) AS cbp_defense,
                SUM(json_extract(pms.raw_stats_json, '$.cbp.gain')) AS cbp_gain,
                SUM(json_extract(pms.raw_stats_json, '$.cbp.pass')) AS cbp_pass,
                SUM(json_extract(pms.raw_stats_json, '$.cbp.cross')) AS cbp_cross,
                SUM(json_extract(pms.raw_stats_json, '$.cbp.dribble')) AS cbp_dribble,
                SUM(json_extract(pms.raw_stats_json, '$.cbp.shoot')) AS cbp_shoot,
                SUM(json_extract(pms.raw_stats_json, '$.spaia.tackle_count')) AS total_tackles,
                SUM(json_extract(pms.raw_stats_json, '$.spaia.pa_entries')) AS pa_entries,
                pmp.primary_role,
                pmp.primary_lane
            FROM entity_master_players emp
            LEFT JOIN player_match_stats pms ON emp.player_id = pms.player_id
            LEFT JOIN (
                SELECT player_id, primary_role, primary_lane
                FROM player_match_positions
                GROUP BY player_id
            ) pmp ON emp.player_id = pmp.player_id
            GROUP BY emp.player_id
            HAVING total_matches > 0 OR emp.dominant_foot IS NOT NULL
            ORDER BY emp.team_id, total_minutes DESC
            """,
        ).fetchall()

        assignments_by_team: Dict[str, List[Dict[str, Any]]] = {}
        updates_to_db: List[Tuple[str, str]] = []

        for r in rows:
            p_dict = dict(r)
            prim, sec, scores = _score_archetype_for_player(p_dict)

            rec = {
                "player_id": p_dict["player_id"],
                "team_id": p_dict["team_id"],
                "name": p_dict["canonical_name"],
                "number": p_dict["number"],
                "registered_pos": p_dict["registered_pos"],
                "primary_role": p_dict["primary_role"],
                "dominant_foot": p_dict["dominant_foot"],
                "height_cm": p_dict["height_cm"],
                "total_minutes": p_dict["total_minutes"] or 0,
                "primary_archetype": prim,
                "primary_archetype_name": arch_meta.get(prim, prim),
                "secondary_archetype": sec,
                "secondary_archetype_name": arch_meta.get(sec, sec) if sec else None,
                "confidence_score": round(scores.get(prim, 50.0), 1),
            }

            tid = str(p_dict["team_id"] or "OTHER")
            assignments_by_team.setdefault(tid, []).append(rec)

            # DB profile_json 更新
            existing_prof = {}
            if p_dict.get("profile_json"):
                try:
                    existing_prof = json.loads(p_dict["profile_json"])
                except Exception:
                    existing_prof = {}
            existing_prof["archetypes"] = {
                "primary": prim,
                "primary_name": arch_meta.get(prim, prim),
                "secondary": sec,
                "secondary_name": arch_meta.get(sec, sec) if sec else None,
            }
            updates_to_db.append((json.dumps(existing_prof, ensure_ascii=False), p_dict["player_id"]))

        # DBへ一括反映
        conn.executemany(
            "UPDATE entity_master_players SET profile_json = ? WHERE player_id = ?",
            updates_to_db,
        )
        conn.commit()

        payload = {
            "version": "1.0.0",
            "description": "Deterministic Player Archetype Assignments for All 20 J1 Clubs (2026 Season)",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_players_assigned": len(rows),
            "teams": assignments_by_team,
        }

        OUTPUT_ASSIGNMENTS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "Assigned archetypes to %d players across %d teams.",
            len(rows),
            len(assignments_by_team),
        )
        return payload
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = assign_archetypes_all_players()
    print(f"Assigned archetypes for {res['total_players_assigned']} players across {len(res['teams'])} clubs.")

