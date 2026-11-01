# -*- coding: utf-8 -*-
"""
Football LAB チームスタッツ インジェスター (pipeline/flab_team_stats_ingester.py).
data/raw/football_lab/*.json から全120試合・全クラブのインターセプト、CK、クロス、
タックル、CBP等の詳細スタッツを安全にパースし、DBテーブル `team_match_flab_stats` に格納する。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("flab_team_stats_ingester")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_FLAB_DIR = ROOT_DIR / "data" / "raw" / "football_lab"


def safe_float(val: Any) -> Optional[float]:
    """文字列（'26.1%', '1.778', '(14.78)', '-' など）を安全に float に変換する。"""
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    s = re.sub(r"[()%m\s]", "", s)
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def safe_int(val: Any) -> Optional[int]:
    """文字列（'116,883m', '23', '-' など）を安全に int に変換する。"""
    f = safe_float(val)
    if f is None:
        return None
    return int(round(f))


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team_match_flab_stats (
    match_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    is_home INTEGER NOT NULL,
    opponent_team_id TEXT NOT NULL,
    
    -- 基本スタッツ（実数、成功率、今季平均）
    xg REAL,
    xg_avg REAL,
    shots INTEGER,
    shots_rate REAL,
    shots_avg REAL,
    shots_on_target INTEGER,
    shots_on_target_avg REAL,
    passes INTEGER,
    passes_rate REAL,
    passes_avg REAL,
    crosses INTEGER,
    crosses_rate REAL,
    crosses_avg REAL,
    direct_fk INTEGER,
    direct_fk_avg REAL,
    indirect_fk INTEGER,
    indirect_fk_avg REAL,
    corner_kicks INTEGER,
    corner_kicks_avg REAL,
    throw_ins INTEGER,
    throw_ins_rate REAL,
    throw_ins_avg REAL,
    dribbles INTEGER,
    dribbles_rate REAL,
    dribbles_avg REAL,
    tackles INTEGER,
    tackles_rate REAL,
    tackles_avg REAL,
    clears INTEGER,
    clears_avg REAL,
    intercepts INTEGER,
    intercepts_avg REAL,
    offsides INTEGER,
    offsides_avg REAL,
    yellow_cards INTEGER,
    yellow_cards_avg REAL,
    red_cards INTEGER,
    red_cards_avg REAL,
    m30_entries INTEGER,
    m30_entries_avg REAL,
    pa_entries INTEGER,
    pa_entries_avg REAL,
    distance_m INTEGER,
    distance_m_avg REAL,
    sprints INTEGER,
    sprints_avg REAL,
    attack_count INTEGER,
    attack_count_avg REAL,
    chance_create_rate REAL,
    chance_create_rate_avg REAL,
    possession_rate REAL,
    possession_rate_avg REAL,

    -- CBP (チャンスビルディングポイント)
    cbp_attack REAL,
    cbp_attack_avg REAL,
    cbp_pass REAL,
    cbp_pass_avg REAL,
    cbp_cross REAL,
    cbp_cross_avg REAL,
    cbp_dribble REAL,
    cbp_dribble_avg REAL,
    cbp_shoot REAL,
    cbp_shoot_avg REAL,
    cbp_gain REAL,
    cbp_gain_avg REAL,
    cbp_defense REAL,
    cbp_defense_avg REAL,
    cbp_save REAL,
    cbp_save_avg REAL,

    raw_stats_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_id, team_id)
);
"""

