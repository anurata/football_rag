from bs4 import BeautifulSoup

with open("page_review.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/review_detail.txt", "w", encoding="utf-8") as out:
    # 試合名
    h1 = soup.find("h1", class_="visually-hidden")
    out.write(f"Match Name: {h1.text.strip() if h1 else 'None'}\n\n")

    # 戦評
    editorial = soup.find(class_=lambda c: c and "review-editorial" in c)
    if editorial:
        out.write("=== EDITORIAL (戦評) ===\n")
        out.write(editorial.get_text("\n", strip=True))
        out.write("\n\n")
    else:
        out.write("EDITORIAL NOT FOUND\n\n")

    # セクションごとに走査
    # 選手コメント、監督コメント
    section_headers = soup.find_all(class_=lambda c: c and "m-section-header__h1--header-text" in c)
    for sh in section_headers:
        sec_title = sh.get_text(strip=True)
        out.write(f"=== SECTION: {sec_title} ===\n")
        # 次のコンテナを探す
        parent_sec = sh.find_parent("section") or sh.find_parent("div")
        # 親の中で player-comment を探す
        comments = parent_sec.find_all(class_=lambda c: c and "player-comment" in c) if parent_sec else []
        for c in comments:
            name_el = c.find(class_=lambda x: x and "player-comment__name" in x)
            name = name_el.get_text(strip=True) if name_el else "Unknown"
            
            # 所属クラブ（親要素などから取得）
            club_el = c.find_parent(class_=lambda x: x and "comment-list" in x)
            club_name = ""
            if club_el:
                club_header = club_el.find(class_=lambda x: x and "comment-club" in x)
                if club_header:
                    club_name = club_header.get_text(strip=True)
            
            content_el = c.find(class_=lambda x: x and "player-comment__content" in x)
            content = content_el.get_text("\n", strip=True) if content_el else ""
            
            out.write(f"[{club_name}] {name}:\n{content}\n---\n")
        out.write("\n")
