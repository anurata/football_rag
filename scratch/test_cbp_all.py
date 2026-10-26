from bs4 import BeautifulSoup

with open("scratch/page_flab_1021.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/cbp_all_tables.txt", "w", encoding="utf-8") as out:
    for i in range(17, 27):
        tbl = soup.find_all("table")[i]
        prev_h = tbl.find_previous(["h2", "h3", "h4", "h5", "li", "span", "div"])
        # tblの親
        parent = tbl.parent
        out.write(f"=== Table {i} ===\n")
        out.write(f"Parent: {parent.name}, id={parent.get('id')}, class={parent.get('class')}\n")
        out.write(f"Previous Element: {prev_h.name if prev_h else 'None'}, text='{prev_h.get_text(strip=True)[:50] if prev_h else ''}'\n")
        for tr in tbl.find_all("tr")[:5]:
            row = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            out.write("  " + " | ".join(row) + "\n")
        out.write("\n")
