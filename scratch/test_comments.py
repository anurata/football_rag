from bs4 import BeautifulSoup

with open("page_review.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/comments_summary.txt", "w", encoding="utf-8") as out:
    comments = soup.find_all(class_="player-comment")
    for i, c in enumerate(comments):
        name_el = c.find(class_="player-comment__name")
        name = name_el.get_text(strip=True) if name_el else "Unknown"
        
        # どのセクション（選手コメント or 監督コメント）に属しているか？
        # cの祖先をたどる
        section_name = "Unknown"
        curr = c
        while curr:
            prev_h = curr.find_previous(["h1", "h2", "h3"])
            if prev_h and any(k in prev_h.get_text() for k in ["選手コメント", "監督コメント"]):
                section_name = prev_h.get_text(strip=True)
                break
            curr = curr.parent

        club_name = ""
        club_el = c.find_parent(class_="p-game-details-highlight__comment-list")
        if club_el:
            club_header = club_el.find(class_="p-game-details-highlight__comment-club")
            if club_header:
                club_name = club_header.get_text(strip=True)

        content_el = c.find(class_="player-comment__content")
        # 「続きを読む」などのボタンテキストを除外
        if content_el:
            for b in content_el.find_all("button"):
                b.decompose()
            text = content_el.get_text("\n", strip=True)
        else:
            text = ""

        out.write(f"=== Comment {i} ===\n")
        out.write(f"Section: {section_name}\n")
        out.write(f"Club: {club_name}\n")
        out.write(f"Name: {name}\n")
        out.write(f"Content:\n{text}\n\n")
