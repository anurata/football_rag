# -*- coding: utf-8 -*-
"""
pipeline/external_links.py

Deterministic external links generator for J-League matches:
1. YouTube Official Highlights (Search / Direct URL)
2. Club Official Match Review / Report pages (Home & Away)
3. Yahoo! Sports Navi Soccer (Yahoo! J-League)
4. Football LAB Match / Club CBP Analytics
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, Optional

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

# Football LAB club slugs
FOOTBALL_LAB_SLUGS: Dict[str, str] = {
    "FCT": "toky",
    "OKA": "okay",
    "REY": "reys",
    "KAS": "kasm",
    "VER": "t-ve",
    "KAW": "kawa",
    "JEF": "chib",
    "CER": "c-os",
    "VOB": "kobe",
    "NAG": "ngya",
    "GAM": "g-os",
    "URA": "uraw",
    "SAN": "kyot",
    "FUK": "fuku",
    "MIT": "mito",
    "ZEL": "m-ze",
    "PUL": "spul",
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


def get_yahoo_soccer_url(match: Optional[Dict[str, Any]] = None) -> str:
    """Get Yahoo! Sports Navi J-League page URL."""
    return "https://soccer.yahoo.co.jp/jleague/category/j1"


def get_football_lab_url(team_id: Optional[str] = None) -> str:
    """Get Football LAB analytics page URL for a club or general J1."""
    if team_id and team_id in FOOTBALL_LAB_SLUGS:
        slug = FOOTBALL_LAB_SLUGS[team_id]
        return f"https://www.football-lab.jp/{slug}/"
    return "https://www.football-lab.jp/"


def generate_match_external_links(match: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate dictionary of all 4 major external links for a given match:
    - youtube_highlights: URL to official YouTube highlight search
    - home_official_review: Home club official match review URL
    - away_official_review: Away club official match review URL
    - yahoo_soccer: Yahoo! Sports Navi J-League URL
    - football_lab: Football LAB CBP stats URL
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
            "title": "Yahoo! 速報・日程",
            "url": get_yahoo_soccer_url(match),
            "icon": "📰",
            "badge": "スポーツナビ",
        },
        "football_lab": {
            "title": "Football LAB スタッツ",
            "url": get_football_lab_url(home_id or away_id),
            "icon": "📊",
            "badge": "CBP・詳細分析",
        },
    }

