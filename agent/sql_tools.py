"""
SQL quantitative analysis tools for J-League tactical analysis RAG agent.
Provides structured data aggregation queries to answer tactical questions.
"""

import re
import sqlite3
from typing import List, Optional, Dict, Any
from pipeline.db import get_db_connection, DEFAULT_DB_PATH


class TacticalSQLTools:
    """Quantitative analysis tools querying the normalized SQLite match database."""

    def __init__(
        self,
        conn: Optional[sqlite3.Connection] = None,
        db_path: Optional[str] = None,
    ):
        if conn is not None:
            self.conn = conn
            self._should_close = False
        else:
            self.conn = get_db_connection(db_path or DEFAULT_DB_PATH)
            self._should_close = True

    def close(self) -> None:
        """Close database connection if owned by this instance."""
        if self._should_close and self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute_custom_query(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a safe read-only SQL SELECT query.
        Prohibits data-modifying statements (INSERT, UPDATE, DELETE, DROP, etc.).
        """
        normalized_query = query.strip().rstrip(";")
        clean_check = re.sub(r"--.*", "", normalized_query, flags=re.MULTILINE)
        clean_check = clean_check.strip().upper()

        if not clean_check.startswith("SELECT") and not clean_check.startswith("WITH"):
            raise ValueError("Only read-only SELECT / WITH queries are allowed.")

        forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
        words = re.findall(r"\b[A-Z]+\b", clean_check)
        for f in forbidden:
            if f in words:
                raise ValueError(f"Forbidden SQL keyword detected: {f}")

        cursor = self.conn.cursor()
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_match_summary(self, match_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve comprehensive match summary including metadata, overall team stats,
        and key events (goals, cards).
        """
        match_query = """
        SELECT
            match_id, season, matchweek, date,
            home_team_id, away_team_id, home_score, away_score,
            stadium, weather, pitch_condition, attendance
        FROM matches
        WHERE match_id = ?;
        """
        cursor = self.conn.cursor()
        cursor.execute(match_query, (match_id,))
        match_row = cursor.fetchone()
        if not match_row:
            return None

        match_dict = dict(match_row)

        stats_query = """
        SELECT
            team_id, period, game_state, possession, xg, shots,
            shots_on_target, big_chances, final_third_passes,
            total_distance_km, sprints
        FROM team_match_stats
        WHERE match_id = ? AND period = 'ALL' AND game_state = 'ALL';
        """
        cursor.execute(stats_query, (match_id,))
        stats_rows = cursor.fetchall()
        stats_by_team = {r["team_id"]: dict(r) for r in stats_rows}

        events_query = """
        SELECT
            minute, period, game_state, team_id, player_name,
            event_type, zone_name, xg, situation, description_text
        FROM match_events
        WHERE match_id = ? AND event_type IN ('GOAL', 'CARD', 'SHOT')
        ORDER BY minute ASC;
        """
        cursor.execute(events_query, (match_id,))
        events = [dict(r) for r in cursor.fetchall()]

        return {
            "match": match_dict,
            "team_stats": stats_by_team,
            "events": events,
        }

    def get_team_trajectory(
        self,
        team_id: str,
        last_n: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chronological match trajectory for a team, comparing actual goals vs xG,
        possession, and physical running metrics. Answers 'Skill vs Luck' & 'Evolution'.
        """
        query = """
        SELECT
            m.match_id,
            m.matchweek,
            m.date,
            CASE WHEN m.home_team_id = ? THEN m.away_team_id ELSE m.home_team_id END AS opponent_id,
            CASE WHEN m.home_team_id = ? THEN 'HOME' ELSE 'AWAY' END AS venue,
            CASE WHEN m.home_team_id = ? THEN m.home_score ELSE m.away_score END AS team_score,
            CASE WHEN m.home_team_id = ? THEN m.away_score ELSE m.home_score END AS opponent_score,
            ts.possession,
            ts.xg AS team_xg,
            ts.shots AS team_shots,
            ts.shots_on_target,
            ts.big_chances,
            ts.final_third_passes,
            ts.total_distance_km,
            ts.sprints,
            opp_ts.xg AS opponent_xg,
            opp_ts.shots AS opponent_shots
        FROM matches m
        LEFT JOIN team_match_stats ts
            ON m.match_id = ts.match_id
            AND ts.team_id = ?
            AND ts.period = 'ALL'
            AND ts.game_state = 'ALL'
        LEFT JOIN team_match_stats opp_ts
            ON m.match_id = opp_ts.match_id
            AND opp_ts.team_id != ?
            AND opp_ts.period = 'ALL'
            AND opp_ts.game_state = 'ALL'
        WHERE (m.home_team_id = ? OR m.away_team_id = ?)
        ORDER BY m.date ASC, m.match_id ASC
        LIMIT ?;
        """
        cursor = self.conn.cursor()
        cursor.execute(
            query,
            (
                team_id,
                team_id,
                team_id,
                team_id,
                team_id,
                team_id,
                team_id,
                team_id,
                last_n,
            ),
        )
        rows = cursor.fetchall()
        trajectory = []
        for r in rows:
            row_dict = dict(r)
            team_score = row_dict.get("team_score")
            team_xg = row_dict.get("team_xg")
            opp_score = row_dict.get("opponent_score")
            opp_xg = row_dict.get("opponent_xg")

            row_dict["xg_goal_diff"] = (
                round(team_score - team_xg, 2)
                if (team_score is not None and team_xg is not None)
                else None
            )
            row_dict["opp_xg_goal_diff"] = (
                round(opp_score - opp_xg, 2)
                if (opp_score is not None and opp_xg is not None)
                else None
            )
            trajectory.append(row_dict)

        return trajectory

    def get_game_state_breakdown(
        self,
        team_id: str,
        match_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Analyze team performance under different game states (LEADING, DRAW, TRAILING).
        Identifies whether a team maintains pressure or drops lines after scoring.
        """
        query = """
        SELECT
            team_id,
            game_state,
            COUNT(DISTINCT match_id) AS match_count,
            ROUND(AVG(possession), 1) AS avg_possession,
            ROUND(AVG(xg), 2) AS avg_xg,
            ROUND(AVG(shots), 1) AS avg_shots,
            ROUND(AVG(final_third_passes), 1) AS avg_final_third_passes,
            ROUND(AVG(total_distance_km), 2) AS avg_distance_km,
            ROUND(AVG(sprints), 1) AS avg_sprints
        FROM team_match_stats
        WHERE team_id = ?
          AND period = 'ALL'
          AND game_state IN ('LEADING', 'DRAW', 'TRAILING')
        """
        params = [team_id]
        if match_id:
            query += " AND match_id = ?"
            params.append(match_id)

        query += " GROUP BY game_state ORDER BY CASE game_state WHEN 'LEADING' THEN 1 WHEN 'DRAW' THEN 2 WHEN 'TRAILING' THEN 3 ELSE 4 END;"

        cursor = self.conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]

    def get_player_impact_on_off(
        self,
        team_id: str,
        player_name: str,
    ) -> Dict[str, Any]:
        """
        Evaluate team performance with vs without a specific player (On/Off analysis).
        Uncovers unsung heroes (陰のMVP) who elevate team performance without flashy stats.
        """
        cursor = self.conn.cursor()

        matches_with_query = """
        SELECT DISTINCT match_id
        FROM player_match_stats
        WHERE team_id = ?
          AND player_name = ?
          AND (minutes_played > 0 OR is_starter = 1);
        """
        cursor.execute(matches_with_query, (team_id, player_name))
        with_match_ids = {r["match_id"] for r in cursor.fetchall()}

        all_matches_query = """
        SELECT DISTINCT match_id
        FROM team_match_stats
        WHERE team_id = ?;
        """
        cursor.execute(all_matches_query, (team_id,))
        all_match_ids = {r["match_id"] for r in cursor.fetchall()}
        without_match_ids = all_match_ids - with_match_ids

        def _calc_stats(match_ids: set) -> Dict[str, Any]:
            if not match_ids:
                return {
                    "match_count": 0,
                    "avg_points": 0.0,
                    "avg_goals_for": 0.0,
                    "avg_goals_against": 0.0,
                    "avg_xg": 0.0,
                    "avg_possession": 0.0,
                }

            placeholders = ",".join("?" for _ in match_ids)
            query = f"""
            SELECT
                m.match_id,
                CASE WHEN m.home_team_id = ? THEN m.home_score ELSE m.away_score END AS goals_for,
                CASE WHEN m.home_team_id = ? THEN m.away_score ELSE m.home_score END AS goals_against,
                ts.xg,
                ts.possession
            FROM matches m
            LEFT JOIN team_match_stats ts
                ON m.match_id = ts.match_id
                AND ts.team_id = ?
                AND ts.period = 'ALL'
                AND ts.game_state = 'ALL'
            WHERE m.match_id IN ({placeholders});
            """
            c = self.conn.cursor()
            c.execute(query, (team_id, team_id, team_id, *match_ids))
            rows = c.fetchall()

            total_matches = len(rows)
            if total_matches == 0:
                return {
                    "match_count": 0,
                    "avg_points": 0.0,
                    "avg_goals_for": 0.0,
                    "avg_goals_against": 0.0,
                    "avg_xg": 0.0,
                    "avg_possession": 0.0,
                }

            total_points = 0
            total_gf = 0
            total_ga = 0
            total_xg = 0.0
            total_poss = 0.0

            for r in rows:
                gf = r["goals_for"] or 0
                ga = r["goals_against"] or 0
                if gf > ga:
                    total_points += 3
                elif gf == ga:
                    total_points += 1

                total_gf += gf
                total_ga += ga
                total_xg += (r["xg"] or 0.0)
                total_poss += (r["possession"] or 0.0)

            return {
                "match_count": total_matches,
                "avg_points": round(total_points / total_matches, 2),
                "avg_goals_for": round(total_gf / total_matches, 2),
                "avg_goals_against": round(total_ga / total_matches, 2),
                "avg_xg": round(total_xg / total_matches, 2),
                "avg_possession": round(total_poss / total_matches, 1),
            }

        stats_on = _calc_stats(with_match_ids)
        stats_off = _calc_stats(without_match_ids)

        return {
            "player_name": player_name,
            "team_id": team_id,
            "on_field": stats_on,
            "off_field": stats_off,
            "delta_points": round(stats_on["avg_points"] - stats_off["avg_points"], 2),
            "delta_xg": round(stats_on["avg_xg"] - stats_off["avg_xg"], 2),
        }

    def get_player_pairing_stats(
        self,
        team_id: str,
        player_a: str,
        player_b: str,
    ) -> Dict[str, Any]:
        """
        Analyze chemistry between two players (相性・ペア分析).
        Compares matches where both start vs one/neither starts, and tracks positional coords.
        """
        cursor = self.conn.cursor()
        query = """
        SELECT
            p1.match_id,
            p1.player_name AS name_a,
            p1.avg_x AS avg_x_a,
            p1.avg_y AS avg_y_a,
            p2.player_name AS name_b,
            p2.avg_x AS avg_x_b,
            p2.avg_y AS avg_y_b,
            CASE WHEN m.home_team_id = ? THEN m.home_score ELSE m.away_score END AS goals_for,
            CASE WHEN m.home_team_id = ? THEN m.away_score ELSE m.home_score END AS goals_against,
            ts.xg AS team_xg
        FROM player_match_stats p1
        JOIN player_match_stats p2
            ON p1.match_id = p2.match_id
            AND p1.team_id = p2.team_id
        JOIN matches m
            ON p1.match_id = m.match_id
        LEFT JOIN team_match_stats ts
            ON p1.match_id = ts.match_id
            AND ts.team_id = ?
            AND ts.period = 'ALL'
            AND ts.game_state = 'ALL'
        WHERE p1.team_id = ?
          AND p1.player_name = ?
          AND p2.player_name = ?
          AND p1.is_starter = 1
          AND p2.is_starter = 1;
        """
        cursor.execute(
            query,
            (team_id, team_id, team_id, team_id, player_a, player_b),
        )
        rows = cursor.fetchall()

        match_count = len(rows)
        if match_count == 0:
            return {
                "pair": (player_a, player_b),
                "co_starts": 0,
                "avg_distance": None,
                "team_avg_xg": 0.0,
                "team_avg_goals": 0.0,
            }

        total_gf = 0
        total_xg = 0.0
        distances = []

        for r in rows:
            total_gf += (r["goals_for"] or 0)
            total_xg += (r["team_xg"] or 0.0)
            xa, ya = r["avg_x_a"], r["avg_y_a"]
            xb, yb = r["avg_x_b"], r["avg_y_b"]
            if xa is not None and ya is not None and xb is not None and yb is not None:
                dist = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5
                distances.append(dist)

        avg_dist = round(sum(distances) / len(distances), 1) if distances else None

        return {
            "pair": (player_a, player_b),
            "co_starts": match_count,
            "avg_distance": avg_dist,
            "team_avg_xg": round(total_xg / match_count, 2),
            "team_avg_goals": round(total_gf / match_count, 2),
        }

    def get_timeline_phases(
        self,
        match_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Breakdown match into 15-minute tactical phases (6 phases).
        Summarizes events, shots, and momentum changes per phase.
        """
        cursor = self.conn.cursor()
        query = """
        SELECT
            minute,
            period,
            game_state,
            team_id,
            player_name,
            event_type,
            zone_name,
            xg,
            situation,
            description_text
        FROM match_events
        WHERE match_id = ?
        ORDER BY minute ASC;
        """
        cursor.execute(query, (match_id,))
        events = cursor.fetchall()

        phases = [
            {"phase": "0-15m (1H開始)", "min": 0, "max": 15, "events": [], "shots": 0, "goals": 0, "xg": 0.0},
            {"phase": "16-30m (1H中盤)", "min": 16, "max": 30, "events": [], "shots": 0, "goals": 0, "xg": 0.0},
            {"phase": "31-45+m (1H終盤)", "min": 31, "max": 55, "events": [], "shots": 0, "goals": 0, "xg": 0.0},
            {"phase": "46-60m (2H開始)", "min": 46, "max": 60, "events": [], "shots": 0, "goals": 0, "xg": 0.0},
            {"phase": "61-75m (2H勝負所)", "min": 61, "max": 75, "events": [], "shots": 0, "goals": 0, "xg": 0.0},
            {"phase": "76-90+m (2H終盤)", "min": 76, "max": 130, "events": [], "shots": 0, "goals": 0, "xg": 0.0},
        ]

        for e in events:
            minute = e["minute"]
            if minute is None:
                continue

            event_dict = dict(e)
            for p in phases:
                if p["min"] <= minute <= p["max"]:
                    p["events"].append(event_dict)
                    if e["event_type"] == "SHOT":
                        p["shots"] += 1
                        p["xg"] = round(p["xg"] + (e["xg"] or 0.0), 3)
                    elif e["event_type"] == "GOAL":
                        p["goals"] += 1
                        p["shots"] += 1
                        p["xg"] = round(p["xg"] + (e["xg"] or 0.0), 3)
                    break

        return phases
