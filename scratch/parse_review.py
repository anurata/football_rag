from bs4 import BeautifulSoup

with open("page_review.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/review_structure.txt", "w", encoding="utf-8") as out:
    out.write(f"Title: {soup.title.text if soup.title else ''}\n\n")
    
    # 見出しとクラス
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        classes = " ".join(h.get("class", []))
        out.write(f"<{h.name} class='{classes}'> {h.get_text(strip=True)}\n")
        
    out.write("\n--- Sections with id or data attributes ---\n")
    for sec in soup.find_all(["section", "div"]):
        sid = sec.get("id")
        classes = " ".join(sec.get("class", []))
        if sid or "review" in classes or "comment" in classes or "report" in classes:
            out.write(f"Tag: {sec.name}, id: {sid}, class: {classes}\n")
