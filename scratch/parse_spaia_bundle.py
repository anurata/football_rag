import requests
import re

url = 'https://spaia.jp/football/jleague/vue/pc/game_text.bundle.js?v=v3.0.0'
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers)
print('Status:', resp.status_code, 'Length:', len(resp.text))

matches = set(re.findall(r'["\'](/football/[^"\']+)["\']', resp.text))
print('Football endpoints found:', len(matches))
for m in sorted(matches):
    print(m)

# axiosやfetchやgetの呼び出しパターン
urls = set(re.findall(r'https?://[^"\'\s]+', resp.text))
print('Full URLs found:', len(urls))
for u in sorted(urls):
    if 'spaia' in u or 'api' in u:
        print(u)
