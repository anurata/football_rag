import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}
with open('config/entity_master.json', 'r', encoding='utf-8') as f:
    master = json.load(f)

for t in master.get('teams', []):
    slug = t.get('football_lab_slug')
    found = False
    candidates = [slug]
    if t['team_id'] == 'FCT':
        candidates = ['fctk', 'tokyo']
    for s in candidates:
        if not s:
            continue
        url = f'https://www.football-lab.jp/{s}/'
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=3) as res:
                print(f"{t['team_id']} ({t['canonical_name']}): {s} -> OK")
                found = True
                break
        except Exception as e:
            pass
    if not found:
        print(f"{t['team_id']} ({t['canonical_name']}): {slug} -> NOT FOUND")
