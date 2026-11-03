"""
SQLite database manager and schema initialization for football_rag.
"""

import json
import os
import sqlite3
from typing import Optional, Dict, Any, List

DEFAULT_DB_PATH = os.path.join("data", "football.db")

SCHEMA_MATCHES = """
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    season INTEGER NOT NULL,
    matchweek INTEGER,
    date TEXT,
    home_team_id TEXT NOT NULL,
    away_team_id TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    stadium TEXT,
    weather TEXT,
    pitch_condition TEXT,
    attendance INTEGER,
    source_updated_stage INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SCHEMA_TEAM_MATCH_STATS = """
CREATE TABLE IF NOT EXISTS team_match_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    period TEXT DEFAULT 'ALL',
    game_state TEXT DEFAULT 'ALL',
    possession REAL,
    xg REAL,
    shots INTEGER,
    shots_on_target INTEGER,
    big_chances INTEGER,
    final_third_passes INTEGER,
    total_distance_km REAL,
    sprints INTEGER,
    raw_stats_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, team_id, period, game_state),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
"""

SCHEMA_PLAYER_MATCH_STATS = """
CREATE TABLE IF NOT EXISTS player_match_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    player_id TEXT,
    player_name TEXT NOT NULL,
    team_id TEXT NOT NULL,
    is_starter BOOLEAN DEFAULT 1,
    minutes_played INTEGER,
    position TEXT,
    number INTEGER,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    xg REAL,
    xa REAL,
    touches INTEGER,
    duels_won INTEGER,
    distance_km REAL,
    sprints INTEGER,
    avg_x REAL,
    avg_y REAL,
    cbp_points REAL,
    raw_stats_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, player_name, team_id),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
