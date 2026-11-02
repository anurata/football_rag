# -*- coding: utf-8 -*-
"""
pipeline/external_links.py

Deterministic external links generator for J-League matches:
1. YouTube Official Highlights (Search / Direct URL)
2. J.LEAGUE Official Match Report (Direct Match URL)
3. Club Official Match Review / Report pages (Home & Away)
4. Yahoo! Sports Navi Soccer (Direct Game Summary URL)
5. Football LAB Match CBP Analytics (Direct Match Report URL)
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Official match review base URLs for all 20 J1 clubs (2026)
CLUB_OFFICIAL_REVIEW_URLS: Dict[str, str] = {
    "FCT": "https://www.fctokyo.co.jp/game/",
    "OKA": "https://www.fagiano-okayama.com/match/",
    "REY": "https://www.reysol.co.jp/game/results/",
    "KAS": "https://www.antlers.co.jp/games/",
    "VER": "https://www.verdy.co.jp/match/",
    "KAW": "https://www.frontale.co.jp/game/",
    "JEF": "https://jefunited.co.jp/matches/",
    "CER": "https://www.cerezo.jp/matches/",
    "VOB": "https://www.vissel-kobe.co.jp/match/",
    "NAG": "https://nagoya-grampus.jp/game/",
    "GAM": "https://www.gamba-osaka.net/game/",
    "URA": "https://www.urawa-reds.co.jp/game/",
    "SAN": "https://www.sanga-fc.jp/game/",
    "FUK": "https://www.avispa.co.jp/game/",
    "MIT": "https://www.mito-hollyhock.net/matches/",
    "ZEL": "https://www.zelvia.co.jp/match/",
    "PUL": "https://www.s-pulse.co.jp/games/",
    "VVN": "https://www.v-varen.com/game/",
    "MAR": "https://www.f-marinos.com/match/",
    "HIR": "https://www.sanfrecce.co.jp/matches/",
}

# Football LAB club slugs (synced with scrapers/football_lab.py CLUB_SLUGS)
FOOTBALL_LAB_SLUGS: Dict[str, str] = {
    "FCT": "fctk",
    "OKA": "okay",
    "REY": "kasw",
    "KAS": "kasm",
    "VER": "tk-v",
    "KAW": "ka-f",
    "JEF": "chib",
    "CER": "c-os",
    "VOB": "kobe",
    "NAG": "nago",
    "GAM": "g-os",
    "URA": "uraw",
    "SAN": "kyot",
    "FUK": "fuku",
    "MIT": "mito",
    "ZEL": "mcd",
    "PUL": "shim",
    "VVN": "ngsk",
    "MAR": "y-fm",
    "HIR": "hiro",
}

# Japanese canonical club names for search queries
CLUB_CANONICAL_NAMES: Dict[str, str] = {
    "FCT": "FC東京",
    "OKA": "ファジアーノ岡山",
    "REY": "柏レイソル",
    "KAS": "鹿島アントラーズ",
    "VER": "東京ヴェルディ",
    "KAW": "川崎フロンターレ",
    "JEF": "ジェフユナイテッド千葉",
    "CER": "セレッソ大阪",
    "VOB": "ヴィッセル神戸",
    "NAG": "名古屋グランパス",
    "GAM": "ガンバ大阪",
    "URA": "浦和レッズ",
    "SAN": "京都サンガF.C.",
    "FUK": "アビスパ福岡",
    "MIT": "水戸ホーリーホック",
    "ZEL": "FC町田ゼルビア",
    "PUL": "清水エスパルス",
    "VVN": "V・ファーレン長崎",
    "MAR": "横浜F・マリノス",
    "HIR": "サンフレッチェ広島",
}

# Manual fallback mappings for matches not yet in game_id_map_2026.json
MANUAL_GAME_ID_MAP: Dict[str, str] = {
    "20261031_OKA_FCT": "2026103109",
    "20261101_KAS_VER": "2026110101",
    "20261101_KAW_JEF": "2026110102",
    "20261101_MAR_HIR": "2026110103",
    "20261101_MIT_ZEL": "2026110104",
    "20261101_NAG_GAM": "2026110105",
    "20261101_PUL_VVN": "2026110106",
    "20261101_SAN_FUK": "2026110107",
    "20261101_URA_REY": "2026110108",
    "20261101_CER_VOB": "2026110110",
}


@lru_cache(maxsize=1)
def _load_match_to_game_id_map() -> Dict[str, str]:
    """Load reverse mapping of match_id to Yahoo game_id from raw map file."""
    mapping: Dict[str, str] = dict(MANUAL_GAME_ID_MAP)
    raw_map_file = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "raw"
        / "yahoo"
        / "game_id_map_2026.json"
    )
    if raw_map_file.exists():
        try:
            with open(raw_map_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for gid, mid in data.items():
                        mapping[str(mid)] = str(gid)
        except Exception as e:
            logger.warning("Failed to load game_id_map_2026.json: %s", e)
    return mapping


def resolve_game_id(match: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Resolve Yahoo/J-League canonical game_id from match dict."""
    if not match:
        return None

    # 1. Direct game_id field in match dict
    if match.get("game_id"):
        return str(match["game_id"])

    # 2. Look up by match_id
    match_id = match.get("match_id", "")
    if match_id:
        rev_map = _load_match_to_game_id_map()
        if match_id in rev_map:
            return rev_map[match_id]

    return None


