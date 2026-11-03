"""
API endpoint for match application context (pitch coordinates, starters, preview).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException

from agent.objective_profiler import resolve_team_name
from api.schemas import (
    MatchAppContextResponse,
    PlayerContextItem,
    RecentMatchesResponse,
    RecentMatchItem,
    TeamContextItem,
)
from pipeline.db import get_db_connection

router = APIRouter(prefix="/api", tags=["context"])

STRUCTURED_DIR = Path("data") / "structured"


KNOWN_SHORT_NAMES: Dict[str, str] = {
    "バングーナガンデ 佳史扶": "バングーナガンデ",
    "アレクサンダー ショルツ": "ショルツ",
    "ブラウンノア 賢信": "ブラウンノア",
    "レナート モーザー": "モーザー",
    "ダニ ゴメス": "ダニ ゴメス",
    "キム スンギュ": "キム スンギュ",
    "ナ サンホ": "ナ サンホ",
    "レオ ガウショ": "レオ ガウショ",
}


def resolve_short_player_name(full_name: str) -> str:
    """Return a compact display name suitable for mobile pitch card."""
    if not full_name:
        return ""
    if full_name in KNOWN_SHORT_NAMES:
        return KNOWN_SHORT_NAMES[full_name]
    parts = full_name.split()
    if len(parts) >= 2 and len(full_name) > 5:
        return parts[0]
    return full_name


# Base coordinates for 5-line / 3-back formations (18% equal vertical steps: 88 -> 70 -> 52 -> 34 -> 16)
COORDINATES_5LINE: Dict[str, Tuple[float, float]] = {
    "GK": (50.0, 88.0),
    "LSB": (14.0, 70.0),
    "LCB": (24.0, 70.0),
    "CB": (50.0, 70.0),
    "RCB": (76.0, 70.0),
    "RSB": (86.0, 70.0),
    "LWB": (12.0, 52.0),
    "RWB": (88.0, 52.0),
    "LCM": (38.0, 52.0),
    "RCM": (62.0, 52.0),
    "DMF": (50.0, 52.0),
    "CMF": (50.0, 52.0),
    "LSH": (14.0, 52.0),
    "RSH": (86.0, 52.0),
    "OMF": (50.0, 34.0),
    "CAM": (50.0, 34.0),
    "LOM": (32.0, 34.0),
    "ROM": (68.0, 34.0),
    "CF": (50.0, 16.0),
    "LCF": (35.0, 16.0),
    "RCF": (65.0, 16.0),
    "ST": (50.0, 16.0),
}

# Base coordinates for 4-line / 4-back formations (23% equal vertical steps: 89 -> 66 -> 43 -> 20)
COORDINATES_4LINE: Dict[str, Tuple[float, float]] = {
    "GK": (50.0, 89.0),
    "LSB": (14.0, 66.0),
    "LCB": (38.0, 66.0),
    "RCB": (62.0, 66.0),
    "RSB": (86.0, 66.0),
    "CB": (50.0, 66.0),
    "LWB": (12.0, 43.0),
    "RWB": (88.0, 43.0),
    "LSH": (14.0, 43.0),
    "RSH": (86.0, 43.0),
    "LCM": (38.0, 43.0),
    "RCM": (62.0, 43.0),
    "DMF": (50.0, 43.0),
    "CMF": (50.0, 43.0),
    "OMF": (50.0, 31.0),
    "CAM": (50.0, 31.0),
    "LOM": (32.0, 31.0),
    "ROM": (68.0, 31.0),
    "CF": (50.0, 20.0),
    "LCF": (35.0, 20.0),
    "RCF": (65.0, 20.0),
    "ST": (50.0, 20.0),
}

POSITION_COORDINATES = COORDINATES_5LINE


def _auto_layout_starters(starters: List[PlayerContextItem]) -> List[PlayerContextItem]:
    """Auto-layout starters across GK, DF, MF, FW lines or precise position coordinates."""
    if not starters:
        return []

    # Check if starters have detailed tactical position codes
    has_detailed_positions = any(
        (p.position or "").upper() in COORDINATES_5LINE for p in starters
    )

    if has_detailed_positions:
        result: List[PlayerContextItem] = []
        has_cb = any((p.position or "").upper() == "CB" for p in starters)
        coord_dict = COORDINATES_5LINE if has_cb else COORDINATES_4LINE

        for p in starters:
            pos_key = (p.position or "").upper()
            coords = coord_dict.get(pos_key)
            if coords:
                x, y = coords
            else:
                x, y = (p.pitch_x, p.pitch_y)
            result.append(
                PlayerContextItem(
                    player_id=p.player_id,
                    player_name=p.player_name,
                    short_name=resolve_short_player_name(p.player_name),
                    number=p.number,
                    position=p.position,
                    is_starter=p.is_starter,
                    pitch_x=x,
                    pitch_y=y,
                    photo_url=p.photo_url,
                ),
            )
        return result

    # Fallback: line-by-line distribution
    gk_list: List[PlayerContextItem] = []
    df_list: List[PlayerContextItem] = []
    mf_list: List[PlayerContextItem] = []
    fw_list: List[PlayerContextItem] = []

    for p in starters:
        pos = (p.position or "").upper()
        if "GK" in pos:
            gk_list.append(p)
        elif any(k in pos for k in ["CB", "SB", "WB", "DF"]):
            df_list.append(p)
        elif any(k in pos for k in ["FW", "CF", "WG", "ST"]):
            fw_list.append(p)
        else:
            mf_list.append(p)

    def _spread_line(
        players: List[PlayerContextItem],
        y_ratio: float,
    ) -> List[PlayerContextItem]:
        n = len(players)
        if n == 0:
            return []
        if n == 1:
            xs = [50.0]
        else:
            step = 72.0 / (n - 1)
            xs = [14.0 + (i * step) for i in range(n)]

        line_res: List[PlayerContextItem] = []
        for i, p in enumerate(players):
            stagger = 2.0 if (i % 2 == 1 and n > 3) else 0.0
            line_res.append(
                PlayerContextItem(
                    player_id=p.player_id,
                    player_name=p.player_name,
                    short_name=resolve_short_player_name(p.player_name),
                    number=p.number,
                    position=p.position,
                    is_starter=p.is_starter,
                    pitch_x=round(xs[i], 1),
                    pitch_y=round(y_ratio + stagger, 1),
                    photo_url=p.photo_url,
                ),
            )
        return line_res

    res_gk = _spread_line(gk_list, 89.0)
    res_df = _spread_line(df_list, 66.0)
    res_mf = _spread_line(mf_list, 43.0)
    res_fw = _spread_line(fw_list, 20.0)

    return res_gk + res_df + res_mf + res_fw


def _load_tactical_json(match_id: str) -> Dict[str, Any]:
    """Load pre-generated structured JSON if exists."""
    p = STRUCTURED_DIR / f"{match_id}_tactical.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _build_team_context(
    cursor: Any,
    match_id: str,
    team_id: str,
    score: Optional[int],
) -> TeamContextItem:
    """Fetch players and assemble team context with smart coordinate layout."""
    t_name = resolve_team_name(team_id)

    cursor.execute(
        """
        SELECT
            player_id,
            player_name,
            number,
            position,
            is_starter,
            avg_x,
            avg_y
        FROM player_match_stats
        WHERE match_id = ? AND team_id = ?
        ORDER BY is_starter DESC, number ASC, player_name ASC;
        """,
        (match_id, team_id),
    )
    rows = cursor.fetchall()

    starters_raw: List[PlayerContextItem] = []
    bench: List[PlayerContextItem] = []

    for r in rows:
        p_id = r["player_id"] or f"p_{team_id}_{r['number']}_{r['player_name']}"
        pos = r["position"] or "MF"
        is_st = bool(r["is_starter"])

        item = PlayerContextItem(
            player_id=p_id,
            player_name=r["player_name"],
            short_name=resolve_short_player_name(r["player_name"]),
            number=r["number"],
            position=pos,
            is_starter=is_st,
            pitch_x=float(r["avg_x"]) if r["avg_x"] is not None else 50.0,
            pitch_y=float(r["avg_y"]) if r["avg_y"] is not None else 50.0,
            photo_url=f"/assets/players/{team_id}_{r['number']}.png",
        )
        if is_st:
            starters_raw.append(item)
        else:
            bench.append(item)

    # Apply auto-layout to prevent overlapping pins
    starters = _auto_layout_starters(starters_raw)

    return TeamContextItem(
        team_id=team_id,
        team_name=t_name,
        short_name=t_name[:4] if t_name else team_id,
        score=score or 0,
        formation="4-2-3-1",
        starters=starters,
        bench=bench,
    )


@router.get("/matches/recent", response_model=RecentMatchesResponse)
def get_recent_matches(limit: int = 20) -> RecentMatchesResponse:
    """List recent matches with team names for selection menu."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                match_id,
                season,
                matchweek,
                date,
                home_team_id,
                away_team_id,
                home_score,
                away_score,
                stadium
            FROM matches
            ORDER BY date DESC, match_id DESC
            LIMIT ?;
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        items = [
            RecentMatchItem(
                match_id=r["match_id"],
                season=r["season"] or 2026,
                matchweek=r["matchweek"] or 1,
                date=str(r["date"] or ""),
                home_team_id=r["home_team_id"],
                away_team_id=r["away_team_id"],
                home_team_name=resolve_team_name(r["home_team_id"]),
                away_team_name=resolve_team_name(r["away_team_id"]),
                home_score=r["home_score"],
                away_score=r["away_score"],
                stadium=str(r["stadium"] or ""),
            )
            for r in rows
        ]
        return RecentMatchesResponse(matches=items)
    finally:
        conn.close()


