from bs4 import BeautifulSoup

with open("scratch/page_flab_1021.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

tab_box = soup.find(class_="tabBox")
with open("scratch/cbp_tabs_detail.txt", "w", encoding="utf-8") as out:
    if not tab_box:
        out.write("tabBox not found\n")
    else:
        # タブのヘッダー一覧
        tab_menu = soup.find(class_=lambda c: c and "tab" in c and "menu" in c.lower())
        if tab_menu:
            out.write(f"Tab menu: {tab_menu.get_text(' | ', strip=True)}\n\n")

        # 各テーブル
        tables = tab_box.find_all("table")
        out.write(f"Total tables in tabBox: {len(tables)}\n\n")
        for i, t in enumerate(tables):
            parent_div = t.find_parent("div")
            pid = parent_div.get("id") if parent_div else ""
            pcls = parent_div.get("class") if parent_div else ""
            out.write(f"=== Table {i} (id={pid}, class={pcls}) ===\n")
            for tr in t.find_all("tr"):
                row = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                out.write("  " + " | ".join(row) + "\n")
            out.write("\n")
