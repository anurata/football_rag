import requests

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
r = requests.get('https://spaia.jp/football/jleague/api/live_games', headers=headers)
data = r.json()

# FC東京のID
fct_id = 123 # または 270 かどうか確認
with open('scratch/spaia_fctokyo_2026.txt', 'w', encoding='utf-8') as f:
    for g in data:
        if str(g.get('GameDate', '')).startswith('2026'):
            h = g.get('HNameS', '')
            v = g.get('VNameS', '')
            if '東京' in h or 'FC東京' in h or '東京' in v or 'FC東京' in v:
                f.write(f"ID={g.get('ID')} | Date={g.get('GameDate')} | Kind={g.get('GameKindName')} | {h}({g.get('HTeamID')}) vs {v}({g.get('VTeamID')}) | Score={g.get('HScore')}-{g.get('VScore')}\n")

print("Done")
