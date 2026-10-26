from bs4 import BeautifulSoup

with open("scratch/page_flab_1021.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/flab_heatmap_and_cbp.txt", "w", encoding="utf-8") as out:
    # 1. hotzone (ヒートマップ)
    hotzones = soup.find_all("table", class_=lambda c: c and "hotzone" in c)
    out.write(f"Total hotzones: {len(hotzones)}\n")
    for i, hz in enumerate(hotzones):
        # どのハーフか？直前の要素
        prev = hz.find_previous(["h3", "h4", "div", "table"])
        out.write(f"\n--- Hotzone {i} ---\n")
        # 各行とセルのスタイル/属性/テキスト
        for tr in hz.find_all("tr"):
            row = []
            for td in tr.find_all("td"):
                style = td.get("style", "")
                cls = td.get("class", [])
                text = td.get_text(strip=True)
                row.append(f"[{style or cls or 'empty'}: '{text}']")
            out.write(" ".join(row) + "\n")

    # 2. CBP選手別テーブル (攻撃、パス、クロス、ドリブル、シュート、奪取、守備、セーブ)
    # チャンスビルディングポイント配下の見出しとテーブル
    cbp_sec = None
    for h in soup.find_all(["h3"]):
        if "チャンスビルディングポイント" in h.get_text():
            cbp_sec = h
            break
            
    if cbp_sec:
        out.write("\n\n=== CBP TABLES & HEADERS ===\n")
        curr = cbp_sec.find_next_sibling()
        while curr and curr.name != "h3":
            if curr.name in ["h4", "h5", "div"]:
                out.write(f"<{curr.name} class='{curr.get('class')}'> {curr.get_text(strip=True)[:100]}\n")
            if curr.name == "table":
                out.write(f"<table class='{curr.get('class')}'>\n")
                for tr in curr.find_all("tr")[:5]:
                    row = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                    out.write("  " + " | ".join(row) + "\n")
            curr = curr.find_next_sibling()
