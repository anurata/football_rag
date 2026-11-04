"""
J-League Schedule Crawler (scrapers/schedule_crawler.py)
Crawls and generates structured metadata for J1 matches across matchweeks.
"""

import os
import re
import urllib.request
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from pipeline.normalizer import EntityNormalizer


DEFAULT_SCHEDULE_URL = "https://data.j-league.or.jp/SFMS01/search?competition_years={year}&competition_frame_ids=1"


class ScheduleCrawler:
    """Crawls official schedule and builds structured match metadata."""

    def __init__(self, normalizer: Optional[EntityNormalizer] = None):
        self.normalizer = normalizer or EntityNormalizer()

    def fetch_schedule_html(self, year: int = 2024, timeout: int = 15) -> str:
        """Fetch schedule HTML from J. League Data Site."""
        url = DEFAULT_SCHEDULE_URL.format(year=year)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read().decode("utf-8", errors="ignore")

    def parse_matchweek_number(self, section_text: str) -> Optional[int]:
        """Extract integer matchweek number from section string (e.g. '第１節第１日' -> 1)."""
        match = re.search(r"第(\d+)節", section_text)
        if match:
            return int(match.group(1))
        # Handle zenkaku numbers if any
        trans = str.maketrans("０１２３４５６７８９", "0123456789")
        converted = section_text.translate(trans)
        match_zenkaku = re.search(r"第(\d+)節", converted)
        if match_zenkaku:
            return int(match_zenkaku.group(1))
        return None

    def parse_date_and_time(self, date_raw: str, time_raw: str, year: int) -> Dict[str, str]:
        """
        Parse raw date (e.g. '24/02/23(金・祝)') and time (e.g. '14:06') into
        standard ISO date 'YYYY-MM-DD', 'MMDD', and 'HH:MM'.
        """
        m_date = re.search(r"(\d{2})/(\d{2})/(\d{2})", date_raw)
        if m_date:
            yr_suffix, month, day = m_date.groups()
            full_year = 2000 + int(yr_suffix)
            iso_date = f"{full_year:04d}-{int(month):02d}-{int(day):02d}"
            mmdd = f"{int(month):02d}{int(day):02d}"
        else:
            iso_date = f"{year}-01-01"
            mmdd = "0101"

        clean_time = time_raw.strip()
        return {
            "date": iso_date,
            "mmdd": mmdd,
            "time": clean_time,
        }

    def parse_schedule_rows(self, html_content: str, year: int = 2024) -> List[Dict[str, Any]]:
        """Parse raw HTML table rows into structured match entries."""
        soup = BeautifulSoup(html_content, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        rows = table.find_all("tr")
        parsed_entries = []

        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            link = row.find("a", href=re.compile(r"/SFMS02/"))
            if not link or len(cols) < 8:
                continue

            href = link.get("href", "")
            card_match = re.search(r"match_card_id=(\d+)", href)
            card_id = card_match.group(1) if card_match else ""

            mw = self.parse_matchweek_number(cols[2])
            date_info = self.parse_date_and_time(cols[3], cols[4], year)

            home_raw = cols[5]
            score_raw = cols[6]
            away_raw = cols[7]
            stadium = cols[8] if len(cols) > 8 else ""
            attendance = cols[9] if len(cols) > 9 else ""

            home_id = self.normalizer.normalize_team_name(home_raw) or home_raw
            away_id = self.normalizer.normalize_team_name(away_raw) or away_raw

            parsed_entries.append(
                {
                    "year": year,
                    "matchweek": mw,
                    "date": date_info["date"],
                    "mmdd": date_info["mmdd"],
                    "time": date_info["time"],
                    "home_team_raw": home_raw,
                    "home_team_id": home_id,
                    "away_team_raw": away_raw,
                    "away_team_id": away_id,
                    "score": score_raw,
                    "stadium": stadium,
                    "attendance": attendance,
                    "card_id": card_id,
                },
            )

        return parsed_entries

    def build_schedule(
        self,
        html_content: Optional[str] = None,
        year: int = 2026,
        start_mw: int = 1,
        end_mw: int = 38,
    ) -> List[Dict[str, Any]]:
        """
        Build complete schedule with unique match_id and official J-League match URLs.
        Groups matches by date, orders by kickoff time, and assigns match index within the date.
        """
        if html_content is None:
            html_content = self.fetch_schedule_html(year=year)

        all_matches = self.parse_schedule_rows(html_content, year=year)

        # Filter by matchweek range
        filtered = [
            m for m in all_matches
            if m["matchweek"] is not None and start_mw <= m["matchweek"] <= end_mw
        ]

        # Group by date to determine daily match sequence numbers (01, 02, ...)
        by_date: Dict[str, List[Dict[str, Any]]] = {}
        for m in filtered:
            by_date.setdefault(m["date"], []).append(m)

        final_matches: List[Dict[str, Any]] = []

        for date_key, matches_on_date in by_date.items():
            # Sort by kickoff time
            matches_on_date.sort(key=lambda x: x["time"])
            for idx, m in enumerate(matches_on_date, start=1):
                clean_date = m["date"].replace("-", "")
                match_id = f"{clean_date}_{m['home_team_id']}_{m['away_team_id']}"
                official_url = f"https://www.jleague.jp/match/j1/{year}/{m['mmdd']}{idx:02d}/"

                m_final = dict(m)
                m_final["match_id"] = match_id
                m_final["daily_match_index"] = idx
                m_final["official_url"] = official_url
                final_matches.append(m_final)

        # Sort by matchweek then date then time
        final_matches.sort(key=lambda x: (x["matchweek"] or 0, x["date"], x["time"]))
        return final_matches
