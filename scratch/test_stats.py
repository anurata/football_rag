from bs4 import BeautifulSoup

with open("page_match.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

comp = soup.find(class_=lambda c: c and "o-team-comparison" in c and "o-team-comparison--game-average-matchup" in c)
with open("scratch/stats_detail.txt", "w", encoding="utf-8") as out:
    if not comp:
        out.write("Comparison not found\n")
    else:
        # 構造をダンプ
        out.write(comp.prettify())
