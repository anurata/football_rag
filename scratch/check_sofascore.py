import sys
import urllib.request
import json

sys.stdout.reconfigure(encoding='utf-8')

# Sofascore で J1 League を検索
search_url = "https://api.sofascore.com/api/v1/search/all?q=J.League"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
}

try:
    req = urllib.request.Request(search_url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("Sofascore API response keys:", list(data.keys()))
        print(json.dumps(data, indent=2, ensure_ascii=False)[:500])
except Exception as e:
    print("Sofascore API Error:", e)
