"""
Pydantic data models for J-League tactical analysis RAG pipeline.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class MatchModel(BaseModel):
    """Match metadata and overall information."""
    match_id: str = Field(description="Unique identifier for the match, e.g., 20261021_FCT_KAS")
    season: int = Field(default=2026, description="Season year")
    matchweek: Optional[int] = Field(default=None, description="Matchweek number (節)")
    date: Optional[str] = Field(default=None, description="Match date in YYYY-MM-DD format")
    home_team_id: str = Field(description="Normalized team ID of home team (e.g., FCT)")
    away_team_id: str = Field(description="Normalized team ID of away team (e.g., KAS)")
    home_score: Optional[int] = Field(default=None, description="Home team score")
    away_score: Optional[int] = Field(default=None, description="Away team score")
    stadium: Optional[str] = Field(default=None, description="Stadium name")
    weather: Optional[str] = Field(default=None, description="Weather condition")
    pitch_condition: Optional[str] = Field(default=None, description="Pitch condition")
    attendance: Optional[int] = Field(default=None, description="Number of spectators")
    source_updated_stage: int = Field(default=1, description="Update stage (1=Match Day, 2=Confirmed Tracking)")


class TeamMatchStatsModel(BaseModel):
    """Aggregated team-level match stats."""
    match_id: str
    team_id: str
    period: str = Field(default="ALL", description="ALL, 1H, or 2H")
    game_state: str = Field(default="ALL", description="ALL, DRAW, LEADING, or TRAILING")
    possession: Optional[float] = Field(default=None, description="Possession percentage")
    xg: Optional[float] = Field(default=None, description="Expected Goals (xG)")
    shots: Optional[int] = Field(default=None, description="Total shots")
    shots_on_target: Optional[int] = Field(default=None, description="Shots on target")
    big_chances: Optional[int] = Field(default=None, description="Big chances created")
    final_third_passes: Optional[int] = Field(default=None, description="Passes into final third")
    total_distance_km: Optional[float] = Field(default=None, description="Total distance run in km")
    sprints: Optional[int] = Field(default=None, description="Number of sprints")
    raw_stats_json: Optional[str] = Field(default=None, description="Raw stats dictionary serialized as JSON")


class PlayerMatchStatsModel(BaseModel):
    """Player-level match performance and stats."""
    match_id: str
    player_id: Optional[str] = Field(default=None, description="Normalized player ID")
    player_name: str
    team_id: str
    is_starter: bool = Field(default=True)
    minutes_played: Optional[int] = Field(default=None)
    position: Optional[str] = Field(default=None)
    number: Optional[int] = Field(default=None)
    goals: int = Field(default=0)
    assists: int = Field(default=0)
    xg: Optional[float] = Field(default=None)
    xa: Optional[float] = Field(default=None)
    touches: Optional[int] = Field(default=None)
    duels_won: Optional[int] = Field(default=None)
    distance_km: Optional[float] = Field(default=None)
    sprints: Optional[int] = Field(default=None)
    avg_x: Optional[float] = Field(default=None)
    avg_y: Optional[float] = Field(default=None)
    cbp_points: Optional[float] = Field(default=None, description="Football LAB Chance Building Points")
    raw_stats_json: Optional[str] = Field(default=None)


class MatchEventModel(BaseModel):
    """Match incident or timeline event."""
    event_id: str
    match_id: str
    minute: Optional[int] = Field(default=None)
    period: str = Field(default="1H", description="1H, 2H, ET, etc.")
    game_state: str = Field(default="DRAW", description="DRAW, LEADING, or TRAILING")
    team_id: Optional[str] = Field(default=None)
    player_id: Optional[str] = Field(default=None)
    player_name: Optional[str] = Field(default=None)
    event_type: str = Field(description="GOAL, SHOT, SUBSTITUTION, CARD, TEXT_LIVE")
    coord_x: Optional[float] = Field(default=None, description="Normalized 0-100 coordinate")
    coord_y: Optional[float] = Field(default=None, description="Normalized 0-100 coordinate")
    zone_name: Optional[str] = Field(default=None, description="Tactical zone name")
    xg: Optional[float] = Field(default=None)
    situation: Optional[str] = Field(default=None, description="OPEN_PLAY, SET_PIECE, COUNTER")
    description_text: str = Field(default="")


class MatchReviewModel(BaseModel):
    """Qualitative review, coach comments, and player interviews."""
    match_id: str
    review_type: str = Field(
        description="OFFICIAL_REPORT, HOME_COACH, AWAY_COACH, HOME_PLAYER, AWAY_PLAYER, CLUB_OFFICIAL",
    )
    speaker_name: Optional[str] = Field(default=None)
    speaker_team_id: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    content_text: str = Field(default="")
    raw_markdown: Optional[str] = Field(default=None)


class MatchBundleModel(BaseModel):
    """Complete collection of match data ready for database persistence."""
    match: MatchModel
    team_stats: List[TeamMatchStatsModel] = Field(default_factory=list)
    player_stats: List[PlayerMatchStatsModel] = Field(default_factory=list)
    events: List[MatchEventModel] = Field(default_factory=list)
    reviews: List[MatchReviewModel] = Field(default_factory=list)


class SerializedChunkModel(BaseModel):
    """Vector-ready chunk containing formatted tactical text and metadata."""
    chunk_id: str = Field(description="Unique identifier, e.g. {match_id}_{chunk_type}")
    match_id: str
    chunk_type: str = Field(
        description="match_summary_and_stats, tactical_timeline_and_zones, manager_interviews, player_interviews",
    )
    content: str = Field(description="Serialized markdown or narrative content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata for filtering in vector DB")


class TacticalEventItem(BaseModel):
    """Structured tactical event extracted by AI from text live commentary."""
    minute: Optional[int] = Field(default=None, description="Match minute, e.g., 32")
    period: str = Field(default="1H", description="1H, 2H, or ET")
    team_side: str = Field(default="HOME", description="HOME or AWAY")
    category: str = Field(
        default="CHANCE_CREATION",
        description="CHANCE_CREATION, PRESSING, BUILDUP, SUBSTITUTION_TACTIC, GAME_STATE_SHIFT",
    )
    actors: List[str] = Field(default_factory=list, description="Key players involved")
    zone: Optional[str] = Field(default=None, description="Tactical area, e.g., 右ハーフスペース, バイタルエリア")
    description: str = Field(default="", description="Tactical explanation of the event")


class PhaseSummaryItem(BaseModel):
    """Tactical summary of a 15-minute game phase."""
    phase: str = Field(description="0-15, 15-30, 30-45+, 45-60, 60-75, 75-90+")
    dominant_team: str = Field(default="EQUAL", description="HOME, AWAY, or EQUAL")
    momentum_summary: str = Field(default="", description="Summary of who had control and chances")
    pressing_battle: str = Field(default="", description="Pressing intensity and press-breaking dynamics")
    tactical_adjustments: str = Field(default="", description="Tactical adaptations or bench interventions")


class MatchTacticalStructure(BaseModel):
    """Complete AI-structured tactical representation of a match."""
    match_id: str = Field(description="Match identifier, e.g., 2026102505")
    home_formation: Optional[str] = Field(default=None, description="Estimated home formation, e.g., 4-4-2")
    away_formation: Optional[str] = Field(default=None, description="Estimated away formation, e.g., 4-4-2")
    tactical_highlights: List[str] = Field(
        default_factory=list,
        description="Core tactical highlights and decisive factors of the match",
    )
    phases: List[PhaseSummaryItem] = Field(default_factory=list, description="6 tactical phase summaries")
    key_tactical_events: List[TacticalEventItem] = Field(
        default_factory=list,
        description="Key tactical events extracted from live text",
    )


