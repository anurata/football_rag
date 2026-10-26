from bs4 import BeautifulSoup
import collections

with open('scratch/page_flab_1021.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

category_names = {
    "1": "攻撃",
    "2": "パス",
    "3": "クロス",
    "4": "ドリブル",
    "5": "シュート",
    "6": "奪取",
    "7": "守備",
    "8": "セーブ",
}

player_cbp = collections.defaultdict(lambda: {"team": "", "cbp": {cat: 0.0 for cat in category_names.values()}})

for cat_id, cat_name in category_names.items():
    rank_div = soup.find(id=f"rank{cat_id}")
    if not rank_div:
        continue
    tbl = rank_div.find("table")
    if not tbl:
        continue
    for tr in tbl.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
        if len(tds) < 3:
            continue
        h_name = tds[0] if len(tds) > 0 and tds[0] else ""
        pts = float(tds[2]) if len(tds) > 2 and tds[2] else 0.0
        a_name = tds[4] if len(tds) > 4 and tds[4] else ""
        
        if h_name:
            player_cbp[h_name]["team"] = "HOME"
            player_cbp[h_name]["cbp"][cat_name] = pts
        if a_name:
            player_cbp[a_name]["team"] = "AWAY"
            player_cbp[a_name]["cbp"][cat_name] = pts

with open('scratch/flab_player_cbp_reconstructed.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total players with CBP: {len(player_cbp)}\n\n")
    headers = ["選手名", "チーム", "攻撃", "パス", "クロス", "ドリブル", "シュート", "奪取", "守備", "セーブ"]
    f.write(" | ".join(headers) + "\n")
    f.write("-" * 80 + "\n")
    for name, data in sorted(player_cbp.items(), key=lambda x: (x[1]["team"], -x[1]["cbp"]["攻撃"])):
        row = [name, data["team"]] + [f"{data['cbp'][c]:.2f}" for c in ["攻撃", "パス", "クロス", "ドリブル", "シュート", "奪取", "守備", "セーブ"]]
        f.write(" | ".join(row) + "\n")

print(f"Reconstructed {len(player_cbp)} players CBP!")
