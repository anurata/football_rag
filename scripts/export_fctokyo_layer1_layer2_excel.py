# -*- coding: utf-8 -*-
"""
Export FC Tokyo Layer 1 (Ground Truth) & Layer 2 (Tactical Heuristics) to Excel.
(scripts/export_fctokyo_layer1_layer2_excel.py)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection

OUTPUT_FILE = ROOT_DIR / "exports" / "FCT_Layer1_Layer2_Dossier_2026.xlsx"
PROFILES_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"
PLAYERS_JSON_PATH = ROOT_DIR / "data" / "players" / "FCT_players.json"


def get_fct_matches(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Fetch all FC Tokyo matches in 2026 season."""
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
               home_score, away_score, stadium, weather
        FROM matches
        WHERE (home_team_id = 'FCT' OR away_team_id = 'FCT')
          AND season = 2026
          AND matchweek <= 12
        ORDER BY matchweek ASC;
        """
    )
    return cur.fetchall()


def build_layer1_team_stats(conn: sqlite3.Connection, matches: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build Sheet: Layer 1 Team Detailed Match Stats (75 items)."""
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()

    records = []
    for m in matches:
        m_id = m["match_id"]
        is_home = (m["home_team_id"] == "FCT")
        opp_id = m["away_team_id"] if is_home else m["home_team_id"]
        fct_score = m["home_score"] if is_home else m["away_score"]
        opp_score = m["away_score"] if is_home else m["home_score"]

        result = "勝" if fct_score > opp_score else ("分" if fct_score == opp_score else "敗")

        # Fetch FCT stats
        cur.execute("SELECT * FROM team_match_flab_stats WHERE match_id = ? AND team_id = 'FCT'", (m_id,))
        fct_flab = cur.fetchone() or {}

        # Fetch Opponent stats
        cur.execute("SELECT * FROM team_match_flab_stats WHERE match_id = ? AND team_id = ?", (m_id, opp_id))
        opp_flab = cur.fetchone() or {}

        row = {
            "試合ID": m_id,
            "節": m["matchweek"],
            "開催日": m["date"],
            "会場/天候": f"{m.get('stadium', '')} ({m.get('weather', '')})",
            "H/A": "HOME" if is_home else "AWAY",
            "対戦相手": opp_id,
            "スコア(FCT)": fct_score,
            "スコア(相手)": opp_score,
            "勝敗": result,
            # Core Layer 1 Fact Stats
            "xG": fct_flab.get("xg"),
            "相手xG": opp_flab.get("xg"),
            "シュート数": fct_flab.get("shots"),
            "枠内シュート": fct_flab.get("shots_on_target"),
            "相手シュート数": opp_flab.get("shots"),
            "相手枠内シュート": opp_flab.get("shots_on_target"),
            "ボール支配率(%)": fct_flab.get("possession_rate"),
            "パス数": fct_flab.get("passes"),
            "パス成功率(%)": fct_flab.get("passes_rate"),
            "クロス数": fct_flab.get("crosses"),
            "クロス成功率(%)": fct_flab.get("crosses_rate"),
            "30mライン進入数": fct_flab.get("m30_entries"),
            "PA進入数": fct_flab.get("pa_entries"),
            "相手30m進入数": opp_flab.get("m30_entries"),
            "相手PA進入数": opp_flab.get("pa_entries"),
            "走行距離(km)": round((fct_flab.get("distance_m") or 0) / 1000.0, 1),
            "相手走行距離(km)": round((opp_flab.get("distance_m") or 0) / 1000.0, 1),
            "スプリント数": fct_flab.get("sprints"),
            "相手スプリント数": opp_flab.get("sprints"),
            "タックル数": fct_flab.get("tackles"),
            "タックル成功率(%)": fct_flab.get("tackles_rate"),
            "インターセプト": fct_flab.get("intercepts"),
            "クリア数": fct_flab.get("clears"),
            "ドリブル数": fct_flab.get("dribbles"),
            "コーナーキック": fct_flab.get("corner_kicks"),
            "攻撃回数": fct_flab.get("attack_count"),
            "チャンス構築率(%)": fct_flab.get("chance_create_rate"),
            # CBP metrics (correct points)
            "CBP_攻撃": fct_flab.get("cbp_attack"),
            "CBP_パス": fct_flab.get("cbp_pass"),
            "CBP_クロス": fct_flab.get("cbp_cross"),
            "CBP_ドリブル": fct_flab.get("cbp_dribble"),
            "CBP_シュート": fct_flab.get("cbp_shoot"),
            "CBP_奪取": fct_flab.get("cbp_gain"),
            "CBP_守備": fct_flab.get("cbp_defense"),
            "CBP_セーブ": fct_flab.get("cbp_save"),
        }
        records.append(row)

    return pd.DataFrame(records)


