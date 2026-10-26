from bs4 import BeautifulSoup

with open("page_fctokyo.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/fctokyo_structure.txt", "w", encoding="utf-8") as out:
    out.write(f"Title: {soup.title.text if soup.title else ''}\n\n")

    # 見出し
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5"]):
        classes = " ".join(h.get("class", []))
        out.write(f"<{h.name} class='{classes}'> {h.get_text(strip=True)}\n")

    out.write("\n=== Main article blocks ===\n")
    # 記事本文のコンテナ
    for el in soup.find_all(class_=lambda c: c and any(k in c for k in ["article", "detail", "fanzone", "entry", "content", "post"])):
        classes = " ".join(el.get("class", []))
        if "container" not in classes and "wrapper" not in classes:
            out.write(f"[{el.name} class='{classes}'] Length: {len(el.get_text())}\n")
