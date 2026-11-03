"""
Pydantic request and response schemas for Mobile API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --- Action Sync Schemas ---
class UserActionItem(BaseModel):
    id: str = Field(..., description="Unique action UUID generated locally on mobile")
    match_id: str
    player_id: str
    team_id: str
    action_type: str = Field(..., description="'good' or 'bad'")
    match_minute: int = Field(0, description="Match minute when action occurred")
    play_category: Optional[str] = Field(None, description="pass, press, dribble, shot, duel, etc.")
    note: Optional[str] = None
    created_at: Optional[str] = None


class ActionsSyncRequest(BaseModel):
    actions: List[UserActionItem]


class ActionsSyncResponse(BaseModel):
    success: bool = True
    synced_count: int
    message: str = "Actions synced successfully"


class ActionSummaryPerPlayer(BaseModel):
    player_id: str
    player_name: Optional[str] = None
    team_id: str
    good_count: int = 0
    bad_count: int = 0
    total_count: int = 0
    net_score: int = 0


class ActionsSummaryResponse(BaseModel):
    match_id: str
    total_good: int = 0
    total_bad: int = 0
    players: List[ActionSummaryPerPlayer] = []
    recent_actions: List[UserActionItem] = []


# --- Note Schemas ---
class UserNoteItem(BaseModel):
    id: Optional[str] = None
    match_id: str
    phase: str = Field(..., description="'pre_match', 'half_time', or 'post_match'")
    note: str
    mom_player_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class NotesSyncRequest(BaseModel):
    notes: List[UserNoteItem]


class NotesSyncResponse(BaseModel):
    success: bool = True
    synced_count: int
    message: str = "Notes synced successfully"


class NotesListResponse(BaseModel):
    match_id: str
    notes: List[UserNoteItem] = []


# --- Photo Schemas ---
class PhotoItem(BaseModel):
    id: str
    match_id: str
    stadium_id: str
    phase: Optional[str] = None
    file_url: str
    caption: Optional[str] = None
    created_at: str


class PhotoUploadResponse(BaseModel):
    success: bool = True
    photo: PhotoItem
    message: str = "Photo uploaded successfully"


class PhotosListResponse(BaseModel):
    items: List[PhotoItem] = []


# --- App Context (Pitch & Match Data) Schemas ---
class PlayerContextItem(BaseModel):
    player_id: str
    player_name: str
    short_name: Optional[str] = None
    number: Optional[int] = None
    position: Optional[str] = None
    is_starter: bool = True
    pitch_x: float = 50.0  # 0.0 - 100.0
    pitch_y: float = 50.0  # 0.0 - 100.0
    photo_url: Optional[str] = None


class TeamContextItem(BaseModel):
    team_id: str
    team_name: str
    short_name: str
    score: Optional[int] = 0
    formation: Optional[str] = "4-2-3-1"
    starters: List[PlayerContextItem] = []
    bench: List[PlayerContextItem] = []


class MatchAppContextResponse(BaseModel):
    match_id: str
    season: int = 2026
    matchweek: int = 1
    date: str = ""
    stadium: str = ""
    weather: Optional[str] = None
    status: str = "PRE"  # PRE, LIVE, FINISHED
    home_team: TeamContextItem
    away_team: TeamContextItem
    tactical_preview: Dict[str, Any] = {}
    live_stats: Dict[str, Any] = {}


class RecentMatchItem(BaseModel):
    match_id: str
    season: int = 2026
    matchweek: int = 1
    date: str = ""
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str
    home_score: Optional[int] = 0
    away_score: Optional[int] = 0
    stadium: str = ""


class RecentMatchesResponse(BaseModel):
    matches: List[RecentMatchItem] = []
