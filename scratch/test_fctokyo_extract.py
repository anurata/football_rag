from bs4 import BeautifulSoup

with open("page_fctokyo.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

contents = soup.find(class_="detail-article__contents")
if not contents:
    print("Contents not found")
    exit()

# 画像、スクリプト、スタイルなどをクリーンアップ
for tag in contents(["script", "style", "figure", "img", "iframe"]):
    tag.decompose()

# 見出しごとにセクションを分割して出力してみる
with open("scratch/fctokyo_extracted.txt", "w", encoding="utf-8") as out:
    for child in contents.children:
        if not child.name:
            continue
        text = child.get_text(strip=True)
        if not text:
            continue
        if child.name in ["h1", "h2", "h3"]:
            out.write(f"\n{'#' * (int(child.name[1]) + 1)} {text}\n")
        elif child.name == "p":
            out.write(f"{text}\n\n")
        else:
            out.write(f"[{child.name}] {text}\n\n")

print("saved fctokyo_extracted.txt")
