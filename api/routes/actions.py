"""
API endpoints for user actions (Good/Bad sync and summaries).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    ActionsSummaryResponse,
    ActionsSyncRequest,
    ActionsSyncResponse,
    ActionSummaryPerPlayer,
    UserActionItem,
)
from pipeline.db import get_db_connection

router = APIRouter(prefix="/api", tags=["actions"])


def _upsert_user_action(
    cursor: sqlite3.Cursor,
    act: UserActionItem,
) -> None:
    """Insert or update single action record."""
    cursor.execute(
        """
        INSERT INTO user_match_actions (
            id,
            match_id,
            player_id,
            team_id,
            action_type,
            match_minute,
            play_category,
            note,
            created_at,
            is_synced
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), 1)
        ON CONFLICT(id) DO UPDATE SET
            action_type = excluded.action_type,
            match_minute = excluded.match_minute,
            play_category = excluded.play_category,
            note = excluded.note,
            is_synced = 1;
        """,
        (
            act.id,
            act.match_id,
            act.player_id,
            act.team_id,
            act.action_type,
            act.match_minute,
            act.play_category,
            act.note,
            act.created_at,
        ),
    )


@router.post("/sync/actions", response_model=ActionsSyncResponse)
def sync_user_actions(payload: ActionsSyncRequest) -> ActionsSyncResponse:
    """Bulk sync user good/bad action records from mobile client."""
    if not payload.actions:
        return ActionsSyncResponse(
            success=True,
            synced_count=0,
            message="No actions provided",
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for act in payload.actions:
            _upsert_user_action(cursor, act)
        conn.commit()
        return ActionsSyncResponse(
            success=True,
            synced_count=len(payload.actions),
            message=f"Synced {len(payload.actions)} actions successfully",
        )
    finally:
        conn.close()


def _fetch_player_summaries(
    cursor: sqlite3.Cursor,
    match_id: str,
) -> List[ActionSummaryPerPlayer]:
    """Calculate aggregated good/bad count per player."""
    cursor.execute(
        """
        SELECT
            uma.player_id,
            uma.team_id,
            COALESCE(pms.player_name, uma.player_id) AS player_name,
            SUM(CASE WHEN uma.action_type = 'good' THEN 1 ELSE 0 END) AS good_cnt,
            SUM(CASE WHEN uma.action_type = 'bad' THEN 1 ELSE 0 END) AS bad_cnt,
            COUNT(*) AS total_cnt
        FROM user_match_actions uma
        LEFT JOIN player_match_stats pms
            ON pms.match_id = uma.match_id AND (pms.player_id = uma.player_id OR pms.player_name = uma.player_id)
        WHERE uma.match_id = ?
        GROUP BY uma.player_id, uma.team_id
        ORDER BY good_cnt DESC, total_cnt DESC;
        """,
        (match_id,),
    )
    rows = cursor.fetchall()

    result: List[ActionSummaryPerPlayer] = []
    for r in rows:
        g = int(r["good_cnt"] or 0)
        b = int(r["bad_cnt"] or 0)
        t = int(r["total_cnt"] or 0)
        result.append(
            ActionSummaryPerPlayer(
                player_id=r["player_id"],
                player_name=r["player_name"],
                team_id=r["team_id"],
                good_count=g,
                bad_count=b,
                total_count=t,
                net_score=g - b,
            ),
        )
    return result


def _fetch_recent_actions(
    cursor: sqlite3.Cursor,
    match_id: str,
    limit: int = 50,
) -> List[UserActionItem]:
    """Fetch latest actions for timeline display."""
    cursor.execute(
        """
        SELECT
            id,
            match_id,
            player_id,
            team_id,
            action_type,
            match_minute,
            play_category,
            note,
            created_at
        FROM user_match_actions
        WHERE match_id = ?
        ORDER BY match_minute DESC, created_at DESC
        LIMIT ?;
        """,
        (match_id, limit),
    )
    rows = cursor.fetchall()
    return [
        UserActionItem(
            id=r["id"],
            match_id=r["match_id"],
            player_id=r["player_id"],
            team_id=r["team_id"],
            action_type=r["action_type"],
            match_minute=r["match_minute"],
            play_category=r["play_category"],
            note=r["note"],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


@router.get("/matches/{match_id}/actions/summary", response_model=ActionsSummaryResponse)
def get_actions_summary(
    match_id: str,
    limit: int = Query(50, ge=1, le=200),
) -> ActionsSummaryResponse:
    """Retrieve good/bad totals, player breakdown, and recent timeline for a match."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        players = _fetch_player_summaries(cursor, match_id)
        recent = _fetch_recent_actions(cursor, match_id, limit=limit)

        total_good = sum(p.good_count for p in players)
        total_bad = sum(p.bad_count for p in players)

        return ActionsSummaryResponse(
            match_id=match_id,
            total_good=total_good,
            total_bad=total_bad,
            players=players,
            recent_actions=recent,
        )
    finally:
        conn.close()
