from bs4 import BeautifulSoup

with open("page_review.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

editorial = soup.find(class_=lambda c: c and "review-editorial" in c)
with open("scratch/editorial_paragraphs.txt", "w", encoding="utf-8") as out:
    if editorial:
        # button 等のUI要素を除去
        for b in editorial.find_all("button"):
            b.decompose()
        
        paragraphs = editorial.find_all("p")
        for i, p in enumerate(paragraphs):
            text = p.get_text(strip=True)
            if text:
                out.write(f"[{i}] {text}\n\n")
