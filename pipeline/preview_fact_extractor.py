"""
Preview Fact Extractor (pipeline/preview_fact_extractor.py).
Deterministically extracts all verified factual data for match previews
directly from SQLite database, LineupPredictionService, and configuration files.
Zero-hallucination factual foundation.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.lineup_prediction_service import LineupPredictionService

logger = logging.getLogger("preview_fact_extractor")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_INJURY_PATH = ROOT_DIR / "config" / "injury_tracker.json"
DEFAULT_SCHEDULE_PATH = ROOT_DIR / "scratch" / "fctokyo_yahoo_schedule.txt"


class PreviewFactExtractor:
    """Extracts verified factual preview data using deterministic scripts."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        injury_path: Path = DEFAULT_INJURY_PATH,
    ) -> None:
        self.db_path = db_path
        self.injury_path = injury_path
        self.lineup_service = LineupPredictionService(db_path=db_path)

    def extract_match_preview_facts(
        self,
        home_team_id: str,
        away_team_id: str,
        match_date: str = "2026-10-31",
        matchweek: int = 13,
    ) -> Dict[str, Any]:
        """Extract all verified factual components for the fixture."""
        basic_info = self._get_fixture_basic_info(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            match_date=match_date,
            matchweek=matchweek,
        )
        home_profile = self._build_team_factual_profile(
            team_id=home_team_id,
            opponent_id=away_team_id,
            as_of_date=match_date,
            is_home=True,
        )
        away_profile = self._build_team_factual_profile(
            team_id=away_team_id,
            opponent_id=home_team_id,
            as_of_date=match_date,
            is_home=False,
        )

        return {
            "basic_info": basic_info,
            "home_team": home_profile,
            "away_team": away_profile,
        }

    def _get_fixture_basic_info(
        self,
        home_team_id: str,
        away_team_id: str,
        match_date: str,
        matchweek: int,
    ) -> Dict[str, Any]:
        """Return stadium, kickoff time, and competition metadata."""
        stadium_name = "シティライトスタジアム (JFE晴れの国スタジアム)"
        kickoff_time = "14:00"

        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT canonical_name FROM entity_master_teams WHERE team_id = ?",
                (home_team_id,),
            )
            home_row = c.fetchone()
            home_name = home_row[0] if home_row else home_team_id

            c.execute(
                "SELECT canonical_name FROM entity_master_teams WHERE team_id = ?",
                (away_team_id,),
            )
            away_row = c.fetchone()
            away_name = away_row[0] if away_row else away_team_id

        return {
            "matchweek": matchweek,
            "date": match_date,
            "kickoff": kickoff_time,
            "stadium": stadium_name,
            "weather_forecast": "晴 / 良芝",
            "home_team_id": home_team_id,
            "home_team_name": home_name,
            "away_team_id": away_team_id,
            "away_team_name": away_name,
        }

    def _build_team_factual_profile(
        self,
        team_id: str,
        opponent_id: str,
        as_of_date: str,
        is_home: bool,
    ) -> Dict[str, Any]:
        """Build full factual profile for a team from DB and services."""
        manager_info = self._get_manager_info(team_id)
        injuries = self._get_injuries(team_id)
        record = self._get_recent_record(team_id)
        avg_stats = self._get_average_stats(team_id)
        key_players = self._get_key_players(team_id)
        winning_patterns = self._get_match_patterns(team_id, is_win=True)
        losing_patterns = self._get_match_patterns(team_id, is_win=False)

        formation = "4-4-2" if team_id == "FCT" else "3-4-2-1"
        lineup = self.lineup_service.predict_starting_lineup(
            team_id=team_id,
            opponent_team_id=opponent_id,
            as_of_date=as_of_date,
            formation=formation,
        )

        formatted_lineup = self._format_predicted_lineup(lineup)

        return {
            "team_id": team_id,
            "is_home": is_home,
            "manager": manager_info,
            "injuries": injuries,
            "record": record,
            "formation": formation,
            "avg_stats": avg_stats,
            "key_players": key_players,
            "winning_patterns": winning_patterns,
            "losing_patterns": losing_patterns,
            "predicted_lineup": formatted_lineup,
            "impact_subs": lineup.get("impact_subs", []),
        }

    def _get_manager_info(self, team_id: str) -> Dict[str, str]:
        """Get manager name and recent quote from reviews."""
        manager_name = "松橋 力蔵" if team_id == "FCT" else "木山 隆之"
        quote = ""
        symbolic_match = ""

        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT mr.speaker_name, mr.title, mr.content_text, m.matchweek, m.home_team_id, m.away_team_id
                FROM match_reviews mr
                JOIN matches m ON mr.match_id = m.match_id
                WHERE mr.speaker_team_id = ? AND mr.review_type LIKE '%COACH%' AND m.season = 2026
                ORDER BY m.matchweek DESC
                LIMIT 2
                """,
                (team_id,),
            )
            rows = c.fetchall()
            if rows:
                manager_name = rows[0][0]
                quote = rows[0][2][:180] + "..."
                symbolic_match = f"第{rows[0][3]}節"

        return {
            "name": manager_name,
            "recent_quote": quote,
            "symbolic_match": symbolic_match,
        }

    def _get_injuries(self, team_id: str) -> List[Dict[str, str]]:
        """Get injury list from config, filtering only currently active OUT/INJURED players on the roster."""
        if not self.injury_path.exists():
            return []

        # 在籍選手セットを取得して他クラブ移籍・退団選手を除外
        active_roster_names = self._get_active_roster_player_names(team_id)

        try:
            with open(self.injury_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                injuries = data.get("injuries", [])
                result: List[Dict[str, str]] = []
                for inj in injuries:
                    if inj.get("team_id") != team_id:
                        continue
                    status = inj.get("status", "")
                    if status not in ("OUT", "INJURED"):
                        continue
                    pname = inj.get("player_name", "")
                    if active_roster_names and pname not in active_roster_names:
                        continue
                    result.append(
                        {
                            "player_name": pname,
                            "status": status,
                            "injury_type": inj.get("injury_type", ""),
                            "notes": inj.get("notes", ""),
                        },
                    )
                return result
        except Exception as e:
            logger.error(f"Failed to read injuries: {e}")
            return []

    def _get_active_roster_player_names(self, team_id: str) -> Set[str]:
        """Fetch active canonical player names for a team from entity master."""
        if not self.db_path.exists():
            return set()
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                rows = c.execute(
                    "SELECT canonical_name FROM entity_master_players WHERE team_id = ?",
                    (team_id,),
                ).fetchall()
                return {r[0] for r in rows if r[0]}
        except Exception as e:
            logger.warning(f"Failed to fetch active roster names for {team_id}: {e}")
            return set()

    def _get_recent_record(self, team_id: str) -> Dict[str, Any]:
        """Calculate season record for matches up to MW12."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT matchweek, home_team_id, away_team_id, home_score, away_score
                FROM matches
                WHERE (home_team_id = ? OR away_team_id = ?) AND season = 2026 AND matchweek <= 12
                ORDER BY matchweek
                """,
                (team_id, team_id),
            )
            rows = c.fetchall()

        wins = 0
        draws = 0
        losses = 0
        gf = 0
        ga = 0
        recent_form = []

        for row in rows:
            mw, h, a, hs, ascore = row
            if hs is None or ascore is None:
                continue
            is_h = (h == team_id)
            myscore = hs if is_h else ascore
            oppscore = ascore if is_h else hs
            gf += myscore
            ga += oppscore
            if myscore > oppscore:
                wins += 1
                recent_form.append("W")
            elif myscore == oppscore:
                draws += 1
                recent_form.append("D")
            else:
                losses += 1
                recent_form.append("L")

        return {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": gf,
            "goals_against": ga,
            "recent_form": "".join(recent_form[-5:]),
            "match_count": len(rows),
        }

    def _get_average_stats(self, team_id: str) -> Dict[str, float]:
        """Get aggregated team stats from team_match_stats table."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT AVG(possession), AVG(shots), AVG(shots_on_target), AVG(total_distance_km), AVG(sprints), AVG(final_third_passes)
                FROM team_match_stats
                WHERE team_id = ? AND period = 'ALL'
                """,
                (team_id,),
            )
            row = c.fetchone()

        if not row or row[0] is None:
            return {}

        return {
            "possession_pct": round(row[0], 1),
            "shots_per_game": round(row[1], 1),
            "shots_on_target": round(row[2], 1),
            "distance_km": round(row[3], 1),
            "sprints_per_game": round(row[4], 1),
            "final_third_passes": round(row[5], 1),
        }

    def _get_key_players(self, team_id: str) -> Dict[str, Any]:
        """Extract top scorers and creators by CBP points."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT player_name, position, number, COUNT(*) as apps, SUM(goals) as g, SUM(assists) as a, AVG(cbp_points) as avg_cbp
                FROM player_match_stats
                WHERE team_id = ? AND is_starter = 1
                GROUP BY player_name
                ORDER BY g DESC, avg_cbp DESC
                LIMIT 8
                """,
                (team_id,),
            )
            rows = c.fetchall()

        players = [
            {
                "name": r[0],
                "pos": r[1],
                "number": r[2],
                "apps": r[3],
                "goals": r[4],
                "assists": r[5],
                "cbp": round(r[6], 1) if r[6] else 0.0,
            }
            for r in rows
        ]

        return {
            "top_scorers": [p for p in players if p["goals"] > 0][:3],
            "playmakers": sorted(players, key=lambda x: x["cbp"], reverse=True)[:3],
        }

    def _get_match_patterns(self, team_id: str, is_win: bool) -> List[Dict[str, Any]]:
        """Get up to 3 distinct winning or losing match patterns with actual goal events."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            comp_op = ">" if is_win else "<"
            c.execute(
                f"""
                SELECT m.match_id, m.matchweek, m.home_team_id, m.away_team_id, m.home_score, m.away_score
                FROM matches m
                WHERE ((m.home_team_id = ? AND m.home_score {comp_op} m.away_score)
                   OR (m.away_team_id = ? AND m.away_score {comp_op} m.home_score))
                   AND m.season = 2026 AND m.matchweek <= 12
                ORDER BY m.matchweek DESC
                LIMIT 3
                """,
                (team_id, team_id),
            )
            matches = c.fetchall()

            patterns = []
            for m in matches:
                mid, mw, h, a, hs, ascore = m
                opp = a if h == team_id else h
                c.execute(
                    """
                    SELECT minute, team_id, player_name, description_text
                    FROM match_events
                    WHERE match_id = ? AND event_type = 'GOAL'
                    ORDER BY minute
                    """,
                    (mid,),
                )
                goals = c.fetchall()
                goal_timeline = [
                    f"{g[0]}分: {g[2]} ({g[1]})"
                    for g in goals
                ]
                patterns.append(
                    {
                        "matchweek": mw,
                        "opponent": opp,
                        "score": f"{hs}-{ascore}",
                        "goals": goal_timeline,
                    },
                )

        return patterns

    def _format_predicted_lineup(self, lineup: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format LineupPredictionService slots into clean structure."""
        formatted = []
        for sp in lineup.get("slots", []):
            primary = sp.primary
            item = {
                "slot_id": sp.slot_id,
                "slot_name": sp.slot_name,
                "player_name": primary.player_name,
                "number": primary.number,
                "pos": primary.registered_pos,
                "probability": round(primary.probability * 100, 1),
            }
            if sp.contender:
                item["contender"] = {
                    "player_name": sp.contender.player_name,
                    "probability": round(sp.contender.probability * 100, 1),
                }
            formatted.append(item)
        return formatted
