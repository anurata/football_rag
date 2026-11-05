"""
pipeline/league_overview_data.py

Aggregates J-League overview data for Streamlit Dashboard:
1. League standings table & expected points (xPTS, Luck Index, xG, xGA, Form)
2. Matchweek schedule & result cards with deep-linking & external URLs
3. Team & player statistical rankings (Top 5 leaderboards)
4. Tactical positioning 4-quadrant comparative map data
"""

import math
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from agent.objective_profiler import TEAM_NAME_MAP
from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.external_links import generate_match_external_links
from pipeline.match_report_card_calculator import MatchReportCardCalculator
from pipeline.team_55_metrics_calculator import simulate_poisson_match


def get_available_seasons(
    conn: Optional[sqlite3.Connection] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> List[int]:
    """Return sorted list of available seasons from matches table."""
    close_conn = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_conn = True

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT season
            FROM matches
            ORDER BY season DESC;
            """,
        )
        rows = cur.fetchall()
        seasons = [int(r[0]) for r in rows if r[0] is not None]
        return seasons if seasons else [2026]
    finally:
        if close_conn:
            conn.close()


def get_team_metadata_map(
    conn: Optional[sqlite3.Connection] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Dict[str, str]]:
    """Return dictionary of team metadata mapping team_id to names and info."""
    close_conn = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_conn = True

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT team_id, canonical_name, short_name, en_name
            FROM entity_master_teams;
            """,
        )
        rows = cur.fetchall()
        meta: Dict[str, Dict[str, str]] = {}
        for r in rows:
            tid = str(r[0])
            cname = str(r[1]) if r[1] else TEAM_NAME_MAP.get(tid, tid)
            sname = str(r[2]) if r[2] else cname
            meta[tid] = {
                "team_id": tid,
                "name": cname,
                "short_name": sname,
                "en_name": str(r[3]) if r[3] else tid,
            }
        return meta
    finally:
        if close_conn:
            conn.close()


def _compute_match_xpts(
    home_score: Optional[int],
    away_score: Optional[int],
    home_xg: Optional[float],
    away_xg: Optional[float],
) -> Tuple[float, float]:
    """Calculate expected points (home_xpts, away_xpts) using Poisson model."""
    h_xg = home_xg if (home_xg is not None and home_xg > 0.0) else (float(home_score) if home_score is not None else 1.2)
    a_xg = away_xg if (away_xg is not None and away_xg > 0.0) else (float(away_score) if away_score is not None else 1.2)

    p_win, p_draw, p_loss = simulate_poisson_match(h_xg, a_xg)
    h_xpts = round(p_win * 3.0 + p_draw * 1.0, 2)
    a_xpts = round(p_loss * 3.0 + p_draw * 1.0, 2)
    return h_xpts, a_xpts


