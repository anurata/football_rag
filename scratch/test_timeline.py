from bs4 import BeautifulSoup

with open("page_flab_report.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/flab_timeline_section.txt", "w", encoding="utf-8") as out:
    for h in soup.find_all(["h3", "h4"]):
        if "タイムライン" in h.get_text():
            out.write(f"Header: {h.get_text(strip=True)}\n")
            # 次の兄弟要素を走査
            curr = h.next_sibling
            while curr:
                if hasattr(curr, "name") and curr.name in ["h3", "h2"]:
                    break
                if hasattr(curr, "prettify"):
                    out.write(curr.prettify())
                curr = curr.next_sibling
