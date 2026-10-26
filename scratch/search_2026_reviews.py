import sqlite3

conn = sqlite3.connect('data/football.db')
c = conn.cursor()
c.execute("SELECT match_id, review_type, speaker_name, speaker_team_id, title, content_text FROM match_reviews WHERE match_id LIKE '%2026%' OR match_id LIKE '%1025%'")
rows = c.fetchall()
print('Matching 2026 reviews in DB:', len(rows))
for r in rows:
    print(r[0], r[1], r[2], r[3], r[4])
    print(r[5][:200])
    print("-" * 40)

# Check distinct seasons in matches
c.execute("SELECT DISTINCT season FROM matches")
print("Seasons in matches:", c.fetchall())

c.execute("SELECT match_id, home_team_id, away_team_id, date FROM matches WHERE match_id LIKE '%2026%' LIMIT 10")
print("2026 matches:", c.fetchall())

conn.close()
