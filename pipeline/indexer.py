"""
Database indexer for upserting normalized match data into SQLite.
"""

import sqlite3
from typing import Optional, List
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)
from pipeline.db import get_db_connection, DEFAULT_DB_PATH


class MatchIndexer:
    """Manages transactional upserts of match bundles into the SQLite database."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None):
        if conn is not None:
            self.conn = conn
            self._should_close = False
        else:
            self.conn = get_db_connection(db_path or DEFAULT_DB_PATH)
            self._should_close = True

    def close(self) -> None:
        """Close connection if owned by indexer."""
        if self._should_close and self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def upsert_match(self, match: MatchModel) -> None:
        """Insert or update match metadata."""
        query = """
        INSERT INTO matches (
            match_id,
            season,
            matchweek,
            date,
            home_team_id,
            away_team_id,
            home_score,
            away_score,
            stadium,
            weather,
            pitch_condition,
            attendance,
            source_updated_stage,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(match_id) DO UPDATE SET
            season = excluded.season,
            matchweek = COALESCE(excluded.matchweek, matches.matchweek),
            date = COALESCE(excluded.date, matches.date),
            home_team_id = excluded.home_team_id,
            away_team_id = excluded.away_team_id,
            home_score = COALESCE(excluded.home_score, matches.home_score),
            away_score = COALESCE(excluded.away_score, matches.away_score),
            stadium = COALESCE(excluded.stadium, matches.stadium),
            weather = COALESCE(excluded.weather, matches.weather),
            pitch_condition = COALESCE(excluded.pitch_condition, matches.pitch_condition),
            attendance = COALESCE(excluded.attendance, matches.attendance),
            source_updated_stage = MAX(matches.source_updated_stage, excluded.source_updated_stage),
            updated_at = CURRENT_TIMESTAMP;
        """
        self.conn.execute(
            query,
            (
                match.match_id,
                match.season,
                match.matchweek,
                match.date,
                match.home_team_id,
                match.away_team_id,
                match.home_score,
                match.away_score,
                match.stadium,
                match.weather,
                match.pitch_condition,
                match.attendance,
                match.source_updated_stage,
            ),
        )

    def upsert_team_stats(self, stats_list: List[TeamMatchStatsModel]) -> None:
        """Insert or update team-level stats."""
        query = """
        INSERT INTO team_match_stats (
            match_id,
            team_id,
            period,
            game_state,
            possession,
            xg,
            shots,
            shots_on_target,
            big_chances,
            final_third_passes,
            total_distance_km,
            sprints,
            raw_stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id, team_id, period, game_state) DO UPDATE SET
            possession = COALESCE(excluded.possession, team_match_stats.possession),
            xg = COALESCE(excluded.xg, team_match_stats.xg),
            shots = COALESCE(excluded.shots, team_match_stats.shots),
            shots_on_target = COALESCE(excluded.shots_on_target, team_match_stats.shots_on_target),
            big_chances = COALESCE(excluded.big_chances, team_match_stats.big_chances),
            final_third_passes = COALESCE(excluded.final_third_passes, team_match_stats.final_third_passes),
            total_distance_km = COALESCE(excluded.total_distance_km, team_match_stats.total_distance_km),
            sprints = COALESCE(excluded.sprints, team_match_stats.sprints),
            raw_stats_json = COALESCE(excluded.raw_stats_json, team_match_stats.raw_stats_json);
        """
        for stats in stats_list:
            self.conn.execute(
                query,
                (
                    stats.match_id,
                    stats.team_id,
                    stats.period,
                    stats.game_state,
                    stats.possession,
                    stats.xg,
                    stats.shots,
                    stats.shots_on_target,
                    stats.big_chances,
                    stats.final_third_passes,
                    stats.total_distance_km,
                    stats.sprints,
                    stats.raw_stats_json,
                ),
            )

    def upsert_player_stats(self, players: List[PlayerMatchStatsModel]) -> None:
        """Insert or update player performance stats."""
        query = """
        INSERT INTO player_match_stats (
            match_id,
            player_id,
            player_name,
            team_id,
            is_starter,
            minutes_played,
            position,
            number,
            goals,
            assists,
            xg,
            xa,
            touches,
            duels_won,
            distance_km,
            sprints,
            avg_x,
            avg_y,
            cbp_points,
            raw_stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id, player_name, team_id) DO UPDATE SET
            player_id = COALESCE(excluded.player_id, player_match_stats.player_id),
            is_starter = excluded.is_starter,
            minutes_played = COALESCE(excluded.minutes_played, player_match_stats.minutes_played),
            position = COALESCE(excluded.position, player_match_stats.position),
            number = COALESCE(excluded.number, player_match_stats.number),
            goals = excluded.goals,
            assists = excluded.assists,
            xg = COALESCE(excluded.xg, player_match_stats.xg),
            xa = COALESCE(excluded.xa, player_match_stats.xa),
            touches = COALESCE(excluded.touches, player_match_stats.touches),
            duels_won = COALESCE(excluded.duels_won, player_match_stats.duels_won),
            distance_km = COALESCE(excluded.distance_km, player_match_stats.distance_km),
            sprints = COALESCE(excluded.sprints, player_match_stats.sprints),
            avg_x = COALESCE(excluded.avg_x, player_match_stats.avg_x),
            avg_y = COALESCE(excluded.avg_y, player_match_stats.avg_y),
            cbp_points = COALESCE(excluded.cbp_points, player_match_stats.cbp_points),
            raw_stats_json = COALESCE(excluded.raw_stats_json, player_match_stats.raw_stats_json);
        """
        for player in players:
            self.conn.execute(
                query,
                (
                    player.match_id,
                    player.player_id,
                    player.player_name,
                    player.team_id,
                    player.is_starter,
                    player.minutes_played,
                    player.position,
                    player.number,
                    player.goals,
                    player.assists,
                    player.xg,
                    player.xa,
                    player.touches,
                    player.duels_won,
                    player.distance_km,
                    player.sprints,
                    player.avg_x,
                    player.avg_y,
                    player.cbp_points,
                    player.raw_stats_json,
                ),
            )

    def upsert_events(self, events: List[MatchEventModel]) -> None:
        """Insert or update timeline and shot events."""
        query = """
        INSERT INTO match_events (
            event_id,
            match_id,
            minute,
            period,
            game_state,
            team_id,
            player_id,
            player_name,
            event_type,
            coord_x,
            coord_y,
            zone_name,
            xg,
            situation,
            description_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            minute = excluded.minute,
            period = excluded.period,
            game_state = excluded.game_state,
            team_id = excluded.team_id,
            player_id = excluded.player_id,
            player_name = excluded.player_name,
            event_type = excluded.event_type,
            coord_x = excluded.coord_x,
            coord_y = excluded.coord_y,
            zone_name = excluded.zone_name,
            xg = excluded.xg,
            situation = excluded.situation,
            description_text = excluded.description_text;
        """
        for ev in events:
            self.conn.execute(
                query,
                (
                    ev.event_id,
                    ev.match_id,
                    ev.minute,
                    ev.period,
                    ev.game_state,
                    ev.team_id,
                    ev.player_id,
                    ev.player_name,
                    ev.event_type,
                    ev.coord_x,
                    ev.coord_y,
                    ev.zone_name,
                    ev.xg,
                    ev.situation,
                    ev.description_text,
                ),
            )

    def upsert_reviews(self, reviews: List[MatchReviewModel]) -> None:
        """Insert qualitative reviews and coach/player interviews."""
        delete_query = """
        DELETE FROM match_reviews
        WHERE match_id = ? AND review_type = ? AND speaker_name IS ?;
        """
        insert_query = """
        INSERT INTO match_reviews (
            match_id,
            review_type,
            speaker_name,
            speaker_team_id,
            title,
            content_text,
            raw_markdown
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        for r in reviews:
            self.conn.execute(
                delete_query,
                (r.match_id, r.review_type, r.speaker_name),
            )
            self.conn.execute(
                insert_query,
                (
                    r.match_id,
                    r.review_type,
                    r.speaker_name,
                    r.speaker_team_id,
                    r.title,
                    r.content_text,
                    r.raw_markdown,
                ),
            )

    def upsert_bundle(self, bundle: MatchBundleModel) -> None:
        """Upsert entire match bundle inside an atomic transaction."""
        with self.conn:
            self.upsert_match(bundle.match)
            if bundle.team_stats:
                self.upsert_team_stats(bundle.team_stats)
            if bundle.player_stats:
                self.upsert_player_stats(bundle.player_stats)
            if bundle.events:
                self.upsert_events(bundle.events)
            if bundle.reviews:
                self.upsert_reviews(bundle.reviews)
