import sqlite3
import json

conn = sqlite3.connect('data/football.db')
cursor = conn.cursor()

for t in ['team_match_stats', 'team_match_flab_stats', 'player_match_stats']:
    cursor.execute(f"PRAGMA table_info({t})")
    cols = [c[1] for c in cursor.fetchall()]
    print(f"=== {t} ===")
    print(cols)
    cursor.execute(f"SELECT * FROM {t} LIMIT 1")
    row = cursor.fetchone()
    if row:
        print("Sample:", dict(zip(cols, row)))

conn.close()
