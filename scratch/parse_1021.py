from bs4 import BeautifulSoup

with open("scratch/page_flab_1021.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/flab_1021_analysis.txt", "w", encoding="utf-8") as out:
    out.write(f"Title: {soup.title.text if soup.title else ''}\n\n")

    # テーブル一覧
    for i, tbl in enumerate(soup.find_all("table")):
        prev_h = tbl.find_previous(["h2", "h3", "h4"])
        h_title = prev_h.get_text(strip=True) if prev_h else "No header"
        out.write(f"=== Table {i}: Header='{h_title}' class='{tbl.get('class')}' ===\n")
        for tr in tbl.find_all("tr"):
            row = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            out.write("  " + " | ".join(row) + "\n")
        out.write("\n")

    # タイムラインセクション
    for h in soup.find_all(["h3", "h4"]):
        if "タイムライン" in h.get_text():
            out.write("=== TIMELINE SECTION ===\n")
            curr = h.find_next_sibling()
            while curr and curr.name not in ["h2", "h3"]:
                out.write(f"<{curr.name} class='{curr.get('class')}'> {curr.get_text(' | ', strip=True)[:200]}\n")
                curr = curr.find_next_sibling()
