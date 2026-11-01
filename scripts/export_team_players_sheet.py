"""Team Players Sheet Exporter for Layer 1 Data Validation.

Exports all available player data for a specified team into an Excel spreadsheet
(with multiple detailed sheets) and corresponding CSV files.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd


def load_player_json(
    team_id: str,
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Loads player data JSON for the specified team."""
    if base_dir is None:
        base_dir = Path("data/players")
    file_path = base_dir / f"{team_id}_players.json"
    if not file_path.exists():
        raise FileNotFoundError(f"Player JSON not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def extract_cbp_metrics(cbp_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts CBP category points."""
    return {
        "CBP_攻撃": cbp_dict.get("attack"),
        "CBP_守備": cbp_dict.get("defense"),
        "CBP_奪取": cbp_dict.get("gain"),
        "CBP_パス": cbp_dict.get("pass"),
        "CBP_クロス": cbp_dict.get("cross"),
        "CBP_ドリブル": cbp_dict.get("dribble"),
        "CBP_シュート": cbp_dict.get("shoot"),
        "CBP_セーブ": cbp_dict.get("save"),
        "CBP_総合": cbp_dict.get("total"),
    }


def extract_area_and_discipline(
    area_dict: Dict[str, Any],
    disc_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Extracts area play counts and disciplinary metrics."""
    return {
        "総プレー数": area_dict.get("total"),
        "アタッキングサード_プレー数": area_dict.get("attacking_third"),
        "ミドルサード_プレー数": area_dict.get("middle_third"),
        "ディフェンシブサード_プレー数": area_dict.get("defensive_third"),
        "イエローカード": disc_dict.get("yellow_cards"),
        "レッドカード": disc_dict.get("red_cards"),
        "ファウル数": disc_dict.get("fouls"),
        "被ファウル数": disc_dict.get("suffer_fouls"),
    }


def extract_spaia_metrics(spaia_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts granular SPAIA tracking metrics."""
    fwd = spaia_dict.get("pass_forward") or {}
    crs = spaia_dict.get("pass_crossway") or {}
    bwd = spaia_dict.get("pass_backward") or {}

    return {
        "PA進入数": spaia_dict.get("pa_entries"),
        "PA進入_左サイド": spaia_dict.get("pa_side_left_entries"),
        "PA進入_右サイド": spaia_dict.get("pa_side_right_entries"),
        "30mライン進入数": spaia_dict.get("m30_entries"),
        "敵陣サード進入数": spaia_dict.get("at_3rd_entries"),
        "敵陣サードプレー率(%)": spaia_dict.get("at_play_rate"),
        "ミドルサードプレー率(%)": spaia_dict.get("mt_play_rate"),
        "自陣サードプレー率(%)": spaia_dict.get("dt_play_rate"),
        "SPAIA_パス数": spaia_dict.get("pass_count"),
        "SPAIA_パス成功率(%)": spaia_dict.get("pass_rate"),
        "前方向パス数": fwd.get("count"),
        "前方向パス成功率(%)": fwd.get("success_rate"),
        "横方向パス数": crs.get("count"),
        "横方向パス成功率(%)": crs.get("success_rate"),
        "後方向パス数": bwd.get("count"),
        "後方向パス成功率(%)": bwd.get("success_rate"),
        "敵陣パス数": spaia_dict.get("opp_area_pass_count"),
        "敵陣パス成功率(%)": spaia_dict.get("opp_area_pass_rate"),
        "クロス数": spaia_dict.get("cross_count"),
        "クロス成功率(%)": spaia_dict.get("cross_rate"),
        "ドリブル数": spaia_dict.get("dribble_count"),
        "ドリブル成功率(%)": spaia_dict.get("dribble_rate"),
        "クリア数": spaia_dict.get("clear_count"),
        "タックル数": spaia_dict.get("tackle_count"),
        "敵陣サードタックル": spaia_dict.get("at_3rd_tackle"),
        "敵陣タックル": spaia_dict.get("opp_area_tackle"),
        "セーブ数": spaia_dict.get("save_count"),
        "セーブ率(%)": spaia_dict.get("save_rate"),
    }


def extract_yahoo_metrics(yahoo_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts supplementary Yahoo soccer action metrics."""
    return {
        "シュート数": yahoo_dict.get("shoots"),
        "枠内シュート数": yahoo_dict.get("shoots_on_target"),
        "敵陣サードパス数": yahoo_dict.get("attacking_third_passes"),
        "スルーパス数": yahoo_dict.get("through_passes"),
        "ドリブル成功数": yahoo_dict.get("dribble_success"),
        "こぼれ球奪取": yahoo_dict.get("loose_ball_recoveries"),
        "シュートブロック": yahoo_dict.get("blocks"),
        "FK獲得": yahoo_dict.get("fk_count"),
        "CK獲得": yahoo_dict.get("ck_count"),
    }


def flatten_raw_stats_json(raw_json_str: Optional[str]) -> Dict[str, Any]:
    """Flattens the entire raw_stats_json containing Football Lab/SPAIA/Yahoo data."""
    if not raw_json_str:
        return {}
    try:
        data = json.loads(raw_json_str)
    except Exception:
        return {}

    flat: Dict[str, Any] = {
        "評点(Rating)": data.get("rating"),
        "最高時速(km/h)": data.get("max_speed_kmh"),
        "走行距離_前半(km)": data.get("distance_first_half"),
        "走行距離_後半(km)": data.get("distance_second_half"),
        "スプリント_前半": data.get("sprints_first_half"),
        "スプリント_後半": data.get("sprints_second_half"),
    }

    flat.update(extract_area_and_discipline(
        data.get("plays_by_area") or {},
        data.get("discipline") or {},
    ))
    flat.update(extract_cbp_metrics(data.get("cbp") or {}))
    flat.update(extract_spaia_metrics(data.get("spaia") or {}))
    flat.update(extract_yahoo_metrics(data.get("yahoo") or {}))

    return flat


def load_player_match_stats(
    team_id: str,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Loads match stats logs for the team and expands all raw JSON metrics."""
    if db_path is None:
        db_path = Path("data/football.db")
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    query = """
        SELECT
            pms.id,
            pms.match_id,
            pms.player_id,
            pms.player_name,
            pms.team_id,
            pms.is_starter,
            pms.minutes_played,
            pms.position,
            pms.number,
            pms.goals,
            pms.assists,
            pms.xg,
            pms.xa,
            pms.touches,
            pms.duels_won,
            pms.distance_km,
            pms.sprints,
            pms.avg_x,
            pms.avg_y,
            pms.cbp_points,
            pms.raw_stats_json,
            pms.created_at,
            pmp.primary_role,
            pmp.primary_lane,
            pmp.fluidity_tags_json
        FROM player_match_stats pms
        LEFT JOIN player_match_positions pmp
            ON pms.match_id = pmp.match_id
            AND pms.team_id = pmp.team_id
            AND (pms.player_name = pmp.player_name OR pms.player_id = pmp.player_id)
        WHERE pms.team_id = ?
        ORDER BY pms.player_name, pms.match_id
    """
    cur.execute(query, (team_id,))
    rows = cur.fetchall()
    conn.close()

    parsed_rows: List[Dict[str, Any]] = []
    for r in rows:
        row_dict = dict(r)
        raw_str = row_dict.pop("raw_stats_json", None)

        record: Dict[str, Any] = {
            "試合ID": row_dict.get("match_id"),
            "選手名": row_dict.get("player_name"),
            "選手ID": row_dict.get("player_id"),
            "先発区分": "先発" if row_dict.get("is_starter") == 1 else "途中出場/ベンチ",
            "出場時間(分)": row_dict.get("minutes_played"),
            "ポジション": row_dict.get("position"),
            "戦術ロール": row_dict.get("primary_role"),
            "主戦レーン": row_dict.get("primary_lane"),
            "流動性タグ": row_dict.get("fluidity_tags_json"),
            "背番号": row_dict.get("number"),
            "得点": row_dict.get("goals"),
            "アシスト": row_dict.get("assists"),
            "ゴール期待値(xG)": row_dict.get("xg"),
            "アシスト期待値(xA)": row_dict.get("xa"),
            "走行距離(km)": row_dict.get("distance_km"),
            "スプリント回数": row_dict.get("sprints"),
            "ボールタッチ数": row_dict.get("touches"),
            "デュエル勝利数": row_dict.get("duels_won"),
            "総合CBP点": row_dict.get("cbp_points"),
            "平均位置_X": row_dict.get("avg_x"),
            "平均位置_Y": row_dict.get("avg_y"),
        }

        # Expand all granular metrics from Football Lab / SPAIA / Yahoo
        flat_raw = flatten_raw_stats_json(raw_str)
        record.update(flat_raw)
        parsed_rows.append(record)

    return parsed_rows


def build_basic_info_records(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extracts flat basic profile and contract records for each player."""
    records: List[Dict[str, Any]] = []
    for p in players:
        strong_points = " / ".join(p.get("strong_points") or [])
        nationalities = ", ".join(p.get("nationalities") or [])

        record = {
            "選手ID": p.get("player_id"),
            "背番号": p.get("number"),
            "氏名": p.get("name"),
            "英語表記": p.get("name_en"),
            "ポジション": p.get("position"),
            "詳細ポジション": p.get("detailed_position_ja"),
            "詳細ポジションコード": p.get("detailed_position_code"),
            "利き足": p.get("dominant_foot"),
            "生年月日": p.get("birthdate"),
            "身長(cm)": p.get("height_cm"),
            "体重(kg)": p.get("weight_kg"),
            "出身地": p.get("birthplace"),
            "国籍": nationalities,
            "前所属クラブ": p.get("previous_club"),
            "加入日": p.get("joined_date"),
            "契約満了日": p.get("contract_until"),
            "市場価値(EUR)": p.get("market_value_eur"),
            "レンタル元": p.get("loan_from_club"),
            "レンタル期限": p.get("loan_until"),
            "通算出場数": p.get("matches"),
            "通算得点数": p.get("goals"),
            "代表歴キャップ": p.get("national_team_caps"),
            "J初出場日": p.get("jleague_debut"),
            "J初得点日": p.get("jleague_first_goal"),
            "スカウティング特徴・強み": strong_points,
            "Transfermarkt_ID": p.get("tm_player_id"),
            "写真URL": p.get("photo_url"),
        }
        records.append(record)
    return records


def build_season_stats_records(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extracts official detailed season stats for each player."""
    records: List[Dict[str, Any]] = []
    for p in players:
        stats = p.get("season_stats") or {}
        row: Dict[str, Any] = {
            "選手ID": p.get("player_id"),
            "背番号": p.get("number"),
            "氏名": p.get("name"),
            "ポジション": p.get("position"),
        }
        for k, v in stats.items():
            row[k] = v
        records.append(row)
    return records


def build_career_history_records(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extracts year-by-year career history for all players."""
    records: List[Dict[str, Any]] = []
    for p in players:
        history = p.get("career_history") or []
        for h in history:
            records.append({
                "選手ID": p.get("player_id"),
                "氏名": p.get("name"),
                "年度": h.get("season"),
                "所属クラブ": h.get("club"),
                "所属リーグ": h.get("league"),
                "出場試合数": h.get("league_matches"),
                "得点数": h.get("league_goals"),
            })
    return records


def aggregate_player_metrics(p_matches: pd.DataFrame) -> Dict[str, Any]:
    """Helper to aggregate granular metrics across a player's matches."""
    m_count = len(p_matches)
    starts = int((p_matches["先発区分"] == "先発").sum())
    total_mins = int(p_matches["出場時間(分)"].fillna(0).sum())
    total_goals = int(p_matches["得点"].fillna(0).sum())
    total_assists = int(p_matches["アシスト"].fillna(0).sum())
    total_xg = float(p_matches["ゴール期待値(xG)"].fillna(0.0).sum())
    total_xa = float(p_matches["アシスト期待値(xA)"].fillna(0.0).sum())

    avg_dist = float(p_matches["走行距離(km)"].fillna(0.0).mean())
    avg_sprints = float(p_matches["スプリント回数"].fillna(0.0).mean())
    avg_duels = float(p_matches["デュエル勝利数"].fillna(0.0).mean())
    avg_cbp = float(p_matches["総合CBP点"].fillna(0.0).mean())

    # Expanded granular aggregations
    avg_rating = float(p_matches["評点(Rating)"].dropna().mean()) if "評点(Rating)" in p_matches.columns and not p_matches["評点(Rating)"].dropna().empty else None
    max_speed = float(p_matches["最高時速(km/h)"].dropna().max()) if "最高時速(km/h)" in p_matches.columns and not p_matches["最高時速(km/h)"].dropna().empty else None
    total_shoots = int(p_matches["シュート数"].fillna(0).sum()) if "シュート数" in p_matches.columns else 0
    total_on_target = int(p_matches["枠内シュート数"].fillna(0).sum()) if "枠内シュート数" in p_matches.columns else 0
    total_pa_entries = int(p_matches["PA進入数"].fillna(0).sum()) if "PA進入数" in p_matches.columns else 0
    total_tackles = int(p_matches["タックル数"].fillna(0).sum()) if "タックル数" in p_matches.columns else 0
    total_clears = int(p_matches["クリア数"].fillna(0).sum()) if "クリア数" in p_matches.columns else 0
    total_loose_balls = int(p_matches["こぼれ球奪取"].fillna(0).sum()) if "こぼれ球奪取" in p_matches.columns else 0
    avg_pass_rate = float(p_matches["SPAIA_パス成功率(%)"].dropna().mean()) if "SPAIA_パス成功率(%)" in p_matches.columns and not p_matches["SPAIA_パス成功率(%)"].dropna().empty else None

    return {
        "DB記録試合数": m_count,
        "先発回数": starts,
        "総出場時間(分)": total_mins,
        "平均評点": round(avg_rating, 2) if avg_rating is not None else None,
        "ゴール": total_goals,
        "アシスト": total_assists,
        "総xG": round(total_xg, 2),
        "総xA": round(total_xa, 2),
        "総シュート数": total_shoots,
        "総枠内シュート": total_on_target,
        "平均パス成功率(%)": round(avg_pass_rate, 1) if avg_pass_rate is not None else None,
        "総PA進入数": total_pa_entries,
        "総タックル数": total_tackles,
        "総クリア数": total_clears,
        "総こぼれ球奪取": total_loose_balls,
        "最高時速(km/h)": round(max_speed, 1) if max_speed is not None else None,
        "平均走行距離(km)": round(avg_dist, 2),
        "平均スプリント": round(avg_sprints, 1),
        "平均デュエル勝利数": round(avg_duels, 1),
        "平均CBP": round(avg_cbp, 1),
    }


def build_match_summary_records(
    players: List[Dict[str, Any]],
    match_stats: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Aggregates DB match performance logs per player with expanded metrics."""
    stats_df = pd.DataFrame(match_stats) if match_stats else pd.DataFrame()
    records: List[Dict[str, Any]] = []

    for p in players:
        p_name = p.get("name")
        p_id = p.get("player_id")

        if stats_df.empty or "選手名" not in stats_df.columns:
            p_matches = pd.DataFrame()
        else:
            p_matches = stats_df[stats_df["選手名"] == p_name]

        if not p_matches.empty:
            agg = aggregate_player_metrics(p_matches)
        else:
            agg = {
                "DB記録試合数": 0,
                "先発回数": 0,
                "総出場時間(分)": 0,
                "平均評点": None,
                "ゴール": 0,
                "アシスト": 0,
                "総xG": 0.0,
                "総xA": 0.0,
                "総シュート数": 0,
                "総枠内シュート": 0,
                "平均パス成功率(%)": None,
                "総PA進入数": 0,
                "総タックル数": 0,
                "総クリア数": 0,
                "総こぼれ球奪取": 0,
                "最高時速(km/h)": None,
                "平均走行距離(km)": 0.0,
                "平均スプリント": 0.0,
                "平均デュエル勝利数": 0.0,
                "平均CBP": 0.0,
            }

        rec = {
            "選手ID": p_id,
            "氏名": p_name,
            "ポジション": p.get("position"),
        }
        rec.update(agg)
        records.append(rec)

    return records


def export_team_to_excel(
    team_id: str,
    output_excel_path: Path,
    players: List[Dict[str, Any]],
    match_stats: List[Dict[str, Any]],
) -> Path:
    """Exports all team player data into a multi-sheet Excel file.
    
    If the target file is locked (e.g., currently open in Excel), it gracefully
    falls back to saving with a secondary filename.
    """
    output_excel_path.parent.mkdir(parents=True, exist_ok=True)

    df_basic = pd.DataFrame(build_basic_info_records(players))
    df_summary = pd.DataFrame(build_match_summary_records(players, match_stats))
    df_season = pd.DataFrame(build_season_stats_records(players))
    df_career = pd.DataFrame(build_career_history_records(players))
    df_match_logs = pd.DataFrame(match_stats)

    target_path = output_excel_path
    try:
        with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
            df_basic.to_excel(writer, sheet_name="1_基本情報・契約", index=False)
            df_summary.to_excel(writer, sheet_name="2_実戦スタッツ集計(DB)", index=False)
            df_season.to_excel(writer, sheet_name="3_公式詳細スタッツ", index=False)
            df_career.to_excel(writer, sheet_name="4_年度別キャリア履歴", index=False)
            if not df_match_logs.empty:
                df_match_logs.to_excel(writer, sheet_name="5_試合別詳細生ログ(DB)", index=False)
    except PermissionError:
        # Fallback if file is locked by user in Excel
        fallback_path = output_excel_path.parent / f"{output_excel_path.stem}_new{output_excel_path.suffix}"
        with pd.ExcelWriter(fallback_path, engine="openpyxl") as writer:
            df_basic.to_excel(writer, sheet_name="1_基本情報・契約", index=False)
            df_summary.to_excel(writer, sheet_name="2_実戦スタッツ集計(DB)", index=False)
            df_season.to_excel(writer, sheet_name="3_公式詳細スタッツ", index=False)
            df_career.to_excel(writer, sheet_name="4_年度別キャリア履歴", index=False)
            if not df_match_logs.empty:
                df_match_logs.to_excel(writer, sheet_name="5_試合別詳細生ログ(DB)", index=False)
        target_path = fallback_path

    return target_path


def export_team_to_csvs(
    team_id: str,
    output_dir: Path,
    players: List[Dict[str, Any]],
    match_stats: List[Dict[str, Any]],
) -> List[Path]:
    """Exports each record set into UTF-8-SIG CSV files for convenience."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: List[Path] = []

    sets = [
        (f"{team_id}_1_basic_info.csv", build_basic_info_records(players)),
        (f"{team_id}_2_match_stats_summary.csv", build_match_summary_records(players, match_stats)),
        (f"{team_id}_3_official_season_stats.csv", build_season_stats_records(players)),
        (f"{team_id}_4_career_history.csv", build_career_history_records(players)),
    ]

    for filename, records in sets:
        csv_path = output_dir / filename
        df = pd.DataFrame(records)
        try:
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            generated_paths.append(csv_path)
        except PermissionError:
            fallback_csv = output_dir / f"{csv_path.stem}_new{csv_path.suffix}"
            df.to_csv(fallback_csv, index=False, encoding="utf-8-sig")
            generated_paths.append(fallback_csv)

    if match_stats:
        match_csv = output_dir / f"{team_id}_5_match_logs.csv"
        try:
            pd.DataFrame(match_stats).to_csv(match_csv, index=False, encoding="utf-8-sig")
            generated_paths.append(match_csv)
        except PermissionError:
            fallback_mcsv = output_dir / f"{match_csv.stem}_new{match_csv.suffix}"
            pd.DataFrame(match_stats).to_csv(fallback_mcsv, index=False, encoding="utf-8-sig")
            generated_paths.append(fallback_mcsv)

    return generated_paths


def export_team_player_data(team_id: str = "FCT") -> Dict[str, Any]:
    """Main export execution function for a given team."""
    players = load_player_json(team_id)
    match_stats = load_player_match_stats(team_id)

    excel_path = Path(f"exports/players/{team_id}_players.xlsx")
    actual_excel = export_team_to_excel(team_id, excel_path, players, match_stats)

    csv_dir = Path("exports/players")
    csv_paths = export_team_to_csvs(team_id, csv_dir, players, match_stats)

    return {
        "team_id": team_id,
        "player_count": len(players),
        "match_stats_count": len(match_stats),
        "excel_path": str(actual_excel),
        "csv_paths": [str(p) for p in csv_paths],
    }


if __name__ == "__main__":
    import sys
    target_team = sys.argv[1] if len(sys.argv) > 1 else "FCT"
    result = export_team_player_data(target_team)
    print(f"Export completed for {result['team_id']}:")
    print(f"  Players: {result['player_count']}")
    print(f"  Match stats logs: {result['match_stats_count']}")
    print(f"  Excel: {result['excel_path']}")
    for cp in result["csv_paths"]:
        print(f"  CSV: {cp}")
