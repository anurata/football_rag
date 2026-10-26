import re

with open('scratch/spaia_raw.html', 'r', encoding='utf-8') as f:
    html = f.read()

# bundle.jsのダウンロードと検索
import requests
js_text = requests.get('https://spaia.jp/football/jleague/vue/pc/game_text.bundle.js?v=v3.0.0').text

for pattern in ['live_player_detail_stats', 'comment', 'live_game_reals']:
    idx = 0
    print(f"=== Pattern: {pattern} ===")
    for m in re.finditer(re.escape(pattern), js_text):
        start = max(0, m.start() - 150)
        end = min(len(js_text), m.end() + 150)
        print("MATCH:", js_text[start:end])
        print("-" * 40)
