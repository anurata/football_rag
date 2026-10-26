from bs4 import BeautifulSoup

with open("page_flab_report.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/flab_report_details.txt", "w", encoding="utf-8") as out:
    # タイムラインセクション
    timeline = soup.find(id=lambda x: x and "timeline" in x) or soup.find(class_=lambda x: x and "timeline" in x)
    if not timeline:
        # 見出し「タイムライン」の次
        for h in soup.find_all(["h3", "h4"]):
            if "タイムライン" in h.get_text():
                out.write("=== Timeline Header Found ===\n")
                parent = h.parent
                out.write(parent.prettify()[:3000])
                break
    else:
        out.write(timeline.prettify()[:3000])

    out.write("\n\n=== ゴール期待値 / AGI / KAGI Around ===\n")
    for tag in soup.find_all(text=lambda t: t and any(k in t for k in ["ゴール期待値", "AGI", "KAGI"])):
        parent = tag.parent
        out.write(f"Tag: {parent.name}, text: {tag.strip()}\n")
        # 祖先
        container = parent.find_parent("table") or parent.find_parent("div")
        if container:
            out.write(f"Container ({container.name}, class={container.get('class')}):\n")
            out.write(container.get_text(" | ", strip=True)[:400] + "\n---\n")