@router.get("/matches/{match_id}/app_context", response_model=MatchAppContextResponse)
def get_match_app_context(match_id: str) -> MatchAppContextResponse:
    """Retrieve full bundle for mobile pitch board, formations, and tactical guide."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                match_id,
                season,
                matchweek,
                date,
                home_team_id,
                away_team_id,
                home_score,
                away_score,
                stadium,
                weather
            FROM matches
            WHERE match_id = ?;
            """,
            (match_id,),
        )
        m = cursor.fetchone()
        if not m:
            raise HTTPException(
                status_code=404,
                detail=f"Match {match_id} not found in database",
            )

        home_ctx = _build_team_context(
            cursor,
            match_id,
            m["home_team_id"],
            m["home_score"],
        )
        away_ctx = _build_team_context(
            cursor,
            match_id,
            m["away_team_id"],
            m["away_score"],
        )

        tactical_data = _load_tactical_json(match_id)
        preview_summary = tactical_data.get("match_context", {})

        # Status determination
        has_score = (m["home_score"] is not None) and (m["away_score"] is not None)
        status = "FINISHED" if has_score else "PRE"

        return MatchAppContextResponse(
            match_id=match_id,
            season=m["season"] or 2026,
            matchweek=m["matchweek"] or 1,
            date=str(m["date"] or ""),
            stadium=str(m["stadium"] or ""),
            weather=m["weather"],
            status=status,
            home_team=home_ctx,
            away_team=away_ctx,
            tactical_preview=preview_summary,
            live_stats={
                "home_score": m["home_score"] or 0,
                "away_score": m["away_score"] or 0,
            },
        )
    finally:
        conn.close()
