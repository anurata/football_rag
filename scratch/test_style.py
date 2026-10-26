from bs4 import BeautifulSoup

with open("scratch/flab_style.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/flab_style_structure.txt", "w", encoding="utf-8") as out:
    out.write(f"Title: {soup.title.text if soup.title else ''}\n\n")

    # テーブルや指標一覧
    for tbl in soup.find_all("table"):
        out.write(f"Table class={tbl.get('class')}:\n")
        for tr in tbl.find_all("tr"):
            row = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            out.write("  " + " | ".join(row) + "\n")
        out.write("\n")

    # 見出し
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        out.write(f"<{h.name}> {h.get_text(strip=True)}\n")