def get_youtube_highlight_url(match: Dict[str, Any]) -> str:
    """Generate official J-League YouTube highlight search URL."""
    season = match.get("season", 2026)
    mw = match.get("matchweek")
    mw_str = f"第{mw}節" if mw else ""
    home_id = match.get("home_team_id", "")
    away_id = match.get("away_team_id", "")
    home_name = CLUB_CANONICAL_NAMES.get(home_id, home_id)
    away_name = CLUB_CANONICAL_NAMES.get(away_id, away_id)

    query = f"{season} J1 {mw_str} {home_name} {away_name} ハイライト".strip()
    encoded = urllib.parse.quote_plus(query)
    return f"https://www.youtube.com/results?search_query={encoded}"


def get_club_official_review_url(
    team_id: str,
    match: Optional[Dict[str, Any]] = None,
) -> str:
    """Get club official website review / match report URL."""
    return CLUB_OFFICIAL_REVIEW_URLS.get(
        team_id,
        "https://www.jleague.jp/",
    )


def get_jleague_official_match_url(
    match: Optional[Dict[str, Any]] = None,
) -> str:
    """Get direct J.LEAGUE official match report URL."""
    gid = resolve_game_id(match)
    if gid and len(gid) >= 8:
        year = gid[:4]
        match_code = gid[4:]
        return f"https://www.jleague.jp/match/j1/{year}/{match_code}/"
    return "https://www.jleague.jp/"


def get_yahoo_soccer_url(match: Optional[Dict[str, Any]] = None) -> str:
    """Get direct Yahoo! Sports Navi match summary URL."""
    gid = resolve_game_id(match)
    if gid:
        return f"https://soccer.yahoo.co.jp/jleague/category/j1/game/{gid}/summary"
    return "https://soccer.yahoo.co.jp/jleague/category/j1"


def _extract_date_parts(date_val: str) -> Optional[tuple[str, str, str]]:
    """Helper to extract (YYYY, MM, DD) strings from date."""
    clean = date_val.replace("-", "").replace("/", "").strip()
    if len(clean) >= 8:
        return clean[:4], clean[4:6], clean[6:8]
    return None


def get_football_lab_url(
    team_id: Optional[str] = None,
    match: Optional[Dict[str, Any]] = None,
) -> str:
    """Get direct Football LAB match report URL or club top page."""
    tid = team_id or (match.get("home_team_id") if match else None) or ""
    slug = FOOTBALL_LAB_SLUGS.get(tid, "")

    if match and match.get("date") and slug:
        parts = _extract_date_parts(str(match["date"]))
        if parts:
            year, month, day = parts
            return f"https://www.football-lab.jp/{slug}/report/?year={year}&month={month}&date={day}"

    if slug:
        return f"https://www.football-lab.jp/{slug}/"
    return "https://www.football-lab.jp/"


def generate_match_external_links(match: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate dictionary of direct external links for a given match:
    - youtube_highlights: URL to official YouTube highlight search
    - jleague_official: Direct URL to official J.LEAGUE match page
    - home_official_review: Home club official match review URL
    - away_official_review: Away club official match review URL
    - yahoo_soccer: Direct URL to Yahoo! Sports Navi match summary
    - football_lab: Direct URL to Football LAB match report
    """
    home_id = match.get("home_team_id", "")
    away_id = match.get("away_team_id", "")
    home_name = CLUB_CANONICAL_NAMES.get(home_id, home_id)
    away_name = CLUB_CANONICAL_NAMES.get(away_id, away_id)

    return {
        "youtube_highlights": {
            "title": "YouTube 公式ハイライト",
            "url": get_youtube_highlight_url(match),
            "icon": "📺",
            "badge": "Jリーグ公式動画",
        },
        "jleague_official": {
            "title": "Jリーグ公式 戦評・詳細",
            "url": get_jleague_official_match_url(match),
            "icon": "⚽",
            "badge": "J.LEAGUE公式",
        },
        "home_official_review": {
            "title": f"{home_name} 公式レビュー",
            "team_id": home_id,
            "url": get_club_official_review_url(home_id, match),
            "icon": "🏢",
            "badge": "ホーム公式",
        },
        "away_official_review": {
            "title": f"{away_name} 公式レビュー",
            "team_id": away_id,
            "url": get_club_official_review_url(away_id, match),
            "icon": "🏢",
            "badge": "アウェイ公式",
        },
        "yahoo_soccer": {
            "title": "Yahoo! 速報・スタッツ",
            "url": get_yahoo_soccer_url(match),
            "icon": "📰",
            "badge": "スポーツナビ",
        },
        "football_lab": {
            "title": "Football LAB マッチレポート",
            "url": get_football_lab_url(home_id, match),
            "icon": "📊",
            "badge": "CBP・詳細分析",
        },
    }