def build_layer1_events(conn: sqlite3.Connection, matches: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build Sheet: Layer 1 Match Events with strict GOAL vs CHANCE distinction."""
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()

    match_ids = [m["match_id"] for m in matches]
    placeholders = ",".join(["?"] * len(match_ids))

    cur.execute(
        f"""
        SELECT e.match_id, m.matchweek, m.date, e.minute, e.period, e.team_id,
               e.player_name, e.event_type, e.zone_name, e.xg, e.situation, e.description_text
        FROM match_events e
        JOIN matches m ON e.match_id = m.match_id
        WHERE e.match_id IN ({placeholders})
        ORDER BY m.matchweek ASC, e.minute ASC;
        """,
        match_ids,
    )
    rows = cur.fetchall()

    cleaned_rows = []
    for r in rows:
        row = dict(r)
        desc = row.get("description_text") or ""
        raw_type = row.get("event_type")

        # Refine GOAL type: check if it's a genuine goal vs a missed shot/telemetry text
        if raw_type == "GOAL":
            is_true_goal = ("GOOOOOAL!!" in desc) or (
                ("得点" in desc or "ゴールを決める" in desc or "ネットを揺らす" in desc)
                and not any(neg in desc for neg in ["外れる", "外れてしまう", "セーブ", "期待値", "シュート数", "ここまでのシュート", "枠上", "枠外"])
            )
            if is_true_goal:
                row["event_type"] = "GOAL (得点)"
            else:
                row["event_type"] = "SHOT_MISSED (決定機/枠外)"
        elif raw_type == "YELLOW_CARD":
            row["event_type"] = "CARD (警告)"
        elif raw_type == "RED_CARD":
            row["event_type"] = "CARD (退場)"

        cleaned_rows.append(row)

    return pd.DataFrame(cleaned_rows)


def build_layer1_player_match_stats(conn: sqlite3.Connection, matches: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build Sheet: Layer 1 Player Match Records (full 22 columns)."""
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()

    match_ids = [m["match_id"] for m in matches]
    placeholders = ",".join(["?"] * len(match_ids))

    cur.execute(
        f"""
        SELECT p.match_id, m.matchweek, m.date, p.player_name, p.number, p.position,
               p.is_starter, p.minutes_played, p.goals, p.assists,
               p.xg, p.xa, p.touches, p.duels_won, p.distance_km, p.sprints,
               p.avg_x, p.avg_y, p.cbp_points
        FROM player_match_stats p
        JOIN matches m ON p.match_id = m.match_id
        WHERE p.match_id IN ({placeholders}) AND p.team_id = 'FCT'
        ORDER BY m.matchweek ASC, p.is_starter DESC, p.minutes_played DESC;
        """,
        match_ids,
    )
    rows = cur.fetchall()
    return pd.DataFrame(rows)


def build_layer1_player_master() -> pd.DataFrame:
    """Build Sheet: Layer 1 Player Comprehensive Profile & Season Specs."""
    if not PLAYERS_JSON_PATH.exists():
        return pd.DataFrame([{"情報": "選手マスターファイルが見つかりません"}])

    data = json.loads(PLAYERS_JSON_PATH.read_text(encoding="utf-8"))
    records = []

    for p in data:
        ss = p.get("season_stats", {})
        row = {
            "選手ID": p.get("player_id"),
            "背番号": p.get("number"),
            "選手名": p.get("name"),
            "英語名": p.get("name_en"),
            "基本ポジション": p.get("position"),
            "詳細ポジション": p.get("detailed_position_ja"),
            "利き足": p.get("dominant_foot"),
            "身長(cm)": p.get("height_cm"),
            "体重(kg)": p.get("weight_kg"),
            "生年月日": p.get("birthdate"),
            "市場価値(EUR)": p.get("market_value_eur"),
            "2026出場試合数": p.get("matches"),
            "2026得点数": p.get("goals"),
            "特長・ストロングポイント": p.get("strong_points"),
            # Season breakdown stats
            "セーブ数": ss.get("セーブ数"),
            "セーブ率": ss.get("セーブ率"),
            "クリーンシート数": ss.get("クリーンシート数"),
            "PA外シュートキャッチ率": ss.get("PA外シュートキャッチ率"),
            "1試合平均パス数": ss.get("1試合平均パス数"),
            "1試合平均ロングパス数": ss.get("1試合平均ロングパス数"),
        }
        records.append(row)

    return pd.DataFrame(records)


def build_layer2_tactical_phases(matches: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build Sheet: Layer 2 Tactical Heuristics & Match Phases."""
    records = []
    structured_dir = ROOT_DIR / "data" / "structured"

    for m in matches:
        m_id = m["match_id"]
        json_path = structured_dir / f"{m_id}_tactical.json"
        if not json_path.exists():
            continue

        data = json.loads(json_path.read_text(encoding="utf-8"))
        is_home = (m["home_team_id"] == "FCT")

        fct_form = data.get("home_formation") if is_home else data.get("away_formation")
        opp_form = data.get("away_formation") if is_home else data.get("home_formation")

        highlights = data.get("tactical_highlights", [])
        h1 = highlights[0] if len(highlights) > 0 else ""
        h2 = highlights[1] if len(highlights) > 1 else ""
        h3 = highlights[2] if len(highlights) > 2 else ""

        phases = data.get("phases", [])
        phase_str = " | ".join([f"{p.get('phase')}: {p.get('dominant_team')}" for p in phases])

        records.append({
            "試合ID": m_id,
            "節": m["matchweek"],
            "開催日": m["date"],
            "対戦相手": m["away_team_id"] if is_home else m["home_team_id"],
            "FCT布陣(推定)": fct_form,
            "相手布陣(推定)": opp_form,
            "時間帯別主導権推移": phase_str,
            "基本方針と今節の狙い(Layer2)": h1,
            "せめぎ合いの力学評価(Layer3)": h2,
            "内容と結果の構造総括(Layer4)": h3,
        })

    return pd.DataFrame(records)


def build_layer2_synthetic_metrics(conn: sqlite3.Connection, matches: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build Sheet: Layer 2 Synthetic Advanced Tactical Metrics."""
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()

    records = []
    for m in matches:
        m_id = m["match_id"]
        is_home = (m["home_team_id"] == "FCT")
        opp_id = m["away_team_id"] if is_home else m["home_team_id"]
        fct_score = m["home_score"] if is_home else m["away_score"]
        opp_score = m["away_score"] if is_home else m["home_score"]

        cur.execute("SELECT * FROM team_match_flab_stats WHERE match_id = ? AND team_id = 'FCT'", (m_id,))
        f = cur.fetchone() or {}
        cur.execute("SELECT * FROM team_match_flab_stats WHERE match_id = ? AND team_id = ?", (m_id, opp_id))
        o = cur.fetchone() or {}

        # 1. Proxy-PPDA (Passes Allowed Per Defensive Action)
        opp_passes = o.get("passes") or 0
        fct_def_actions = (f.get("tackles") or 0) + (f.get("intercepts") or 0)
        proxy_ppda = round(opp_passes / max(1, fct_def_actions), 1)

        # 2. Directness (30m entries per 100 passes)
        fct_passes = f.get("passes") or 0
        fct_m30 = f.get("m30_entries") or 0
        directness = round((fct_m30 / (fct_passes / 100.0)), 2) if fct_passes > 0 else 0.0

        # 3. Wing/Cross Reliance (% of PA entries via crosses)
        fct_crosses = f.get("crosses") or 0
        fct_pa = f.get("pa_entries") or 0
        cross_reliance = round((fct_crosses / max(1, fct_pa) * 100.0), 1)

        # 4. Field Tilt (Final third territorial dominance)
        opp_m30 = o.get("m30_entries") or 0
        tot_m30 = fct_m30 + opp_m30
        field_tilt = round(fct_m30 / max(1, tot_m30) * 100.0, 1)

        # 5. Conversion Efficiency (30m to PA)
        conv_rate = round(fct_pa / max(1, fct_m30) * 100.0, 1)

        # 6. Midfield Recovery Score (CBP Gain + 2*Intercepts)
        recovery_score = round((f.get("cbp_gain") or 0.0) + ((f.get("intercepts") or 0) * 2.0), 1)

        # 7. Finishing Edge (Actual Score - xG)
        xg = f.get("xg") or 0.0
        finishing_edge = round(fct_score - xg, 2)

        # 8. GK Resilience (Opponent xG - Opponent Score)
        opp_xg = o.get("xg") or 0.0
        gk_resilience = round(opp_xg - opp_score, 2)

        records.append({
            "試合ID": m_id,
            "節": m["matchweek"],
            "開催日": m["date"],
            "対戦相手": opp_id,
            "実スコア": f"{fct_score} - {opp_score}",
            "① プレス強度(Proxy-PPDA)": proxy_ppda,
            "② 縦志向性(Directness)": directness,
            "③ クロス依存率(%)": cross_reliance,
            "④ 敵陣支配率(Field Tilt %)": field_tilt,
            "⑤ PA進入変換率(%)": conv_rate,
            "⑥ 中盤セカンドボール奪還力": recovery_score,
            "⑦ 決定力格差(得点 - xG)": finishing_edge,
            "⑧ 守護神阻止点(被xG - 失点)": gk_resilience,
        })

    return pd.DataFrame(records)


def build_layer2_club_profile() -> pd.DataFrame:
    """Build Sheet: Layer 2 Club Tactical Identity & Philosophical Master."""
    if not PROFILES_PATH.exists():
        return pd.DataFrame([{"情報": "プロファイルファイルが見つかりません"}])

    data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    fct = data.get("teams", {}).get("FCT", {})

    records = [
        {"項目": "クラブ名", "内容": fct.get("team_name", "FC東京")},
        {"項目": "基本フォーメーション", "内容": fct.get("base_formation", "4-2-3-1")},
        {"項目": "現監督", "内容": fct.get("manager", "松橋 力蔵")},
        {"項目": "基本戦術哲学", "内容": fct.get("base_style", "")},
        {"項目": "ビルドアップ志向", "内容": fct.get("build_up", "")},
        {"項目": "プレッシング志向", "内容": fct.get("pressing", "")},
        {"項目": "キーマン", "内容": ", ".join(fct.get("key_players", []))},
        {"項目": "構造的強み", "内容": " / ".join(fct.get("strengths", []))},
        {"項目": "構造的弱点・課題", "内容": " / ".join(fct.get("weaknesses", []))},
    ]
    return pd.DataFrame(records)


def export_fct_excel(output_path: Path = OUTPUT_FILE) -> Path:
    """Generate multi-sheet Excel file with Layer 1 & Layer 2 tactical data."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection(str(DEFAULT_DB_PATH))

    matches = get_fct_matches(conn)

    df_l1_team = build_layer1_team_stats(conn, matches)
    df_l1_events = build_layer1_events(conn, matches)
    df_l1_players = build_layer1_player_match_stats(conn, matches)
    df_l1_master = build_layer1_player_master()
    df_l2_phases = build_layer2_tactical_phases(matches)
    df_l2_synthetic = build_layer2_synthetic_metrics(conn, matches)
    df_l2_profile = build_layer2_club_profile()

    conn.close()

    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df_l2_synthetic.to_excel(writer, sheet_name="L2_先進戦術指標", index=False)
        df_l2_phases.to_excel(writer, sheet_name="L2_試合戦術プラン推移", index=False)
        df_l2_profile.to_excel(writer, sheet_name="L2_クラブ戦術プロファイル", index=False)
        df_l1_team.to_excel(writer, sheet_name="L1_チーム詳細スタッツ75項目", index=False)
        df_l1_players.to_excel(writer, sheet_name="L1_選手別試合出場スタッツ", index=False)
        df_l1_master.to_excel(writer, sheet_name="L1_選手詳細マスター", index=False)
        df_l1_events.to_excel(writer, sheet_name="L1_ゴール・重要イベント", index=False)

    print(f"[DONE] Successfully generated FC Tokyo Layer1 & Layer2 Dossier at: {output_path}")
    return output_path


if __name__ == "__main__":
    export_fct_excel()
