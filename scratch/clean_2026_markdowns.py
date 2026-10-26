import os
import glob

markdown_dir = "data/markdown/2026"
removed = 0
for f in glob.glob(os.path.join(markdown_dir, "*.md")):
    # fctokyo の個別スクレイプ結果は残す
    if "_fctokyo" in f:
        continue
    os.remove(f)
    removed += 1

print(f"Cleaned up {removed} files from {markdown_dir}")
