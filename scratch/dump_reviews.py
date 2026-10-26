import sqlite3

conn = sqlite3.connect('data/football.db')
c = conn.cursor()
c.execute("SELECT match_id, review_type, speaker_name, speaker_team_id, title, content_text FROM match_reviews WHERE match_id = '20261025_FCT_MIT'")
rows = c.fetchall()

print(f"Total reviews for 20261025_FCT_MIT: {len(rows)}")
for r in rows:
    mid, rtype, speaker, team, title, content = r
    print("=" * 60)
    print(f"[{rtype}] {title} / 話者: {speaker} ({team})")
    print("-" * 60)
    print(content)
    print("\n")

conn.close()
