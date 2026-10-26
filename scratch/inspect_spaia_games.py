import requests

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
r = requests.get('https://spaia.jp/football/jleague/api/live_games', headers=headers)
data = r.json()

print(f"Total live_games: {len(data)}")

# 2026年の試合を検索
games_2026 = [g for g in data if str(g.get('GameDate', '')).startswith('2026')]
print(f"2026 games: {len(games_2026)}")
if games_2026:
    print("Sample 2026 game:", games_2026[0])

# FC東京 (HTeamID または VTeamID または HNameS / VNameS) を検索
fct_games = [g for g in data if '東京' in str(g.get('HNameS', '')) or '東京' in str(g.get('VNameS', ''))]
print(f"Games with '東京' in team name: {len(fct_games)}")
if fct_games:
    print("Latest 3 Tokyo games:")
    for g in fct_games[-3:]:
        print(f"  ID: {g.get('ID')}, Date: {g.get('GameDate')}, {g.get('HNameS')} vs {g.get('VNameS')}, Score: {g.get('HScore')}-{g.get('VScore')}")
