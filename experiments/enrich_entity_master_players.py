"""
experiments/enrich_entity_master_players.py

J1全20クラブの選手詳細プロフィール（897名）および利き足データを
SQLiteの entity_master_players テーブルに完全統合・同期するスクリプト。
"""

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"
ALL_PLAYERS_JSON = ROOT_DIR / "data" / "players" / "all_players.json"
DOMINANT_FOOT_JSON = ROOT_DIR / "config" / "player_dominant_foot.json"


def clean_name_key(name: str) -> str:
    """Strip spaces, dots, and middle dots for fuzzy matching."""
    if not name:
        return ""
    return re.sub(r"[\s\u3000・\.]+", "", name)


def make_player_id(team_id: str, number: Any, name: str) -> str:
    """Generate canonical player ID matching player_match_stats format."""
    num_str = str(number).strip() if number is not None else "0"
    clean_key = clean_name_key(name)
    return f"P_{team_id}_{num_str}_{clean_key[:8]}"


def safe_int_conversion(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Safely convert value to integer, stripping non-numeric text."""
    if val is None:
        return default
    text = str(val).strip()
    match = re.search(r"\d+", text)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return default
    return default


def ensure_schema(cur: sqlite3.Cursor) -> None:
    """Ensure entity_master_players has all required profile columns idempotently."""
    cur.execute("PRAGMA table_info(entity_master_players);")
    existing_cols: Set[str] = {row[1] for row in cur.fetchall()}

    columns_to_add: List[Tuple[str, str]] = [
        ("jleague_id", "TEXT"),
        ("birthdate", "TEXT"),
        ("height_cm", "INTEGER"),
        ("weight_kg", "INTEGER"),
        ("dominant_foot", "TEXT"),
        ("photo_url", "TEXT"),
        ("profile_json", "TEXT"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            cur.execute(
                f"ALTER TABLE entity_master_players ADD COLUMN {col_name} {col_type};",
            )

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_emp_jleague_id ON entity_master_players(jleague_id);",
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_emp_team_id ON entity_master_players(team_id);",
    )


def load_dominant_foot_map(path: Path) -> Dict[str, str]:
    """Load dominant foot mapping indexed by both raw name and clean name."""
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    players_map: Dict[str, str] = data.get("players", {})
    indexed: Dict[str, str] = {}
    for name, foot in players_map.items():
        indexed[name] = foot
        indexed[clean_name_key(name)] = foot
    return indexed


def resolve_dominant_foot(
    name: str,
    raw_foot: Optional[str],
    dominant_map: Dict[str, str],
) -> Optional[str]:
    """Resolve dominant foot prioritizing knowledge base over scraped blank."""
    clean_k = clean_name_key(name)
    if name in dominant_map:
        return dominant_map[name]
    if clean_k in dominant_map:
        return dominant_map[clean_k]

    # Check substring match (e.g. "アレクサンダー ショルツ" containing "ショルツ")
    for k_name, foot in dominant_map.items():
        clean_target = clean_name_key(k_name)
        if len(clean_target) >= 3 and (clean_target in clean_k or clean_k in clean_target):
            return foot

    if raw_foot and raw_foot.strip():
        return raw_foot.strip()
    return None


def build_player_aliases(
    name: str,
    en_name: Optional[str],
    clean_k: str,
) -> List[str]:
    """Build comprehensive alias list for entity linking."""
    aliases: List[str] = [name, clean_k]
    if " " in name:
        aliases.append(name.replace(" ", "　"))  # full-width
        aliases.append(name.replace(" ", ""))    # no space
    if "　" in name:
        aliases.append(name.replace("　", " "))  # half-width
        aliases.append(name.replace("　", ""))
    if en_name and en_name.strip():
        aliases.append(en_name.strip())
        aliases.append(en_name.strip().title())
    return list(dict.fromkeys(aliases))


def parse_player_record(
    raw: Dict[str, Any],
    dominant_map: Dict[str, str],
) -> Dict[str, Any]:
    """Parse single player JSON record into structured schema dict."""
    team_id = raw.get("team_id", "").strip().upper()
    name = raw.get("name", "").strip()
    number = safe_int_conversion(raw.get("number"), 0)
    pos = raw.get("position", "").strip()
    en_name = raw.get("name_en", "").strip() or None
    jleague_id = str(raw.get("player_id", "")).strip() or None
    clean_k = clean_name_key(name)
    player_id = make_player_id(team_id, number, name)

    foot = resolve_dominant_foot(name, raw.get("dominant_foot"), dominant_map)
    height = safe_int_conversion(raw.get("height_cm"))
    weight = safe_int_conversion(raw.get("weight_kg"))
    birthdate = raw.get("birthdate", "").strip() or None
    photo_url = raw.get("photo_url", "").strip() or raw.get("thumbnail_url", "").strip() or None

    aliases = build_player_aliases(name, en_name, clean_k)

    profile_details: Dict[str, Any] = {
        "jleague_id": jleague_id,
        "club_name": raw.get("club_name"),
        "birthplace": raw.get("birthplace"),
        "birthdate": birthdate,
        "height_cm": height,
        "weight_kg": weight,
        "dominant_foot": foot,
        "matches_total": raw.get("matches"),
        "goals_total": raw.get("goals"),
        "jleague_debut": raw.get("jleague_debut"),
        "jleague_first_goal": raw.get("jleague_first_goal"),
        "national_team_caps": raw.get("national_team_caps"),
        "strong_points": raw.get("strong_points", []),
        "season_stats": raw.get("season_stats", {}),
        "career_history": raw.get("career_history", []),
    }

    return {
        "player_id": player_id,
        "canonical_name": name,
        "team_id": team_id,
        "position": pos,
        "number": number,
        "en_name": en_name,
        "aliases_json": json.dumps(aliases, ensure_ascii=False),
        "jleague_id": jleague_id,
        "birthdate": birthdate,
        "height_cm": height,
        "weight_kg": weight,
        "dominant_foot": foot,
        "photo_url": photo_url,
        "profile_json": json.dumps(profile_details, ensure_ascii=False),
    }


def upsert_player_records(
    cur: sqlite3.Cursor,
    records: List[Dict[str, Any]],
) -> int:
    """Upsert parsed player records into entity_master_players table."""
    upsert_sql = """
    INSERT INTO entity_master_players (
        player_id, canonical_name, team_id, position, number,
        en_name, aliases_json, jleague_id, birthdate, height_cm,
        weight_kg, dominant_foot, photo_url, profile_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(player_id) DO UPDATE SET
        canonical_name = excluded.canonical_name,
        team_id = excluded.team_id,
        position = excluded.position,
        number = excluded.number,
        en_name = excluded.en_name,
        aliases_json = excluded.aliases_json,
        jleague_id = excluded.jleague_id,
        birthdate = excluded.birthdate,
        height_cm = excluded.height_cm,
        weight_kg = excluded.weight_kg,
        dominant_foot = COALESCE(excluded.dominant_foot, entity_master_players.dominant_foot),
        photo_url = excluded.photo_url,
        profile_json = excluded.profile_json;
    """

    count = 0
    for rec in records:
        cur.execute(
            upsert_sql,
            (
                rec["player_id"],
                rec["canonical_name"],
                rec["team_id"],
                rec["position"],
                rec["number"],
                rec["en_name"],
                rec["aliases_json"],
                rec["jleague_id"],
                rec["birthdate"],
                rec["height_cm"],
                rec["weight_kg"],
                rec["dominant_foot"],
                rec["photo_url"],
                rec["profile_json"],
            ),
        )
        count += 1
    return count


def link_unmatched_stats_players(cur: sqlite3.Cursor) -> int:
    """Link any player_match_stats records with entity_master_players by name and team."""
    unmatched_query = """
    SELECT DISTINCT pms.player_name, pms.team_id, pms.number
    FROM player_match_stats pms
    LEFT JOIN entity_master_players emp ON pms.player_id = emp.player_id
    WHERE emp.player_id IS NULL;
    """
    unmatched = cur.execute(unmatched_query).fetchall()
    updated = 0

    for name, team, num in unmatched:
        clean_k = clean_name_key(name)
        # Try finding in entity_master_players by team and clean name
        candidates = cur.execute(
            """
            SELECT player_id FROM entity_master_players
            WHERE team_id = ? AND (
                canonical_name = ?
                OR aliases_json LIKE ?
            )
            """,
            (team, name, f'%"{clean_k}"%'),
        ).fetchall()

        if candidates:
            target_id = candidates[0][0]
            cur.execute(
                """
                UPDATE player_match_stats
                SET player_id = ?
                WHERE team_id = ? AND player_name = ?;
                """,
                (target_id, team, name),
            )
            updated += 1

    return updated


def run_enrichment(
    db_path: Path = DB_PATH,
    all_players_path: Path = ALL_PLAYERS_JSON,
    dominant_foot_path: Path = DOMINANT_FOOT_JSON,
) -> Dict[str, Any]:
    """Execute complete player master enrichment pipeline."""
    if not all_players_path.exists():
        raise FileNotFoundError(f"Missing player file: {all_players_path}")

    with open(all_players_path, "r", encoding="utf-8") as f:
        raw_players: List[Dict[str, Any]] = json.load(f)

    dominant_map = load_dominant_foot_map(dominant_foot_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        cur.execute("BEGIN TRANSACTION;")
        ensure_schema(cur)

        parsed_records = [
            parse_player_record(raw, dominant_map) for raw in raw_players
        ]
        upserted_count = upsert_player_records(cur, parsed_records)

        relinked_count = link_unmatched_stats_players(cur)

        # Gather metrics
        cur.execute("SELECT count(*) FROM entity_master_players;")
        total_master_players = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM entity_master_players WHERE dominant_foot IS NOT NULL;",
        )
        dominant_foot_count = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM entity_master_players WHERE height_cm IS NOT NULL;",
        )
        height_count = cur.fetchone()[0]

        # Check match stats join coverage
        cur.execute("""
            SELECT count(*),
                   count(emp.player_id)
            FROM player_match_stats pms
            LEFT JOIN entity_master_players emp ON pms.player_id = emp.player_id;
        """)
        stats_total, stats_joined = cur.fetchone()

        conn.commit()

        metrics = {
            "upserted_count": upserted_count,
            "relinked_stats_count": relinked_count,
            "total_master_players": total_master_players,
            "dominant_foot_count": dominant_foot_count,
            "height_count": height_count,
            "stats_total": stats_total,
            "stats_joined": stats_joined,
            "join_rate": (stats_joined / stats_total * 100.0) if stats_total > 0 else 0.0,
        }
        return metrics

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def verify_player_master_queries(db_path: Path = DB_PATH) -> None:
    """Run verification queries joining player_match_stats with entity_master_players."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("\n【2026年 J1 最高速度 (km/h) × 身体プロファイル (Top 10)】")
    query_speed = """
    SELECT emp.canonical_name, emp.team_id, emp.position, emp.height_cm,
           emp.dominant_foot,
           json_extract(pms.raw_stats_json, '$.max_speed_kmh') AS max_spd,
           pms.distance_km, pms.match_id
    FROM player_match_stats pms
    JOIN entity_master_players emp ON pms.player_id = emp.player_id
    WHERE max_spd IS NOT NULL AND max_spd > 0
    ORDER BY max_spd DESC
    LIMIT 10;
    """
    for r in cur.execute(query_speed).fetchall():
        foot_str = r[4] or "不明"
        height_str = f"{r[3]}cm" if r[3] else "不明"
        print(f"  {r[0]:15s} ({r[1]} {r[2]} | {height_str} | 利き足:{foot_str}): 最高速度 {r[5]} km/h [走行 {r[6]}km]")

    print("\n【2026年 J1 空中戦ターゲット候補 (185cm以上 × PA進入数 Top 5)】")
    query_aerial = """
    SELECT emp.canonical_name, emp.team_id, emp.position, emp.height_cm,
           json_extract(pms.raw_stats_json, '$.spaia.pa_entries') AS pa_cnt,
           pms.match_id
    FROM player_match_stats pms
    JOIN entity_master_players emp ON pms.player_id = emp.player_id
    WHERE emp.height_cm >= 185 AND pa_cnt IS NOT NULL
    ORDER BY pa_cnt DESC
    LIMIT 5;
    """
    for r in cur.execute(query_aerial).fetchall():
        print(f"  {r[0]:15s} ({r[1]} {r[2]} {r[3]}cm): PA進入 {r[4]}回 [Match: {r[5]}]")

    conn.close()


def print_summary(metrics: Dict[str, Any]) -> None:
    """Print readable summary of the enrichment results."""
    print("=" * 70)
    print("Entity Master Players 統合完了サマリー")
    print("=" * 70)
    print(f"- 処理・登録選手数: {metrics['upserted_count']} 名")
    print(f"- マスタ総登録選手数: {metrics['total_master_players']} 名")
    print(f"- 身長登録件数: {metrics['height_count']} 名")
    print(f"- 利き足登録件数: {metrics['dominant_foot_count']} 名")
    print(
        f"- player_match_stats との結合: {metrics['stats_joined']} / {metrics['stats_total']} "
        f"({metrics['join_rate']:.1f}%)",
    )
    print("=" * 70)


if __name__ == "__main__":
    result_metrics = run_enrichment()
    print_summary(result_metrics)
    verify_player_master_queries()
