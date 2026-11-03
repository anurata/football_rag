import sqlite3
import os

DB_PATH = "data/football.db"

def migrate_player_ids():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get master players: map (team_id, clean_name) -> canonical player_id
    cursor.execute("SELECT player_id, canonical_name, team_id, number FROM entity_master_players;")
    master_players = cursor.fetchall()
    master_map = {}
    for pid, cname, tid, num in master_players:
        clean = cname.replace(" ", "").replace("　", "")
        master_map[(tid, clean)] = pid

    # Find mismatched pms player_ids
    cursor.execute("SELECT DISTINCT player_id, player_name, team_id FROM player_match_stats;")
    pms_players = cursor.fetchall()

    fixed_count = 0
    for old_pid, pname, tid in pms_players:
        clean = pname.replace(" ", "").replace("　", "")
        if (tid, clean) in master_map:
            correct_pid = master_map[(tid, clean)]
            if correct_pid != old_pid:
                cursor.execute(
                    "UPDATE player_match_stats SET player_id = ? WHERE player_id = ? AND team_id = ?;",
                    (correct_pid, old_pid, tid)
                )
                fixed_count += cursor.rowcount
                print(f"Updated {old_pid} -> {correct_pid} ({pname}, {tid}): {cursor.rowcount} rows")

    conn.commit()
    conn.close()
    print(f"Migration completed. Total rows updated: {fixed_count}")

if __name__ == "__main__":
    migrate_player_ids()
