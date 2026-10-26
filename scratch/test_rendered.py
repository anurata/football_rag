from bs4 import BeautifulSoup

with open("page_flab_rendered.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/flab_rendered_structure.txt", "w", encoding="utf-8") as out:
    # タイムラインセクションの調査
    for h in soup.find_all(["h3", "h4"]):
        text = h.get_text(strip=True)
        out.write(f"\n--- Header: {text} ---\n")
        # 次の要素
        curr = h.find_next_sibling()
        count = 0
        while curr and count < 5:
            if curr.name in ["h2", "h3"]:
                break
            out.write(f"  Sibling ({curr.name}, class={curr.get('class')}):\n")
            out.write("  " + curr.get_text(" | ", strip=True)[:300] + "\n")
            curr = curr.find_next_sibling()
            count += 1
