import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scrapers.jleague_official import scrape_jleague_match

sample_match_id = "20240223_HIR_URA"
sample_url = "https://www.jleague.jp/match/j1/2024/022301/"
out_path = scrape_jleague_match(
    match_id=sample_match_id,
    base_url=sample_url,
    output_dir="scratch",
    headless=True,
)
print("Scraped file:", out_path)