UPSERT_SQL = """
INSERT INTO team_match_flab_stats (
    match_id, team_id, is_home, opponent_team_id,
    xg, xg_avg,
    shots, shots_rate, shots_avg,
    shots_on_target, shots_on_target_avg,
    passes, passes_rate, passes_avg,
    crosses, crosses_rate, crosses_avg,
    direct_fk, direct_fk_avg,
    indirect_fk, indirect_fk_avg,
    corner_kicks, corner_kicks_avg,
    throw_ins, throw_ins_rate, throw_ins_avg,
    dribbles, dribbles_rate, dribbles_avg,
    tackles, tackles_rate, tackles_avg,
    clears, clears_avg,
    intercepts, intercepts_avg,
    offsides, offsides_avg,
    yellow_cards, yellow_cards_avg,
    red_cards, red_cards_avg,
    m30_entries, m30_entries_avg,
    pa_entries, pa_entries_avg,
    distance_m, distance_m_avg,
    sprints, sprints_avg,
    attack_count, attack_count_avg,
    chance_create_rate, chance_create_rate_avg,
    possession_rate, possession_rate_avg,
    cbp_attack, cbp_attack_avg,
    cbp_pass, cbp_pass_avg,
    cbp_cross, cbp_cross_avg,
    cbp_dribble, cbp_dribble_avg,
    cbp_shoot, cbp_shoot_avg,
    cbp_gain, cbp_gain_avg,
    cbp_defense, cbp_defense_avg,
    cbp_save, cbp_save_avg,
    raw_stats_json
) VALUES (
    ?, ?, ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?
) ON CONFLICT(match_id, team_id) DO UPDATE SET
    is_home = excluded.is_home,
    opponent_team_id = excluded.opponent_team_id,
    xg = excluded.xg,
    xg_avg = excluded.xg_avg,
    shots = excluded.shots,
    shots_rate = excluded.shots_rate,
    shots_avg = excluded.shots_avg,
    shots_on_target = excluded.shots_on_target,
    shots_on_target_avg = excluded.shots_on_target_avg,
    passes = excluded.passes,
    passes_rate = excluded.passes_rate,
    passes_avg = excluded.passes_avg,
    crosses = excluded.crosses,
    crosses_rate = excluded.crosses_rate,
    crosses_avg = excluded.crosses_avg,
    direct_fk = excluded.direct_fk,
    direct_fk_avg = excluded.direct_fk_avg,
    indirect_fk = excluded.indirect_fk,
    indirect_fk_avg = excluded.indirect_fk_avg,
    corner_kicks = excluded.corner_kicks,
    corner_kicks_avg = excluded.corner_kicks_avg,
    throw_ins = excluded.throw_ins,
    throw_ins_rate = excluded.throw_ins_rate,
    throw_ins_avg = excluded.throw_ins_avg,
    dribbles = excluded.dribbles,
    dribbles_rate = excluded.dribbles_rate,
    dribbles_avg = excluded.dribbles_avg,
    tackles = excluded.tackles,
    tackles_rate = excluded.tackles_rate,
    tackles_avg = excluded.tackles_avg,
    clears = excluded.clears,
    clears_avg = excluded.clears_avg,
    intercepts = excluded.intercepts,
    intercepts_avg = excluded.intercepts_avg,
    offsides = excluded.offsides,
    offsides_avg = excluded.offsides_avg,
    yellow_cards = excluded.yellow_cards,
    yellow_cards_avg = excluded.yellow_cards_avg,
    red_cards = excluded.red_cards,
    red_cards_avg = excluded.red_cards_avg,
    m30_entries = excluded.m30_entries,
    m30_entries_avg = excluded.m30_entries_avg,
    pa_entries = excluded.pa_entries,
    pa_entries_avg = excluded.pa_entries_avg,
    distance_m = excluded.distance_m,
    distance_m_avg = excluded.distance_m_avg,
    sprints = excluded.sprints,
    sprints_avg = excluded.sprints_avg,
    attack_count = excluded.attack_count,
    attack_count_avg = excluded.attack_count_avg,
    chance_create_rate = excluded.chance_create_rate,
    chance_create_rate_avg = excluded.chance_create_rate_avg,
    possession_rate = excluded.possession_rate,
    possession_rate_avg = excluded.possession_rate_avg,
    cbp_attack = excluded.cbp_attack,
    cbp_attack_avg = excluded.cbp_attack_avg,
    cbp_pass = excluded.cbp_pass,
    cbp_pass_avg = excluded.cbp_pass_avg,
    cbp_cross = excluded.cbp_cross,
    cbp_cross_avg = excluded.cbp_cross_avg,
    cbp_dribble = excluded.cbp_dribble,
    cbp_dribble_avg = excluded.cbp_dribble_avg,
    cbp_shoot = excluded.cbp_shoot,
    cbp_shoot_avg = excluded.cbp_shoot_avg,
    cbp_gain = excluded.cbp_gain,
    cbp_gain_avg = excluded.cbp_gain_avg,
    cbp_defense = excluded.cbp_defense,
    cbp_defense_avg = excluded.cbp_defense_avg,
    cbp_save = excluded.cbp_save,
    cbp_save_avg = excluded.cbp_save_avg,
    raw_stats_json = excluded.raw_stats_json,
    updated_at = CURRENT_TIMESTAMP;
"""


