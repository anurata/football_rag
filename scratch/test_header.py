from bs4 import BeautifulSoup
import re

with open("page_match.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

with open("scratch/match_header_info.txt", "w", encoding="utf-8") as out:
    # タイトル / h1
    h1 = soup.find("h1")
    out.write(f"h1: {h1.text.strip() if h1 else 'None'}\n")
    
    # スコア関連
    # 通常ヘッダーにホームチーム、アウェイチーム、スコア、会場情報がある
    header_section = soup.find(class_=lambda c: c and ("match-header" in c or "game-header" in c or "game-details" in c))
    out.write(f"header_section class: {header_section.get('class') if header_section else 'None'}\n\n")

    # 全体のテキストから試合概要になりそうな部分を調査
    for el in soup.find_all(class_=lambda c: c and any(k in c for k in ["score", "team", "stadium", "date", "match-info", "weather"])):
        out.write(f"[{el.name} class='{' '.join(el.get('class', []))}'] {el.get_text(strip=True)[:100]}\n")
