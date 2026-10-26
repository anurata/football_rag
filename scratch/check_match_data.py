import sqlite3
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH
from agent.sql_tools import TacticalSQLTools

conn = sqlite3.connect(DEFAULT_DB_PATH)
cur = conn.cursor()

match_id = "20261025_FCT_MIT"
cur.execute("SELECT count(*) FROM match_reviews WHERE match_id=?", (match_id,))
print("reviews:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM player_match_stats WHERE match_id=?", (match_id,))
print("player_stats:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM team_match_stats WHERE match_id=?", (match_id,))
print("team_stats:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM match_events WHERE match_id=?", (match_id,))
print("events:", cur.fetchone()[0])

sql = TacticalSQLTools(db_path=DEFAULT_DB_PATH)
summary = sql.get_match_summary(match_id)
print("summary keys:", summary.keys() if summary else None)
if summary:
    print("match info:", summary.get("match"))
    print("team stats:", summary.get("team_stats"))
    print("player stats count:", len(summary.get("player_stats", [])))