def get_league_standings(
    season: int = 2026,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Compute league standings including:
    Points, Wins, Draws, Losses, Goals For, Goals Against, Goal Diff,
    xPTS, Luck Index (Points - xPTS), Total xG, Total xGA, and Form (last 5).
    """
    conn = get_db_connection(db_path)
    try:
        team_meta = get_team_metadata_map(conn=conn)
        cur = conn.cursor()

        # Query all finished matches with xG from team_match_flab_stats
        cur.execute(
            """
            SELECT 
                m.match_id,
                m.matchweek,
                m.date,
                m.home_team_id,
                m.away_team_id,
                m.home_score,
                m.away_score,
                f_home.xg AS home_xg,
                f_away.xg AS away_xg
            FROM matches m
            LEFT JOIN team_match_flab_stats f_home
                ON m.match_id = f_home.match_id AND m.home_team_id = f_home.team_id
            LEFT JOIN team_match_flab_stats f_away
                ON m.match_id = f_away.match_id AND m.away_team_id = f_away.team_id
            WHERE m.season = ? AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
            ORDER BY m.date ASC, m.matchweek ASC;
            """,
            (season,),
        )
        match_rows = cur.fetchall()

        # Aggregate stats per team
        records: Dict[str, Dict[str, Any]] = {}

        def _init_team(tid: str) -> Dict[str, Any]:
            meta = team_meta.get(tid, {})
            name = meta.get("name", TEAM_NAME_MAP.get(tid, tid))
            short_name = meta.get("short_name", name)
            return {
                "team_id": tid,
                "name": name,
                "short_name": short_name,
                "played": 0,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "gf": 0,
                "ga": 0,
                "gd": 0,
                "points": 0,
                "xg_total": 0.0,
                "xga_total": 0.0,
                "xpts_total": 0.0,
                "luck_index": 0.0,
                "form_list": [],
            }

        for row in match_rows:
            h_id = row["home_team_id"]
            a_id = row["away_team_id"]
            h_score = int(row["home_score"])
            a_score = int(row["away_score"])
            h_xg = float(row["home_xg"]) if row["home_xg"] is not None else None
            a_xg = float(row["away_xg"]) if row["away_xg"] is not None else None

            if h_id not in records:
                records[h_id] = _init_team(h_id)
            if a_id not in records:
                records[a_id] = _init_team(a_id)

            h_rec = records[h_id]
            a_rec = records[a_id]

            # Played & Goals
            h_rec["played"] += 1
            a_rec["played"] += 1
            h_rec["gf"] += h_score
            h_rec["ga"] += a_score
            a_rec["gf"] += a_score
            a_rec["ga"] += h_score

            # Results & Points
            if h_score > a_score:
                h_rec["won"] += 1
                h_rec["points"] += 3
                h_rec["form_list"].append("W")
                a_rec["lost"] += 1
                a_rec["form_list"].append("L")
            elif h_score == a_score:
                h_rec["drawn"] += 1
                h_rec["points"] += 1
                h_rec["form_list"].append("D")
                a_rec["drawn"] += 1
                a_rec["points"] += 1
                a_rec["form_list"].append("D")
            else:
                h_rec["lost"] += 1
                h_rec["form_list"].append("L")
                a_rec["won"] += 1
                a_rec["points"] += 3
                a_rec["form_list"].append("W")

            # xG and xGA
            if h_xg is not None:
                h_rec["xg_total"] += h_xg
                a_rec["xga_total"] += h_xg
            if a_xg is not None:
                a_rec["xg_total"] += a_xg
                h_rec["xga_total"] += a_xg

            # Poisson xPTS
            h_xpts, a_xpts = _compute_match_xpts(h_score, a_score, h_xg, a_xg)
            h_rec["xpts_total"] += h_xpts
            a_rec["xpts_total"] += a_xpts

        standings: List[Dict[str, Any]] = []
        for tid, r in records.items():
            r["gd"] = r["gf"] - r["ga"]
            r["xg_total"] = round(r["xg_total"], 2)
            r["xga_total"] = round(r["xga_total"], 2)
            r["xpts_total"] = round(r["xpts_total"], 2)
            r["luck_index"] = round(r["points"] - r["xpts_total"], 2)
            r["form"] = r["form_list"][-5:]
            standings.append(r)

        # Sort by Points DESC, Goal Diff DESC, Goals For DESC
        standings.sort(
            key=lambda x: (x["points"], x["gd"], x["gf"]),
            reverse=True,
        )

        for rank_idx, team in enumerate(standings, start=1):
            team["rank"] = rank_idx

        # Sort copy to determine xpts rank
        xpts_sorted = sorted(standings, key=lambda x: x["xpts_total"], reverse=True)
        for xpts_rank_idx, team in enumerate(xpts_sorted, start=1):
            team["xpts_rank"] = xpts_rank_idx

        return standings
    finally:
        conn.close()


def get_matchweek_matches(
    season: int = 2026,
    matchweek: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Return match cards and schedule for a specified matchweek (or latest active matchweek).
    Includes deep-linkable URLs, scores, and tactical status.
    """
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT matchweek
            FROM matches
            WHERE season = ? AND matchweek IS NOT NULL
            ORDER BY matchweek ASC;
            """,
            (season,),
        )
        available_weeks = [int(r[0]) for r in cur.fetchall()]

        if not available_weeks:
            return {
                "available_matchweeks": [],
                "selected_matchweek": 1,
                "matches": [],
            }

        # If matchweek is not specified, select the latest week that has finished matches
        if matchweek is None or matchweek not in available_weeks:
            cur.execute(
                """
                SELECT MAX(matchweek)
                FROM matches
                WHERE season = ? AND home_score IS NOT NULL;
                """,
                (season,),
            )
            row = cur.fetchone()
            selected_week = int(row[0]) if (row and row[0] is not None) else available_weeks[0]
        else:
            selected_week = matchweek

        team_meta = get_team_metadata_map(conn=conn)

        cur.execute(
            """
            SELECT 
                m.match_id,
                m.matchweek,
                m.date,
                m.home_team_id,
                m.away_team_id,
                m.home_score,
                m.away_score,
                m.stadium,
                f_home.xg AS home_xg,
                f_away.xg AS away_xg
            FROM matches m
            LEFT JOIN team_match_flab_stats f_home
                ON m.match_id = f_home.match_id AND m.home_team_id = f_home.team_id
            LEFT JOIN team_match_flab_stats f_away
                ON m.match_id = f_away.match_id AND m.away_team_id = f_away.team_id
            WHERE m.season = ? AND m.matchweek = ?
            ORDER BY m.date ASC, m.match_id ASC;
            """,
            (season, selected_week),
        )
        match_rows = cur.fetchall()

        match_list: List[Dict[str, Any]] = []
        for r in match_rows:
            mid = str(r["match_id"])
            h_id = str(r["home_team_id"])
            a_id = str(r["away_team_id"])
            h_name = team_meta.get(h_id, {}).get("name", TEAM_NAME_MAP.get(h_id, h_id))
            a_name = team_meta.get(a_id, {}).get("name", TEAM_NAME_MAP.get(a_id, a_id))
            h_short = team_meta.get(h_id, {}).get("short_name", h_name)
            a_short = team_meta.get(a_id, {}).get("short_name", a_name)

            h_score = r["home_score"]
            a_score = r["away_score"]
            h_xg = round(float(r["home_xg"]), 2) if r["home_xg"] is not None else None
            a_xg = round(float(r["away_xg"]), 2) if r["away_xg"] is not None else None

            # Generate external URLs
            match_dict = {
                "match_id": mid,
                "date": str(r["date"]) if r["date"] else "",
                "home_team_id": h_id,
                "away_team_id": a_id,
                "home_team": h_name,
                "away_team": a_name,
            }
            ext_links = generate_match_external_links(match_dict)

            is_finished = (h_score is not None and a_score is not None)

            match_list.append(
                {
                    "match_id": mid,
                    "matchweek": selected_week,
                    "date": str(r["date"]) if r["date"] else "",
                    "home_team_id": h_id,
                    "away_team_id": a_id,
                    "home_team_name": h_name,
                    "away_team_name": a_name,
                    "home_short_name": h_short,
                    "away_short_name": a_short,
                    "home_score": h_score,
                    "away_score": a_score,
                    "is_finished": is_finished,
                    "stadium": str(r["stadium"]) if r["stadium"] else "",
                    "home_xg": h_xg,
                    "away_xg": a_xg,
                    "youtube_url": ext_links.get("youtube_search", ""),
                    "official_report_url": ext_links.get("jleague_official", ""),
                    "external_links": ext_links,
                },
            )

        return {
            "available_matchweeks": available_weeks,
            "selected_matchweek": selected_week,
            "matches": match_list,
        }
    finally:
        conn.close()


def get_league_stats_rankings(
    season: int = 2026,
    db_path: str = DEFAULT_DB_PATH,
    top_n: int = 5,
) -> Dict[str, Any]:
    """
    Return Top N team and player leaderboards.
    Team: Goals, Avg Possession, Chance Creation Rate, Total Distance, Sprints.
    Player: Top Scorers, Assists, CBP Leaderboard, Sprints.
    """
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        team_meta = get_team_metadata_map(conn=conn)

        # 1. Team rankings from team_match_flab_stats
        team_rankings: Dict[str, List[Dict[str, Any]]] = {}

        metrics_queries = {
            "possession": (
                """
                SELECT team_id, ROUND(AVG(possession_rate), 1) AS val, COUNT(*) AS count
                FROM team_match_flab_stats f
                JOIN matches m ON f.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY team_id
                ORDER BY val DESC
                LIMIT ?;
                """,
                "%",
            ),
            "chance_create": (
                """
                SELECT team_id, ROUND(AVG(chance_create_rate), 1) AS val, COUNT(*) AS count
                FROM team_match_flab_stats f
                JOIN matches m ON f.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY team_id
                ORDER BY val DESC
                LIMIT ?;
                """,
                "%",
            ),
            "distance": (
                """
                SELECT team_id, ROUND(AVG(distance_m) / 1000.0, 1) AS val, COUNT(*) AS count
                FROM team_match_flab_stats f
                JOIN matches m ON f.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY team_id
                ORDER BY val DESC
                LIMIT ?;
                """,
                "km",
            ),
            "sprints": (
                """
                SELECT team_id, ROUND(AVG(sprints), 1) AS val, COUNT(*) AS count
                FROM team_match_flab_stats f
                JOIN matches m ON f.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY team_id
                ORDER BY val DESC
                LIMIT ?;
                """,
                "回",
            ),
        }

        for cat_key, (sql_query, unit) in metrics_queries.items():
            cur.execute(sql_query, (season, top_n))
            rows = cur.fetchall()
            leaderboard: List[Dict[str, Any]] = []
            for rank_idx, r in enumerate(rows, start=1):
                tid = str(r[0])
                name = team_meta.get(tid, {}).get("name", TEAM_NAME_MAP.get(tid, tid))
                leaderboard.append(
                    {
                        "rank": rank_idx,
                        "team_id": tid,
                        "team_name": name,
                        "value": r[1],
                        "unit": unit,
                        "matches_count": r[2],
                    },
                )
            team_rankings[cat_key] = leaderboard

        # 2. Player rankings from player_match_stats
        player_rankings: Dict[str, List[Dict[str, Any]]] = {}

        player_queries = {
            "goals": (
                """
                SELECT p.player_id, p.player_name, p.team_id, SUM(p.goals) AS val, COUNT(*) AS matches_count
                FROM player_match_stats p
                JOIN matches m ON p.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY p.player_id, p.player_name, p.team_id
                HAVING val > 0
                ORDER BY val DESC, matches_count ASC
                LIMIT ?;
                """,
                "得点",
            ),
            "assists": (
                """
                SELECT p.player_id, p.player_name, p.team_id, SUM(p.assists) AS val, COUNT(*) AS matches_count
                FROM player_match_stats p
                JOIN matches m ON p.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY p.player_id, p.player_name, p.team_id
                HAVING val > 0
                ORDER BY val DESC, matches_count ASC
                LIMIT ?;
                """,
                "アシスト",
            ),
            "cbp_total": (
                """
                SELECT p.player_id, p.player_name, p.team_id, ROUND(SUM(p.cbp_points), 1) AS val, COUNT(*) AS matches_count
                FROM player_match_stats p
                JOIN matches m ON p.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY p.player_id, p.player_name, p.team_id
                ORDER BY val DESC
                LIMIT ?;
                """,
                "pt",
            ),
            "sprints": (
                """
                SELECT p.player_id, p.player_name, p.team_id, SUM(p.sprints) AS val, COUNT(*) AS matches_count
                FROM player_match_stats p
                JOIN matches m ON p.match_id = m.match_id
                WHERE m.season = ?
                GROUP BY p.player_id, p.player_name, p.team_id
                ORDER BY val DESC
                LIMIT ?;
                """,
                "回",
            ),
        }

        for p_cat_key, (p_sql, p_unit) in player_queries.items():
            cur.execute(p_sql, (season, top_n))
            p_rows = cur.fetchall()
            p_leaderboard: List[Dict[str, Any]] = []
            for rank_idx, pr in enumerate(p_rows, start=1):
                pid = str(pr[0]) if pr[0] else ""
                pname = str(pr[1]) if pr[1] else "不明"
                ptid = str(pr[2]) if pr[2] else ""
                tname = team_meta.get(ptid, {}).get("name", TEAM_NAME_MAP.get(ptid, ptid))

                # Lookup photo url if available
                photo_url = ""
                if pid:
                    cur.execute(
                        "SELECT photo_url FROM entity_master_players WHERE player_id = ? LIMIT 1;",
                        (pid,),
                    )
                    ph_row = cur.fetchone()
                    if ph_row and ph_row[0]:
                        photo_url = str(ph_row[0])

                p_leaderboard.append(
                    {
                        "rank": rank_idx,
                        "player_id": pid,
                        "player_name": pname,
                        "team_id": ptid,
                        "team_name": tname,
                        "value": pr[3],
                        "unit": p_unit,
                        "matches_count": pr[4],
                        "photo_url": photo_url,
                    },
                )
            player_rankings[p_cat_key] = p_leaderboard

        return {
            "team_rankings": team_rankings,
            "player_rankings": player_rankings,
        }
    finally:
        conn.close()


def get_tactical_positioning_map_data(
    season: int = 2026,
    metric_preset: str = "possession_vs_press",
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Return 2D tactical positioning scatter coordinates for all teams.
    Presets:
    1. 'possession_vs_press': X = Avg Possession Rate (%), Y = Avg CBP Gain points (or PA entries)
    2. 'xg_attack_vs_defense': X = Avg xG, Y = Avg xGA
    3. 'physical_distance_vs_sprints': X = Avg Distance (km), Y = Avg Sprints
    """
    conn = get_db_connection(db_path)
    try:
        team_meta = get_team_metadata_map(conn=conn)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT 
                team_id,
                ROUND(AVG(possession_rate), 2) AS avg_poss,
                ROUND(AVG(cbp_gain), 2) AS avg_gain,
                ROUND(AVG(xg), 2) AS avg_xg,
                ROUND(AVG(pa_entries), 2) AS avg_pa_entry,
                ROUND(AVG(distance_m) / 1000.0, 2) AS avg_dist_km,
                ROUND(AVG(sprints), 2) AS avg_sprints,
                COUNT(*) AS match_count
            FROM team_match_flab_stats f
            JOIN matches m ON f.match_id = m.match_id
            WHERE m.season = ?
            GROUP BY team_id
            ORDER BY team_id ASC;
            """,
            (season,),
        )
        rows = cur.fetchall()

        # Standings to get current actual rank
        standings = get_league_standings(season=season, db_path=db_path)
        rank_map = {t["team_id"]: t["rank"] for t in standings}
        xga_map = {t["team_id"]: round(t["xga_total"] / max(t["played"], 1), 2) for t in standings}

        teams_data: List[Dict[str, Any]] = []

        for r in rows:
            tid = str(r[0])
            name = team_meta.get(tid, {}).get("name", TEAM_NAME_MAP.get(tid, tid))
            short_name = team_meta.get(tid, {}).get("short_name", name)
            rank = rank_map.get(tid, 99)

            poss = float(r[1]) if r[1] is not None else 50.0
            gain = float(r[2]) if r[2] is not None else 10.0
            xg = float(r[3]) if r[3] is not None else 1.2
            xga = xga_map.get(tid, 1.2)
            dist_km = float(r[5]) if r[5] is not None else 110.0
            sprints = float(r[6]) if r[6] is not None else 110.0

            if metric_preset == "xg_attack_vs_defense":
                x_val = xg
                y_val = xga
            elif metric_preset == "physical_distance_vs_sprints":
                x_val = dist_km
                y_val = sprints
            else:  # "possession_vs_press"
                x_val = poss
                y_val = gain

            teams_data.append(
                {
                    "team_id": tid,
                    "team_name": name,
                    "short_name": short_name,
                    "rank": rank,
                    "x": x_val,
                    "y": y_val,
                    "possession": poss,
                    "cbp_gain": gain,
                    "xg": xg,
                    "xga": xga,
                    "distance_km": dist_km,
                    "sprints": sprints,
                },
            )

        if not teams_data:
            return {
                "preset": metric_preset,
                "x_label": "",
                "y_label": "",
                "x_avg": 0.0,
                "y_avg": 0.0,
                "quadrant_labels": {},
                "teams": [],
            }

        # Calculate league averages for reference cross lines
        x_avg = round(sum(t["x"] for t in teams_data) / len(teams_data), 2)
        y_avg = round(sum(t["y"] for t in teams_data) / len(teams_data), 2)

        if metric_preset == "xg_attack_vs_defense":
            preset_info = {
                "preset": metric_preset,
                "title": "攻守期待値マップ (xG vs xGA)",
                "x_label": "攻撃期待値 (1試合平均xG)",
                "y_label": "守備被期待値 (1試合平均xGA)",
                "x_avg": x_avg,
                "y_avg": y_avg,
                "quadrant_labels": {
                    "top_right": "高攻撃・高失点リスク（撃ち合い型）",
                    "top_left": "低攻撃・高失点リスク（苦戦型）",
                    "bottom_right": "高攻撃・強固守備（圧倒型）",
                    "bottom_left": "低攻撃・堅守型（ロースコア型）",
                },
            }
        elif metric_preset == "physical_distance_vs_sprints":
            preset_info = {
                "preset": metric_preset,
                "title": "フィジカル走量マップ (走行距離 vs スプリント数)",
                "x_label": "チーム総走行距離 (km/試合)",
                "y_label": "チーム総スプリント回数 (回/試合)",
                "x_avg": x_avg,
                "y_avg": y_avg,
                "quadrant_labels": {
                    "top_right": "ハイインテンシティ型（走量・スピード共存）",
                    "top_left": "スプリント特化型（メリハリ型）",
                    "bottom_right": "持続走量特化型（ポジショナル型）",
                    "bottom_left": "低走量型（省エネ・ブロック型）",
                },
            }
        else:  # possession_vs_press
            preset_info = {
                "preset": metric_preset,
                "title": "戦術スタイルマップ (ポゼッション vs プレッシング奪取)",
                "x_label": "ボール保持率 (平均ポゼッション %)",
                "y_label": "プレッシング奪取力 (平均CBP奪取 pt)",
                "x_avg": x_avg,
                "y_avg": y_avg,
                "quadrant_labels": {
                    "top_right": "支配・ハイプレス型（ゲーゲンプレス）",
                    "top_left": "速攻・ハイプレス型（縦志向ショートカウンター）",
                    "bottom_right": "ポジショナル・ブロック型（ボール保持主導）",
                    "bottom_left": "リトリート・ロングカウンター型（専守防衛）",
                },
            }

        preset_info["teams"] = teams_data
        return preset_info
    finally:
        conn.close()


def get_matchweek_report_cards(
    season: int = 2026,
    matchweek: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Return calculated 6-metric report cards for all 20 clubs in a given matchweek.
    Returns both team_cards (sorted by total_score DESC) and match_pairs (paired by match).
    """
    mw_data = get_matchweek_matches(
        season=season,
        matchweek=matchweek,
        db_path=db_path,
    )
    selected_week = mw_data.get("selected_matchweek", 1)
    matches = mw_data.get("matches", [])

    calc = MatchReportCardCalculator(db_path=db_path)
    team_cards: List[Dict[str, Any]] = []
    match_pairs: List[Dict[str, Any]] = []

    for m in matches:
        mid = m.get("match_id", "")
        hid = m.get("home_team_id", "")
        aid = m.get("away_team_id", "")
        h_score = m.get("home_score")
        a_score = m.get("away_score")

        if h_score is None or a_score is None:
            continue

        h_card = calc.calculate_report_card(match_id=mid, team_id=hid)
        a_card = calc.calculate_report_card(match_id=mid, team_id=aid)

        h_entry = {
            "match_id": mid,
            "team_id": hid,
            "team_name": m.get("home_team", hid),
            "opp_team_id": aid,
            "opp_team_name": m.get("away_team", aid),
            "is_home": True,
            "score": f"{h_score}-{a_score}",
            "rank": h_card.get("rank", "B+"),
            "total_score": h_card.get("total_score", 0),
            "critique": h_card.get("critique", {}),
            "metrics": h_card.get("metrics", {}),
        }
        a_entry = {
            "match_id": mid,
            "team_id": aid,
            "team_name": m.get("away_team", aid),
            "opp_team_id": hid,
            "opp_team_name": m.get("home_team", hid),
            "is_home": False,
            "score": f"{a_score}-{h_score}",
            "rank": a_card.get("rank", "B+"),
            "total_score": a_card.get("total_score", 0),
            "critique": a_card.get("critique", {}),
            "metrics": a_card.get("metrics", {}),
        }

        team_cards.extend([h_entry, a_entry])
        match_pairs.append({
            "match_id": mid,
            "date": m.get("date", ""),
            "stadium": m.get("stadium", ""),
            "home": h_entry,
            "away": a_entry,
        })

    # Sort team cards by total_score DESC
    team_cards.sort(key=lambda x: x["total_score"], reverse=True)
    for idx, card in enumerate(team_cards, start=1):
        card["week_rank"] = idx

    return {
        "season": season,
        "matchweek": selected_week,
        "available_matchweeks": mw_data.get("available_matchweeks", []),
        "team_cards": team_cards,
        "match_pairs": match_pairs,
    }
