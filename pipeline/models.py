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


class ScheduleFatigueModel(BaseModel):
    """Schedule, rest days, and travel fatigue model."""
    previous_match_date: Optional[str] = Field(default=None)
    days_between: Optional[int] = Field(default=None)
    rest_days: Optional[int] = Field(default=None)
    rest_days_display: str = Field(default="-")
    is_congested: bool = Field(default=False)
    is_consecutive_away: bool = Field(default=False)
    travel_distance_km: int = Field(default=0)
    transit_type: str = Field(default="HOME")
    fatigue_risk_level: str = Field(default="LOW")
    summary_text: str = Field(default="")


class DisciplinaryModel(BaseModel):
    """Cumulative cards and suspension status model."""
    suspended_players: List[Dict[str, Any]] = Field(default_factory=list)
    warning_reach_players: List[Dict[str, Any]] = Field(default_factory=list)
    all_cumulative_yellows: Dict[str, int] = Field(default_factory=dict)
    summary_text: str = Field(default="")


class WeatherPitchModel(BaseModel):
    """Weather, pitch condition, and climate risk model."""
    weather_condition: str = Field(default="不明")
    temperature_c: Optional[float] = Field(default=None)
    humidity_percent: Optional[int] = Field(default=None)
    is_extreme_heat: bool = Field(default=False)
    is_rain_slippery: bool = Field(default=False)
    cooling_break_required: bool = Field(default=False)
    tactical_implications: str = Field(default="")
    summary_text: str = Field(default="")


class LoanRestrictionModel(BaseModel):
    """Loan contract playing restriction model."""
    has_loan_restriction: bool = Field(default=False)
    restricted_players: List[Dict[str, Any]] = Field(default_factory=list)
    summary_text: str = Field(default="")


class InjuryConditionModel(BaseModel):
    """Injury status and physical conditioning model."""
    active_injuries: List[Dict[str, Any]] = Field(default_factory=list)
    coach_mentions: List[str] = Field(default_factory=list)
    summary_text: str = Field(default="")


class MatchContextModel(BaseModel):
    """Comprehensive external match pre-conditions and context."""
    match_id: str
    team_id: str = Field(default="FCT")
    opponent_team_id: str = Field(default="AWAY")
    schedule_fatigue: ScheduleFatigueModel = Field(default_factory=ScheduleFatigueModel)
    disciplinary: DisciplinaryModel = Field(default_factory=DisciplinaryModel)
    weather_pitch: WeatherPitchModel = Field(default_factory=WeatherPitchModel)
    loan_restrictions: LoanRestrictionModel = Field(default_factory=LoanRestrictionModel)
    injury_condition: InjuryConditionModel = Field(default_factory=InjuryConditionModel)


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
    deep_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deterministic conversion rates, field tilt, and CBP rankings",
    )
    match_context: Optional[MatchContextModel] = Field(
        default=None,
        description="External pre-conditions (injuries, disciplinary, fatigue, loans, pitch)",
    )


class Layer1Metrics(BaseModel):
    """Pure numeric layer 1 statistics."""
    raw_keys_used: List[str] = Field(default_factory=list,)
    metrics: Dict[str, float] = Field(default_factory=dict,)
    formatted_display: Dict[str, str] = Field(default_factory=dict,)


class EventDetail(BaseModel):
    """Timeline incident details extracted from live text."""
    minute: int
    half: str
    team: str
    player_name: str
    event_category: str
    description: str


class Layer2EventCounts(BaseModel):
    """Aggregated occurrence counts and timeline events."""
    home_counts: Dict[str, int] = Field(default_factory=dict,)
    away_counts: Dict[str, int] = Field(default_factory=dict,)
    key_incidents: List[EventDetail] = Field(default_factory=list,)


class PerspectiveItem(BaseModel):
    """Single multi-angle perspective analysis card (4-Element Card)."""
    perspective_id: int = Field(ge=1, le=15,)
    title: str
    layer1_data: Layer1Metrics
    layer2_events: Layer2EventCounts
    layer3_theory_tags: List[str] = Field(default_factory=list,)
    narrative_home: str = Field(min_length=100,)
    narrative_away: str = Field(min_length=100,)


class PlayerRatingItem(BaseModel):
    """Player performance rating and tactical evaluation."""
    name: str
    uniform_number: int
    position: str
    team_side: str  # "HOME" or "AWAY"
    starting: bool
    minutes_played: int
    rating: str  # e.g. "7.0" or "-"
    is_mom: bool = False
    cbp_attack: float = 0.0
    cbp_defense: float = 0.0
    cbp_steal: float = 0.0
    review_comment: str = ""


class CoachRatingItem(BaseModel):
    """Head coach rating and tactical management review."""
    coach_name: str
    team_name: str
    rating: str
    game_plan_review: str = ""
    substitutions_review: str = ""


class MatchAnalysisOutput(BaseModel):
    """Full comprehensive match tactical analysis output schema."""
    match_id: str
    match_title: str
    overall_summary: str = Field(min_length=200,)
    tactical_highlights: List[str] = Field(default_factory=list,)
    three_phase_chronology: Dict[str, str] = Field(default_factory=dict,)
    perspectives: List[PerspectiveItem] = Field(default_factory=list,)
    reasons_win_loss: Dict[str, List[str]] = Field(default_factory=dict,)
    player_ratings: List[PlayerRatingItem] = Field(default_factory=list,)
    coach_ratings: List[CoachRatingItem] = Field(default_factory=list,)
    match_context: Optional[MatchContextModel] = None


