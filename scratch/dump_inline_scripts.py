from bs4 import BeautifulSoup

with open("scratch/page_flab_1021.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

scripts = [s for s in soup.find_all("script") if not s.get("src")]

with open("scratch/flab_inline_scripts.txt", "w", encoding="utf-8") as out:
    for i, s in enumerate(scripts):
        out.write(f"=== Inline Script {i} (length: {len(s.get_text())}) ===\n")
        out.write(s.get_text())
        out.write("\n\n" + "="*50 + "\n\n")

print("saved flab_inline_scripts.txt")
