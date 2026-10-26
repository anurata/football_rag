import sqlite3

conn = sqlite3.connect('data/football.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables in data/football.db:", tables)

for t in tables:
    c.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = c.fetchone()[0]
    print(f"  - {t}: {cnt} rows")

c.execute("SELECT match_id, review_type, speaker_name, speaker_team_id, title, substr(content_text, 1, 150) FROM match_reviews LIMIT 5")
for r in c.fetchall():
    print("Review sample:", r)

conn.close()
