from bs4 import BeautifulSoup

with open("page_flab_report.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/flab_report_structure.txt", "w", encoding="utf-8") as out:
    out.write(f"Title: {soup.title.text if soup.title else ''}\n\n")

    # テーブルの一覧とキャプション/見出し
    for i, tbl in enumerate(soup.find_all("table")):
        caption = tbl.find("caption")
        cap_text = caption.get_text(strip=True) if caption else "No caption"
        prev_h = tbl.find_previous(["h2", "h3", "h4"])
        h_text = prev_h.get_text(strip=True) if prev_h else "No header"
        out.write(f"Table {i}: Header='{h_text}', Caption='{cap_text}', Class='{tbl.get('class')}'\n")

    # 見出し一覧
    out.write("\n=== Headings ===\n")
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        out.write(f"<{h.name}> {h.get_text(strip=True)}\n")

    # テキスト中の主要キーワード検索
    out.write("\n=== Keyword presence ===\n")
    page_text = soup.get_text()
    for kw in ["ゴール期待値", "xG", "走行距離", "スプリント", "AGI", "KAGI", "支配率", "ポゼッション", "30H", "チャンスビルディング", "CBP"]:
        out.write(f"'{kw}' in page: {kw in page_text}\n")
