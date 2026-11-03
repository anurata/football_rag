"""
pipeline/match_data_engine.py

Data engine for Match Deep Dive view.
Provides structured queries for match events timeline, formations,
player stats with official photos from entity_master_players,
and qualitative review summaries.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.team_analytics_engine import (
    get_team_manager_avatar_html,
    get_team_manager_info,
)


def fetch_match_players_with_details(
    match_id: str,
    team_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Fetch player match stats joined with entity_master_players
    to include official photo URLs, romaji/english names, and structured CBP.
    """
    if not match_id or not team_id:
        return []

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    query = """
    SELECT
        pms.id,
        pms.player_id,
        COALESCE(emp.canonical_name, pms.player_name) AS player_name,
        COALESCE(emp.en_name, '') AS en_name,
        COALESCE(pms.number, emp.number, 0) AS number,
        COALESCE(pms.position, emp.position, 'MF') AS position,
        COALESCE(pms.is_starter, 0) AS is_starter,
        COALESCE(pms.minutes_played, 0) AS minutes_played,
        COALESCE(pms.goals, 0) AS goals,
        COALESCE(pms.assists, 0) AS assists,
        COALESCE(pms.xg, 0.0) AS xg,
        COALESCE(pms.xa, 0.0) AS xa,
        COALESCE(pms.touches, 0) AS touches,
        COALESCE(pms.duels_won, 0) AS duels_won,
        COALESCE(pms.distance_km, 0.0) AS distance_km,
        COALESCE(pms.sprints, 0) AS sprints,
        COALESCE(pms.cbp_points, 0.0) AS cbp_points,
        emp.photo_url,
        pms.raw_stats_json
    FROM player_match_stats pms
    LEFT JOIN entity_master_players emp
        ON pms.player_id = emp.player_id
        OR (pms.player_name = emp.canonical_name AND pms.team_id = emp.team_id)
    WHERE pms.match_id = ? AND pms.team_id = ?
    ORDER BY pms.is_starter DESC, pms.number ASC;
    """

    cur.execute(query, (match_id, team_id))
    rows = cur.fetchall()
    conn.close()

    players: List[Dict[str, Any]] = []
    seen_names = set()

    for r in rows:
        name = r["player_name"]
        if name in seen_names:
            continue
        seen_names.add(name)

        raw_json_str = r["raw_stats_json"]
        cbp_dict: Dict[str, float] = {}
        if raw_json_str:
            try:
                parsed = json.loads(raw_json_str)
                cbp_dict = parsed.get("cbp_breakdown", {})
            except Exception:
                cbp_dict = {}

        player_dict = {
            "player_id": r["player_id"],
            "player_name": name,
            "en_name": r["en_name"],
            "number": r["number"],
            "position": r["position"],
            "is_starter": bool(r["is_starter"]),
            "minutes": r["minutes_played"],
            "goals": r["goals"],
            "assists": r["assists"],
            "xg": round(float(r["xg"]), 2),
            "xa": round(float(r["xa"]), 2),
            "touches": r["touches"],
            "duels_won": r["duels_won"],
            "distance_km": round(float(r["distance_km"]), 2),
            "sprints": r["sprints"],
            "cbp_total": round(float(r["cbp_points"]), 2),
            "cbp_pass": round(float(cbp_dict.get("pass", 0.0)), 2),
            "cbp_cross": round(float(cbp_dict.get("cross", 0.0)), 2),
            "cbp_dribble": round(float(cbp_dict.get("dribble", 0.0)), 2),
            "cbp_shoot": round(float(cbp_dict.get("shoot", 0.0)), 2),
            "cbp_takeover": round(float(cbp_dict.get("takeover", 0.0)), 2),
            "cbp_defense": round(float(cbp_dict.get("defense", 0.0)), 2),
            "photo_url": r["photo_url"],
        }
        players.append(player_dict)

    return players


def fetch_match_timeline_events(
    match_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Fetch sequential match timeline events (goals, cards, substitutions).
    """
    if not match_id:
        return []

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    query = """
    SELECT
        minute,
        period,
        team_id,
        player_name,
        event_type,
        situation,
        description_text
    FROM match_events
    WHERE match_id = ?
    ORDER BY minute ASC, event_id ASC;
    """

    cur.execute(query, (match_id,))
    rows = cur.fetchall()
    conn.close()

    events: List[Dict[str, Any]] = []
    for r in rows:
        events.append(
            {
                "minute": r["minute"],
                "period": r["period"] or ("1H" if (r["minute"] or 0) <= 45 else "2H"),
                "team_id": r["team_id"] or "",
                "player_name": r["player_name"] or "",
                "event_type": (r["event_type"] or "EVENT").upper(),
                "situation": r["situation"] or "",
                "description": r["description_text"] or "",
            },
        )

    return events


def fetch_match_formations(
    match_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Fetch initial and in-game tactical formations for both teams.
    """
    default_res = {
        "home_initial": "4-2-3-1",
        "away_initial": "4-2-3-1",
        "home_changes": [],
        "away_changes": [],
    }
    if not match_id:
        return default_res

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    query = """
    SELECT
        home_initial_formation,
        away_initial_formation,
        home_formations_json,
        away_formations_json
    FROM match_formations
    WHERE match_id = ?;
    """

    cur.execute(query, (match_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return default_res

    home_changes: List[str] = []
    away_changes: List[str] = []

    if row["home_formations_json"]:
        try:
            home_changes = json.loads(row["home_formations_json"])
        except Exception:
            home_changes = []

    if row["away_formations_json"]:
        try:
            away_changes = json.loads(row["away_formations_json"])
        except Exception:
            away_changes = []

    return {
        "home_initial": row["home_initial_formation"] or "4-2-3-1",
        "away_initial": row["away_initial_formation"] or "4-2-3-1",
        "home_changes": home_changes,
        "away_changes": away_changes,
    }


def fetch_match_interviews_and_reviews(
    match_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieve and categorize post-match reviews, interviews, and press comments.
    """
    if not match_id:
        return {"official": [], "home_interviews": [], "away_interviews": [], "discourse": []}

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    query = """
    SELECT
        review_type,
        speaker_name,
        speaker_team_id,
        title,
        content_text
    FROM match_reviews
    WHERE match_id = ?
    ORDER BY id ASC;
    """

    cur.execute(query, (match_id,))
    rows = cur.fetchall()
    conn.close()

    res: Dict[str, List[Dict[str, Any]]] = {
        "official": [],
        "home_interviews": [],
        "away_interviews": [],
        "discourse": [],
    }

    for r in rows:
        item = {
            "type": r["review_type"] or "REPORT",
            "speaker": r["speaker_name"] or "",
            "team_id": r["speaker_team_id"] or "",
            "title": r["title"] or "",
            "content": r["content_text"] or "",
        }
        rtype = (r["review_type"] or "").upper()
        if "OFFICIAL" in rtype or "REPORT" in rtype:
            res["official"].append(item)
        elif "DISCOURSE" in rtype or "SNS" in rtype:
            res["discourse"].append(item)
        elif item["team_id"]:
            # Team-specific interview
            res["home_interviews"].append(item)
        else:
            res["home_interviews"].append(item)

    return res