"""

SCHEMA_MATCH_EVENTS = """
CREATE TABLE IF NOT EXISTS match_events (
    event_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    minute INTEGER,
    period TEXT DEFAULT '1H',
    game_state TEXT DEFAULT 'DRAW',
    team_id TEXT,
    player_id TEXT,
    player_name TEXT,
    event_type TEXT NOT NULL,
    coord_x REAL,
    coord_y REAL,
    zone_name TEXT,
    xg REAL,
    situation TEXT,
    description_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
"""

SCHEMA_MATCH_REVIEWS = """
CREATE TABLE IF NOT EXISTS match_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    review_type TEXT NOT NULL,
    speaker_name TEXT,
    speaker_team_id TEXT,
    title TEXT,
    content_text TEXT NOT NULL,
    raw_markdown TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
"""

SCHEMA_ENTITY_TEAMS = """
CREATE TABLE IF NOT EXISTS entity_master_teams (
    team_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    en_name TEXT,
    jleague_name TEXT,
    football_lab_slug TEXT,
    sofascore_id INTEGER,
    aliases_json TEXT
);
"""

SCHEMA_ENTITY_PLAYERS = """
CREATE TABLE IF NOT EXISTS entity_master_players (
    player_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    team_id TEXT NOT NULL,
    position TEXT,
    number INTEGER,
    en_name TEXT,
    aliases_json TEXT,
    FOREIGN KEY (team_id) REFERENCES entity_master_teams(team_id)
);
"""

SCHEMA_AI_CHAT_SESSIONS = """
CREATE TABLE IF NOT EXISTS ai_chat_sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    view_type TEXT NOT NULL,
    section_key TEXT,
    context_data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SCHEMA_AI_CHAT_MESSAGES = """
CREATE TABLE IF NOT EXISTS ai_chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES ai_chat_sessions(session_id) ON DELETE CASCADE
);
"""

SCHEMA_USER_MATCH_ACTIONS = """
CREATE TABLE IF NOT EXISTS user_match_actions (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    match_minute INTEGER NOT NULL,
    play_category TEXT,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_synced INTEGER DEFAULT 1,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
"""

SCHEMA_USER_MATCH_NOTES = """
CREATE TABLE IF NOT EXISTS user_match_notes (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    note TEXT NOT NULL,
    mom_player_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_synced INTEGER DEFAULT 1,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
"""

SCHEMA_USER_STADIUM_PHOTOS = """
CREATE TABLE IF NOT EXISTS user_stadium_photos (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    stadium_id TEXT NOT NULL,
    phase TEXT,
    file_path TEXT NOT NULL,
    caption TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_synced INTEGER DEFAULT 1,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
"""

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);",
    "CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team_id, away_team_id);",
    "CREATE INDEX IF NOT EXISTS idx_team_stats_match ON team_match_stats(match_id, team_id);",
    "CREATE INDEX IF NOT EXISTS idx_player_stats_match ON player_match_stats(match_id, team_id);",
    "CREATE INDEX IF NOT EXISTS idx_player_stats_name ON player_match_stats(player_name);",
    "CREATE INDEX IF NOT EXISTS idx_events_match_minute ON match_events(match_id, minute);",
    "CREATE INDEX IF NOT EXISTS idx_reviews_match ON match_reviews(match_id, review_type);",
    "CREATE INDEX IF NOT EXISTS idx_ai_sessions_view ON ai_chat_sessions(view_type, updated_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_ai_messages_session ON ai_chat_messages(session_id, created_at ASC);",
    "CREATE INDEX IF NOT EXISTS idx_actions_match ON user_match_actions(match_id, player_id);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_match_phase ON user_match_notes(match_id, phase);",
    "CREATE INDEX IF NOT EXISTS idx_photos_match ON user_stadium_photos(match_id);",
    "CREATE INDEX IF NOT EXISTS idx_photos_stadium ON user_stadium_photos(stadium_id);",
]


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open or create a SQLite database connection with row factory enabled."""
    target_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Initialize all schema tables and indexes in the database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    tables = [
        SCHEMA_MATCHES,
        SCHEMA_TEAM_MATCH_STATS,
        SCHEMA_PLAYER_MATCH_STATS,
        SCHEMA_MATCH_EVENTS,
        SCHEMA_MATCH_REVIEWS,
        SCHEMA_ENTITY_TEAMS,
        SCHEMA_ENTITY_PLAYERS,
        SCHEMA_AI_CHAT_SESSIONS,
        SCHEMA_AI_CHAT_MESSAGES,
        SCHEMA_USER_MATCH_ACTIONS,
        SCHEMA_USER_MATCH_NOTES,
        SCHEMA_USER_STADIUM_PHOTOS,
    ]

    for statement in tables:
        cursor.execute(statement)

    for index_stmt in INDEX_STATEMENTS:
        cursor.execute(index_stmt)

    conn.commit()
    return conn


def _seed_teams(cursor: sqlite3.Cursor, teams: List[Dict[str, Any]]) -> None:
    """Insert or update teams from entity master."""
    for team in teams:
        cursor.execute(
            """
            INSERT INTO entity_master_teams (
                team_id,
                canonical_name,
                short_name,
                en_name,
                jleague_name,
                football_lab_slug,
                sofascore_id,
                aliases_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                short_name = excluded.short_name,
                en_name = excluded.en_name,
                jleague_name = excluded.jleague_name,
                football_lab_slug = excluded.football_lab_slug,
                sofascore_id = excluded.sofascore_id,
                aliases_json = excluded.aliases_json;
            """,
            (
                team.get("team_id"),
                team.get("canonical_name"),
                team.get("short_name"),
                team.get("en_name"),
                team.get("jleague_name"),
                team.get("football_lab_slug"),
                team.get("sofascore_id"),
                json.dumps(team.get("aliases", []), ensure_ascii=False),
            ),
        )


def _seed_players(cursor: sqlite3.Cursor, players: List[Dict[str, Any]]) -> None:
    """Insert or update players from entity master."""
    for player in players:
        cursor.execute(
            """
            INSERT INTO entity_master_players (
                player_id,
                canonical_name,
                team_id,
                position,
                number,
                en_name,
                aliases_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                team_id = excluded.team_id,
                position = excluded.position,
                number = excluded.number,
                en_name = excluded.en_name,
                aliases_json = excluded.aliases_json;
            """,
            (
                player.get("player_id"),
                player.get("canonical_name"),
                player.get("team_id"),
                player.get("position"),
                player.get("number"),
                player.get("en_name"),
                json.dumps(player.get("aliases", []), ensure_ascii=False),
            ),
        )


def seed_entity_master(
    conn: sqlite3.Connection,
    config_path: Optional[str] = None,
) -> None:
    """Load entity_master.json and seed into entity_master_teams and players tables."""
    path = config_path or os.path.join("config", "entity_master.json")
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        master_data = json.load(f)

    cursor = conn.cursor()
    _seed_teams(cursor, master_data.get("teams", []))
    _seed_players(cursor, master_data.get("players", []))
    conn.commit()
