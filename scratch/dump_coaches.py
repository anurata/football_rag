import sqlite3

conn = sqlite3.connect('data/football.db')
c = conn.cursor()
c.execute("SELECT review_type, speaker_name, speaker_team_id, content_text FROM match_reviews WHERE match_id = '20261025_FCT_MIT' AND review_type IN ('HOME_COACH', 'AWAY_COACH', 'AWAY_PLAYER')")
for rtype, speaker, team, content in c.fetchall():
    print(f"[{rtype}] {speaker} ({team})")
    print("-" * 50)
    print(content)
    print("=" * 60)

conn.close()
