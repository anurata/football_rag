"""
scripts/import_mw13_data.py

Imports Matchweek 13 fixtures and player statistics into SQLite and structured JSON
for the 2026 season.
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection

MW13_MATCHES = [
    {
        "match_id": "20261101_FCT_REY",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "FCT",
        "away_team_id": "REY",
        "home_score": 3,
        "away_score": 3,
        "stadium": "味の素スタジアム",
        "weather": "晴",
        "pitch_condition": "良芝",
        "attendance": 28450,
    },
    {
        "match_id": "20261101_KAS_VER",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "KAS",
        "away_team_id": "VER",
        "home_score": 3,
        "away_score": 3,
        "stadium": "県立カシマサッカースタジアム",
        "weather": "曇",
        "pitch_condition": "良芝",
        "attendance": 21890,
    },
    {
        "match_id": "20261101_KAW_JEF",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "KAW",
        "away_team_id": "JEF",
        "home_score": 3,
        "away_score": 0,
        "stadium": "Uvanceとどろきスタジアム by Fujitsu",
        "weather": "晴",
        "pitch_condition": "良芝",
        "attendance": 22400,
    },
    {
        "match_id": "20261101_CER_VOB",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "CER",
        "away_team_id": "VOB",
        "home_score": 1,
        "away_score": 4,
        "stadium": "ヨドコウ桜スタジアム",
        "weather": "雨",
        "pitch_condition": "重馬場",
        "attendance": 19500,
    },
    {
        "match_id": "20261101_NAG_GAM",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "NAG",
        "away_team_id": "GAM",
        "home_score": 0,
        "away_score": 1,
        "stadium": "豊田スタジアム",
        "weather": "晴",
        "pitch_condition": "良芝",
        "attendance": 33100,
    },
    {
        "match_id": "20261101_URA_OKA",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "URA",
        "away_team_id": "OKA",
        "home_score": 2,
        "away_score": 0,
        "stadium": "埼玉スタジアム2002",
        "weather": "曇",
        "pitch_condition": "良芝",
        "attendance": 38500,
    },
    {
        "match_id": "20261101_SAN_FUK",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "SAN",
        "away_team_id": "FUK",
        "home_score": 2,
        "away_score": 3,
        "stadium": "サンガスタジアム by KYOCERA",
        "weather": "晴",
        "pitch_condition": "良芝",
        "attendance": 14200,
    },
    {
        "match_id": "20261101_MIT_ZEL",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "MIT",
        "away_team_id": "ZEL",
        "home_score": 1,
        "away_score": 2,
        "stadium": "ケーズデンキスタジアム水戸",
        "weather": "晴",
        "pitch_condition": "良芝",
        "attendance": 10300,
    },
    {
        "match_id": "20261101_PUL_VVN",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "PUL",
        "away_team_id": "VVN",
        "home_score": 2,
        "away_score": 1,
        "stadium": "IAIスタジアム日本平",
        "weather": "晴",
        "pitch_condition": "良芝",
        "attendance": 16500,
    },
    {
        "match_id": "20261101_MAR_HIR",
        "season": 2026,
        "matchweek": 13,
        "date": "2026-11-01",
        "home_team_id": "MAR",
        "away_team_id": "HIR",
        "home_score": 3,
        "away_score": 2,
        "stadium": "日産スタジアム",
        "weather": "晴",
        "pitch_condition": "良芝",
        "attendance": 31200,
    },
]

FCT_PLAYERS = [
    (81, "キム スンギュ", "GK", 1, 90, 0, 0, 32, 1, 4.8, 1.8),
    (22, "石原 広教", "DF", 1, 90, 0, 1, 64, 5, 10.5, 4.2),
    (24, "アレクサンダー ショルツ", "DF", 1, 90, 0, 0, 71, 7, 9.8, 4.0),
    (4, "稲村 隼翔", "DF", 1, 90, 0, 0, 68, 6, 10.2, 3.9),
    (6, "バングーナガンデ 佳史扶", "DF", 1, 75, 0, 1, 58, 4, 8.9, 4.5),
    (8, "高 宇洋", "MF", 1, 90, 0, 0, 82, 9, 11.8, 5.1),
    (7, "安斎 颯馬", "MF", 1, 90, 1, 0, 60, 5, 11.2, 5.8),
    (27, "常盤 亨太", "MF", 1, 90, 0, 1, 72, 8, 11.4, 4.9),
    (10, "佐藤 恵允", "MF", 1, 65, 1, 0, 42, 3, 7.8, 5.0),
    (71, "荒木 遼太郎", "MF", 1, 80, 1, 0, 45, 2, 9.1, 6.2),
    (26, "長倉 幹樹", "FW", 1, 85, 0, 0, 38, 4, 10.1, 4.3),
    (37, "小泉 慶", "MF", 0, 25, 0, 0, 20, 3, 3.2, 1.8),
    (11, "遠藤 渓太", "MF", 0, 15, 0, 0, 12, 1, 1.9, 1.4),
]

REY_PLAYERS = [
    (1, "松本 健太", "GK", 1, 90, 0, 0, 35, 1, 4.5, 1.5),
    (4, "古賀 太陽", "DF", 1, 90, 0, 0, 65, 6, 9.9, 4.1),
    (3, "ジエゴ", "DF", 1, 90, 0, 1, 58, 5, 10.1, 4.3),
    (13, "犬飼 智也", "DF", 1, 90, 1, 0, 62, 7, 9.5, 4.0),
    (2, "三丸 拡", "DF", 1, 70, 0, 0, 48, 3, 8.2, 3.6),
    (5, "高嶺 朋樹", "MF", 1, 90, 0, 0, 75, 8, 11.3, 4.8),
    (6, "山田 雄士", "MF", 1, 80, 1, 0, 52, 4, 10.0, 5.2),
    (14, "小屋松 知哉", "MF", 1, 75, 0, 1, 44, 3, 8.8, 4.4),
    (10, "マテウス サヴィオ", "MF", 1, 90, 1, 1, 68, 6, 11.0, 7.2),
    (19, "細谷 真大", "FW", 1, 90, 0, 0, 40, 5, 10.6, 4.5),
    (18, "垣田 裕暉", "FW", 1, 60, 0, 0, 28, 4, 6.8, 3.1),
    (28, "戸嶋 祥郎", "MF", 0, 20, 0, 0, 18, 2, 2.5, 1.6),
]


def import_mw13(db_path: str = DEFAULT_DB_PATH) -> None:
    """Insert MW13 fixtures and player details into database."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # 1. Insert matches
    for m in MW13_MATCHES:
        cur.execute(
            """
            INSERT OR REPLACE INTO matches (
                match_id, season, matchweek, date, home_team_id, away_team_id,
                home_score, away_score, stadium, weather, pitch_condition, attendance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                m["match_id"],
                m["season"],
                m["matchweek"],
                m["date"],
                m["home_team_id"],
                m["away_team_id"],
                m["home_score"],
                m["away_score"],
                m["stadium"],
                m["weather"],
                m["pitch_condition"],
                m["attendance"],
            ),
        )

    # 2. Insert team match stats for 20261101_FCT_REY
    cur.execute(
        """
        INSERT OR REPLACE INTO team_match_stats (
            match_id, team_id, period, game_state, possession,
            shots, shots_on_target, total_distance_km, sprints
        ) VALUES
        ('20261101_FCT_REY', 'FCT', 'FULL', 'DRAW', 52.4, 14, 6, 115.2, 142),
        ('20261101_FCT_REY', 'REY', 'FULL', 'DRAW', 47.6, 13, 5, 114.8, 138);
        """
    )

    # 3. Insert real players for 20261101_FCT_REY
    for p in FCT_PLAYERS:
        cur.execute(
            """
            INSERT OR REPLACE INTO player_match_stats (
                match_id, player_id, player_name, team_id, is_starter, minutes_played,
                position, number, goals, assists, touches, duels_won, distance_km, cbp_points
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "20261101_FCT_REY",
                f"P_FCT_{p[0]}_{p[1]}",
                p[1],
                "FCT",
                p[3],
                p[4],
                p[2],
                p[0],
                p[5],
                p[6],
                p[7],
                p[8],
                p[9],
                p[10],
            ),
        )

    for p in REY_PLAYERS:
        cur.execute(
            """
            INSERT OR REPLACE INTO player_match_stats (
                match_id, player_id, player_name, team_id, is_starter, minutes_played,
                position, number, goals, assists, touches, duels_won, distance_km, cbp_points
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "20261101_FCT_REY",
                f"P_REY_{p[0]}_{p[1]}",
                p[1],
                "REY",
                p[3],
                p[4],
                p[2],
                p[0],
                p[5],
                p[6],
                p[7],
                p[8],
                p[9],
                p[10],
            ),
        )

    conn.commit()
    conn.close()
    print("Successfully imported 10 MW13 matches and player stats into SQLite!")


if __name__ == "__main__":
    import_mw13()
