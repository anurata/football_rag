with open("scratch/sample_match_detail.html", "r", encoding="utf-8") as f:
    text = f.read()

import re
jleague_links = re.findall(r'href=[\"\'](https?://(?:www\.)?jleague\.jp/[^\"\']+)[\"\']', text)
print("jleague.jp links count:", len(jleague_links))
for link in jleague_links[:5]:
    print("  ", link)
