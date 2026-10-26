with open("scratch/sample_official_page.html", "r", encoding="utf-8") as f:
    html = f.read()

import re
# Look for occurrences of comment or review text
for word in ["戦評", "監督コメント", "選手コメント"]:
    idx = html.find(word)
    print(f"Word '{word}' index: {idx}")
    if idx != -1:
        snippet = html[max(0, idx - 100): min(len(html), idx + 300)]
        print(f"Snippet for '{word}':\n{snippet}\n---")
