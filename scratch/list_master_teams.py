import json
with open('config/entity_master.json', 'r', encoding='utf-8') as f:
    d = json.load(f)
for t in d['teams']:
    print(f"{t['team_id']}: {t['canonical_name']} ({t.get('short_name')})")
