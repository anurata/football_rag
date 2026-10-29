"""
experiments/init_entity_master.py

entity_master_teams および entity_master_players の初期登録スクリプト
1. config/entity_master.json から26チームを entity_master_teams に投入
2. data/football.db の player_match_stats に存在する全ユニーク選手（約380名）を
   entity_master_players に初期登録（選手名、背番号、ポジション、所属チーム、エイリアス）
"""

import json
import sqlite3
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"
CONFIG_PATH = ROOT_DIR / "config" / "entity_master.json"


def init_teams(cur: sqlite3.Cursor) -> int:
    """Insert teams from config/entity_master.json into entity_master_teams."""
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}")
        return 0

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    teams = data.get("teams", [])
    sql = """
    INSERT INTO entity_master_teams (
        team_id, canonical_name, short_name, en_name, jleague_name,
        football_lab_slug, sofascore_id, aliases_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(team_id) DO UPDATE SET
        canonical_name = excluded.canonical_name,
        short_name = excluded.short_name,
        en_name = excluded.en_name,
        jleague_name = excluded.jleague_name,
        football_lab_slug = excluded.football_lab_slug,
        sofascore_id = excluded.sofascore_id,
        aliases_json = excluded.aliases_json;
    """
    for t in teams:
        cur.execute(sql, (
            t["team_id"],
            t["canonical_name"],
            t["short_name"],
            t.get("en_name"),
            t.get("jleague_name"),
            t.get("football_lab_slug"),
            t.get("sofascore_id"),
            json.dumps(t.get("aliases", []), ensure_ascii=False),
        ))
    return len(teams)


def init_players_from_match_stats(cur: sqlite3.Cursor) -> int:
    """Extract distinct players from player_match_stats and insert into entity_master_players."""
    query = """
    SELECT player_name, team_id, position, number,
           count(*) as match_count,
           max(minutes_played) as max_minutes
    FROM player_match_stats
    GROUP BY player_name, team_id
    ORDER BY team_id, number;
    """
    rows = cur.execute(query).fetchall()

    sql = """
    INSERT INTO entity_master_players (
        player_id, canonical_name, team_id, position, number, en_name, aliases_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(player_id) DO UPDATE SET
        canonical_name = excluded.canonical_name,
        team_id = excluded.team_id,
        position = excluded.position,
        number = excluded.number,
        aliases_json = excluded.aliases_json;
    """

    inserted = 0
    for r in rows:
        pname, team_id, pos, num, mcnt, max_min = r
        clean_key = re.sub(r"[\s\u3000・\.]+", "", pname)
        player_id = f"P_{team_id}_{num}_{clean_key[:8]}"

        aliases = [
            pname,
            clean_key,
            pname.replace(" ", "　"),  # 全角スペース
            pname.replace(" ", ""),    # スペースなし
        ]
        unique_aliases = list(dict.fromkeys(aliases))

        cur.execute(sql, (
            player_id,
            pname,
            team_id,
            pos,
            num,
            None,  # en_name will be enriched in collection phase
            json.dumps(unique_aliases, ensure_ascii=False),
        ))
        inserted += 1

    return inserted


def main() -> None:
    print("=" * 60)
    print("Entity Master (チーム・選手) 初期登録実行")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        cur.execute("BEGIN TRANSACTION;")
        t_cnt = init_teams(cur)
        print(f"entity_master_teams 登録件数: {t_cnt} チーム")

        p_cnt = init_players_from_match_stats(cur)
        print(f"entity_master_players 初期登録件数: {p_cnt} 選手")

        conn.commit()
        print("コミット完了。")

        print("\n【登録サンプル（先頭5名）】")
        cur.execute("SELECT player_id, canonical_name, team_id, position, number FROM entity_master_players LIMIT 5;")
        for r in cur.fetchall():
            print(f"  [{r[0]}] {r[1]} ({r[2]}) {r[3]} #{r[4]}")

    except Exception as e:
        conn.rollback()
        print(f"エラー発生のためロールバック: {e}")
        raise e
    finally:
        conn.close()


if __name__ == "__main__":
    main()