def parse_flab_team_side(
    match_id: str,
    team_id: str,
    is_home: bool,
    opponent_team_id: str,
    stats_list: List[Dict[str, Any]],
    cbp_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """片方のチーム（Home または Away）のスタッツレコードを構築する。"""
    prefix = "home_" if is_home else "away_"
    val_k = f"{prefix}val"
    rate_k = f"{prefix}rate"
    avg_k = f"{prefix}avg"

    # スタッツの項目名引き辞書作成
    stat_map: Dict[str, Dict[str, Any]] = {}
    for item in stats_list:
        name = item.get("name")
        if name:
            stat_map[name.strip()] = item

    def get_v(name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        d = stat_map.get(name, {})
        return d.get(val_k), d.get(rate_k), d.get(avg_k)

    # 各スタッツの抽出
    xg_v, _, xg_avg = get_v("ゴール期待値")
    shots_v, shots_r, shots_avg = get_v("シュート")
    sot_v, _, sot_avg = get_v("枠内シュート")
    pass_v, pass_r, pass_avg = get_v("パス")
    cross_v, cross_r, cross_avg = get_v("クロス")
    dfk_v, _, dfk_avg = get_v("直接ＦＫ")
    ifk_v, _, ifk_avg = get_v("間接ＦＫ")
    ck_v, _, ck_avg = get_v("ＣＫ")
    ti_v, ti_r, ti_avg = get_v("スローイン")
    drib_v, drib_r, drib_avg = get_v("ドリブル")
    tack_v, tack_r, tack_avg = get_v("タックル")
    clr_v, _, clr_avg = get_v("クリア")
    int_v, _, int_avg = get_v("インターセプト")
    off_v, _, off_avg = get_v("オフサイド")
    yel_v, _, yel_avg = get_v("警告")
    red_v, _, red_avg = get_v("退場")
    m30_v, _, m30_avg = get_v("３０ｍライン進入")
    pa_v, _, pa_avg = get_v("ペナルティエリア進入")
    dist_v, _, dist_avg = get_v("総移動距離")
    sp_v, _, sp_avg = get_v("スプリント")
    att_v, _, att_avg = get_v("攻撃回数")
    ccr_v, _, ccr_avg = get_v("チャンス構築率")
    pos_v, _, pos_avg = get_v("ボール保持率")

    # CBPのチーム集計
    cbp_team_list = cbp_dict.get("team", [])
    cbp_map: Dict[str, Dict[str, Any]] = {}
    for c_item in cbp_team_list:
        c_name = c_item.get("name")
        if c_name:
            cbp_map[c_name.strip()] = c_item

    def get_cbp(c_name: str) -> Tuple[Optional[float], Optional[float]]:
        cd = cbp_map.get(c_name, {})
        return safe_float(cd.get(val_k)), safe_float(cd.get(avg_k))

    rec = {
        "match_id": match_id,
        "team_id": team_id,
        "is_home": 1 if is_home else 0,
        "opponent_team_id": opponent_team_id,
        "xg": safe_float(xg_v),
        "xg_avg": safe_float(xg_avg),
        "shots": safe_int(shots_v),
        "shots_rate": safe_float(shots_r),
        "shots_avg": safe_float(shots_avg),
        "shots_on_target": safe_int(sot_v),
        "shots_on_target_avg": safe_float(sot_avg),
        "passes": safe_int(pass_v),
        "passes_rate": safe_float(pass_r),
        "passes_avg": safe_float(pass_avg),
        "crosses": safe_int(cross_v),
        "crosses_rate": safe_float(cross_r),
        "crosses_avg": safe_float(cross_avg),
        "direct_fk": safe_int(dfk_v),
        "direct_fk_avg": safe_float(dfk_avg),
        "indirect_fk": safe_int(ifk_v),
        "indirect_fk_avg": safe_float(ifk_avg),
        "corner_kicks": safe_int(ck_v),
        "corner_kicks_avg": safe_float(ck_avg),
        "throw_ins": safe_int(ti_v),
        "throw_ins_rate": safe_float(ti_r),
        "throw_ins_avg": safe_float(ti_avg),
        "dribbles": safe_int(drib_v),
        "dribbles_rate": safe_float(drib_r),
        "dribbles_avg": safe_float(drib_avg),
        "tackles": safe_int(tack_v),
        "tackles_rate": safe_float(tack_r),
        "tackles_avg": safe_float(tack_avg),
        "clears": safe_int(clr_v),
        "clears_avg": safe_float(clr_avg),
        "intercepts": safe_int(int_v),
        "intercepts_avg": safe_float(int_avg),
        "offsides": safe_int(off_v),
        "offsides_avg": safe_float(off_avg),
        "yellow_cards": safe_int(yel_v),
        "yellow_cards_avg": safe_float(yel_avg),
        "red_cards": safe_int(red_v),
        "red_cards_avg": safe_float(red_avg),
        "m30_entries": safe_int(m30_v),
        "m30_entries_avg": safe_float(m30_avg),
        "pa_entries": safe_int(pa_v),
        "pa_entries_avg": safe_float(pa_avg),
        "distance_m": safe_int(dist_v),
        "distance_m_avg": safe_float(dist_avg),
        "sprints": safe_int(sp_v),
        "sprints_avg": safe_float(sp_avg),
        "attack_count": safe_int(att_v),
        "attack_count_avg": safe_float(att_avg),
        "chance_create_rate": safe_float(ccr_v),
        "chance_create_rate_avg": safe_float(ccr_avg),
        "possession_rate": safe_float(pos_v),
        "possession_rate_avg": safe_float(pos_avg),
        "cbp_attack": get_cbp("攻撃")[0],
        "cbp_attack_avg": get_cbp("攻撃")[1],
        "cbp_pass": get_cbp("パス")[0],
        "cbp_pass_avg": get_cbp("パス")[1],
        "cbp_cross": get_cbp("クロス")[0],
        "cbp_cross_avg": get_cbp("クロス")[1],
        "cbp_dribble": get_cbp("ドリブル")[0],
        "cbp_dribble_avg": get_cbp("ドリブル")[1],
        "cbp_shoot": get_cbp("シュート")[0],
        "cbp_shoot_avg": get_cbp("シュート")[1],
        "cbp_gain": get_cbp("奪取")[0],
        "cbp_gain_avg": get_cbp("奪取")[1],
        "cbp_defense": get_cbp("守備")[0],
        "cbp_defense_avg": get_cbp("守備")[1],
        "cbp_save": get_cbp("セーブ")[0],
        "cbp_save_avg": get_cbp("セーブ")[1],
        "raw_stats_json": json.dumps(stat_map, ensure_ascii=False),
    }
    return rec


def record_to_tuple(r: Dict[str, Any]) -> Tuple[Any, ...]:
    """辞書レコードを UPSERT_SQL 用のタプルに変換する。"""
    return (
        r["match_id"],
        r["team_id"],
        r["is_home"],
        r["opponent_team_id"],
        r["xg"],
        r["xg_avg"],
        r["shots"],
        r["shots_rate"],
        r["shots_avg"],
        r["shots_on_target"],
        r["shots_on_target_avg"],
        r["passes"],
        r["passes_rate"],
        r["passes_avg"],
        r["crosses"],
        r["crosses_rate"],
        r["crosses_avg"],
        r["direct_fk"],
        r["direct_fk_avg"],
        r["indirect_fk"],
        r["indirect_fk_avg"],
        r["corner_kicks"],
        r["corner_kicks_avg"],
        r["throw_ins"],
        r["throw_ins_rate"],
        r["throw_ins_avg"],
        r["dribbles"],
        r["dribbles_rate"],
        r["dribbles_avg"],
        r["tackles"],
        r["tackles_rate"],
        r["tackles_avg"],
        r["clears"],
        r["clears_avg"],
        r["intercepts"],
        r["intercepts_avg"],
        r["offsides"],
        r["offsides_avg"],
        r["yellow_cards"],
        r["yellow_cards_avg"],
        r["red_cards"],
        r["red_cards_avg"],
        r["m30_entries"],
        r["m30_entries_avg"],
        r["pa_entries"],
        r["pa_entries_avg"],
        r["distance_m"],
        r["distance_m_avg"],
        r["sprints"],
        r["sprints_avg"],
        r["attack_count"],
        r["attack_count_avg"],
        r["chance_create_rate"],
        r["chance_create_rate_avg"],
        r["possession_rate"],
        r["possession_rate_avg"],
        r["cbp_attack"],
        r["cbp_attack_avg"],
        r["cbp_pass"],
        r["cbp_pass_avg"],
        r["cbp_cross"],
        r["cbp_cross_avg"],
        r["cbp_dribble"],
        r["cbp_dribble_avg"],
        r["cbp_shoot"],
        r["cbp_shoot_avg"],
        r["cbp_gain"],
        r["cbp_gain_avg"],
        r["cbp_defense"],
        r["cbp_defense_avg"],
        r["cbp_save"],
        r["cbp_save_avg"],
        r["raw_stats_json"],
    )


def ingest_all_flab_team_stats(
    db_path: Path = DEFAULT_DB_PATH,
    flab_dir: Path = DEFAULT_FLAB_DIR,
) -> Dict[str, Any]:
    """data/raw/football_lab から全試合のチームスタッツをDBに格納する。"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(CREATE_TABLE_SQL)

        # 2026シーズンの試合マスターを取得
        matches = cur.execute(
            """
            SELECT match_id, date, home_team_id, away_team_id
            FROM matches
            WHERE season = 2026
            ORDER BY matchweek, date, match_id
            """,
        ).fetchall()

        raw_files = {p.stem: p for p in flab_dir.glob("*.json")}
        records_to_insert: List[Tuple[Any, ...]] = []
        skipped_matches: List[str] = []

        for match_id, date_str, h_id, a_id in matches:
            # ファイル名の解決 (match_id または YYYYMMDD_H_A)
            clean_date = date_str.replace("-", "").strip()
            cands = [
                match_id,
                f"{clean_date}_{h_id}_{a_id}",
            ]
            target_path: Optional[Path] = None
            for c in cands:
                if c in raw_files:
                    target_path = raw_files[c]
                    break

            if not target_path or not target_path.exists():
                skipped_matches.append(match_id)
                continue

            try:
                raw_json = json.loads(target_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to parse JSON %s: %s", target_path, e)
                skipped_matches.append(match_id)
                continue

            data_obj = raw_json.get("data") if "data" in raw_json else raw_json
            stats_list = data_obj.get("stats") or []
            cbp_dict = data_obj.get("cbp") or {}

            # ホーム側レコード
            h_rec = parse_flab_team_side(
                match_id=match_id,
                team_id=h_id,
                is_home=True,
                opponent_team_id=a_id,
                stats_list=stats_list,
                cbp_dict=cbp_dict,
            )
            records_to_insert.append(record_to_tuple(h_rec))

            # アウェイ側レコード
            a_rec = parse_flab_team_side(
                match_id=match_id,
                team_id=a_id,
                is_home=False,
                opponent_team_id=h_id,
                stats_list=stats_list,
                cbp_dict=cbp_dict,
            )
            records_to_insert.append(record_to_tuple(a_rec))

        # バッチ実行
        cur.executemany(UPSERT_SQL, records_to_insert)
        conn.commit()

        total_inserted = len(records_to_insert)
        logger.info(
            "Successfully ingested %d flab team records (matches=%d, skipped=%d)",
            total_inserted,
            len(matches) - len(skipped_matches),
            len(skipped_matches),
        )

        return {
            "status": "success",
            "total_records": total_inserted,
            "total_matches": len(matches) - len(skipped_matches),
            "skipped_matches": skipped_matches,
        }
    finally:
        conn.close()
