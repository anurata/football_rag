import requests
import json

base_url = "https://spaia.jp"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://spaia.jp/football/jleague/j1/game/2025050301/text'
}

endpoints = [
    "/football/jleague/api/comment?game_id=2025050301",
    "/football/jleague/api/live_game_reals?game_id=2025050301",
    "/football/jleague/api/live_player_detail_stats?game_id=2025050301",
    "/football/jleague/api/live_starting_players?game_id=2025050301",
    "/football/jleague/api/live_change_players?game_id=2025050301",
]

for ep in endpoints:
    url = base_url + ep
    resp = requests.get(url, headers=headers)
    print(f"Endpoint: {ep} -> Status: {resp.status_code}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            keys = list(data.keys()) if isinstance(data, dict) else f"list len {len(data)}"
            print(f"  Data: {keys}")
            if isinstance(data, list) and len(data) > 0:
                print(f"  Sample item 0 keys: {list(data[0].keys()) if isinstance(data[0], dict) else data[0]}")
            elif isinstance(data, dict):
                sample_sub = {k: type(v).__name__ for k, v in list(data.items())[:5]}
                print(f"  Types: {sample_sub}")
        except Exception as e:
            print("  Failed to parse json:", e)
