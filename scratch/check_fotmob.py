import sys
import urllib.request
import json

sys.stdout.reconfigure(encoding='utf-8')

# FotMob で Jリーグの試合を探す
# FotMob match details API: https://www.fotmob.com/api/matchDetails?matchId=...
search_url = "https://www.fotmob.com/api/leagues?id=268" # J1 League id in FotMob is 268 (or we can search)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

try:
    req = urllib.request.Request(search_url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("FotMob J1 League API Status: 200")
        print("Keys:", list(data.keys()))
        if "matches" in data:
            all_matches = data["matches"].get("allMatches", [])
            print("Total matches:", len(all_matches))
            if all_matches:
                sample = all_matches[0]
                print("Sample match:", sample.get("id"), sample.get("home", {}).get("name"), "vs", sample.get("away", {}).get("name"))
except Exception as e:
    print("FotMob API Error:", e)
