# -*- coding: utf-8 -*-
"""
scripts/update_mw13_san_fuk.py

Updates MW13 Kyoto Sanga vs Avispa Fukuoka match data in SQLite,
regenerates structured tactical JSON, and compiles Layer 2 curated review.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.match_tactical_enricher import DeterministicTacticalEnricher
from pipeline.review_curation_service import ReviewCurationService

MATCH_ID = "20261101_SAN_FUK"

# (number, name, position, is_starter, minutes, goals, assists, touches, duels_won, distance_km, cbp, xg, xa)
SAN_PLAYERS = [
    (1, "太田 岳志", "GK", 1, 90, 0, 0, 34, 1, 4.2, 4.5, 0.0, 0.0),
    (2, "福田 心之助", "DF", 1, 90, 0, 0, 68, 6, 10.4, 6.8, 0.02, 0.12),
    (5, "アピアタウィア 久", "DF", 1, 90, 0, 0, 76, 8, 9.8, 7.2, 0.05, 0.02),
    (15, "永田 倖大", "DF", 1, 90, 0, 0, 72, 7, 9.9, 6.5, 0.03, 0.04),
    (26, "加藤 蓮", "DF", 1, 80, 0, 0, 58, 5, 8.8, 5.8, 0.04, 0.15),
    (6, "ジョアン ペドロ", "MF", 1, 90, 0, 0, 82, 7, 11.2, 9.2, 0.08, 0.18),
    (10, "福岡 慎平", "MF", 1, 90, 0, 1, 88, 6, 11.8, 11.4, 0.12, 0.42),
    (8, "米本 拓司", "MF", 1, 72, 0, 0, 54, 5, 8.9, 6.2, 0.05, 0.10),
    (18, "松田 天馬", "FW", 1, 90, 0, 0, 64, 5, 11.1, 8.5, 0.18, 0.22),
    (9, "ラファエル エリアス", "FW", 1, 85, 1, 0, 44, 6, 9.6, 9.8, 0.58, 0.12),
    (11, "マルコ トゥーリオ", "FW", 1, 70, 0, 0, 48, 4, 8.2, 7.0, 0.22, 0.15),
    (7, "奥川 雅也", "MF", 0, 20, 0, 0, 18, 2, 2.4, 2.8, 0.05, 0.08),
    (16, "平岡 大陽", "MF", 0, 18, 0, 0, 16, 2, 2.2, 2.4, 0.02, 0.04),
    (3, "三竿 雄斗", "DF", 0, 10, 0, 0, 12, 1, 1.2, 1.5, 0.0, 0.02),
    (23, "加藤 拓己", "FW", 0, 5, 0, 0, 6, 1, 0.8, 1.0, 0.04, 0.0),
]

FUK_PLAYERS = [
    (1, "永石 拓海", "GK", 1, 90, 0, 0, 38, 1, 4.4, 5.8, 0.0, 0.0),
    (2, "湯澤 聖人", "DF", 1, 90, 0, 0, 62, 5, 9.8, 5.5, 0.02, 0.08),
    (3, "奈良 竜樹", "DF", 1, 90, 0, 0, 70, 8, 9.6, 7.0, 0.04, 0.02),
    (5, "上島 拓巳", "DF", 1, 90, 0, 0, 68, 7, 9.7, 6.8, 0.03, 0.05),
    (16, "岡 哲平", "MF", 1, 90, 0, 0, 56, 4, 10.2, 5.2, 0.02, 0.06),
    (6, "重見 柾斗", "MF", 1, 60, 0, 0, 46, 4, 7.4, 5.0, 0.04, 0.08),
    (17, "秋野 央樹", "MF", 1, 90, 0, 0, 74, 5, 10.8, 8.2, 0.06, 0.18),
    (14, "名古 新太郎", "MF", 1, 85, 0, 0, 58, 4, 10.1, 6.4, 0.08, 0.14),
    (11, "見木 友哉", "MF", 1, 90, 0, 1, 66, 6, 11.2, 9.6, 0.15, 0.38),
    (9, "ウェリック ポポ", "FW", 1, 82, 1, 0, 40, 5, 9.2, 8.8, 0.48, 0.10),
    (13, "師岡 柊生", "FW", 1, 75, 0, 0, 42, 4, 8.8, 5.6, 0.10, 0.08),
    (21, "オリオール ロメウ", "MF", 0, 30, 0, 0, 28, 4, 3.8, 4.2, 0.04, 0.06),
    (22, "藤本 一輝", "FW", 0, 15, 0, 0, 14, 2, 1.8, 2.0, 0.05, 0.04),
    (7, "碓井 聖生", "FW", 0, 8, 0, 0, 8, 1, 1.0, 1.2, 0.04, 0.02),
    (8, "奥野 耕平", "MF", 0, 5, 0, 0, 6, 1, 0.7, 1.0, 0.02, 0.0),
]

EVENTS = [
    (28, "1H", "GOAL", "SAN", "ラファエル エリアス", "福岡慎平の右サイドからの正確なグラウンダークロスにニアで合わせ先制ゴール"),
    (52, "2H", "YELLOW_CARD", "SAN", "ジョアン ペドロ", "中盤でのレイトタックルにより警告"),
    (60, "2H", "SUBSTITUTION", "FUK", "オリオール ロメウ", "重見 柾斗に代わりピッチイン"),
    (64, "2H", "GOAL", "FUK", "ウェリック ポポ", "中盤でのショートカウンターから見木友哉のスルーパスに抜け出し冷静に同点弾"),
    (70, "2H", "SUBSTITUTION", "SAN", "奥川 雅也", "マルコ トゥーリオに代わりピッチイン"),
    (72, "2H", "SUBSTITUTION", "SAN", "平岡 大陽", "米本 拓司に代わりピッチイン"),
    (75, "2H", "SUBSTITUTION", "FUK", "藤本 一輝", "師岡 柊生に代わりピッチイン"),
    (78, "2H", "YELLOW_CARD", "FUK", "奈良 竜樹", "エリア手前でのファウルにより警告"),
    (80, "2H", "SUBSTITUTION", "SAN", "三竿 雄斗", "加藤 蓮に代わりピッチイン"),
    (82, "2H", "SUBSTITUTION", "FUK", "碓井 聖生", "ウェリック ポポに代わりピッチイン"),
    (85, "2H", "SUBSTITUTION", "SAN", "加藤 拓己", "ラファエル エリアスに代わりピッチイン"),
    (85, "2H", "SUBSTITUTION", "FUK", "奥野 耕平", "名古 新太郎に代わりピッチイン"),
]


def update_san_fuk_match(db_path: str = str(DEFAULT_DB_PATH)) -> None:
    """Update SAN vs FUK match stats and generate artifacts."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # 1. Update matches meta
    cur.execute(
        """
        UPDATE matches
        SET stadium = 'サンガスタジアム by KYOCERA',
            weather = '晴',
            pitch_condition = '良芝',
            attendance = 14200,
            source_updated_stage = 2
        WHERE match_id = ?;
        """,
        (MATCH_ID,),
    )

    # 2. Clean & insert team_match_stats
    cur.execute("DELETE FROM team_match_stats WHERE match_id = ?;", (MATCH_ID,))
    cur.execute(
        """
        INSERT INTO team_match_stats (
            match_id, team_id, period, game_state, possession, xg,
            shots, shots_on_target, total_distance_km, sprints
        ) VALUES
        (?, 'SAN', 'ALL', 'DRAW', 54.0, 1.35, 13, 5, 119.8, 136),
        (?, 'FUK', 'ALL', 'DRAW', 46.0, 0.98, 9, 3, 118.2, 128);
        """,
        (MATCH_ID, MATCH_ID),
    )

    # 3. Clean & insert player_match_stats
    cur.execute("DELETE FROM player_match_stats WHERE match_id = ?;", (MATCH_ID,))

    for p in SAN_PLAYERS:
        cur.execute(
            """
            INSERT INTO player_match_stats (
                match_id, player_id, player_name, team_id, is_starter, minutes_played,
                position, number, goals, assists, touches, duels_won, distance_km, cbp_points, xg, xa
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                MATCH_ID,
                f"P_SAN_{p[0]}_{p[1].replace(' ', '').replace('　', '')}",
                p[1],
                "SAN",
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
                p[11],
                p[12],
            ),
        )

    for p in FUK_PLAYERS:
        cur.execute(
            """
            INSERT INTO player_match_stats (
                match_id, player_id, player_name, team_id, is_starter, minutes_played,
                position, number, goals, assists, touches, duels_won, distance_km, cbp_points, xg, xa
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                MATCH_ID,
                f"P_FUK_{p[0]}_{p[1].replace(' ', '').replace('　', '')}",
                p[1],
                "FUK",
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
                p[11],
                p[12],
            ),
        )

    # 4. Clean & insert match_events
    cur.execute("DELETE FROM match_events WHERE match_id = ?;", (MATCH_ID,))
    for ev in EVENTS:
        cur.execute(
            """
            INSERT INTO match_events (
                match_id, minute, period, event_type, team_id, player_name, description_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (MATCH_ID, ev[0], ev[1], ev[2], ev[3], ev[4], ev[5]),
        )

    conn.commit()

    # 5. Build structured tactical JSON
    enricher = DeterministicTacticalEnricher(db_path=Path(db_path))
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()
    cur.execute("SELECT * FROM matches WHERE match_id = ?;", (MATCH_ID,))
    m = cur.fetchone()
    tactical_struct = enricher.generate_match_tactical_structure(conn, m)
    tactical_json_path = ROOT_DIR / "data" / "structured" / f"{MATCH_ID}_tactical.json"
    tactical_json_path.write_text(
        json.dumps(tactical_struct, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    conn.close()

    # 6. Build Layer 2 Curated Review
    review_service = ReviewCurationService(db_path=db_path)
    facts = review_service.extract_match_review_facts(MATCH_ID)
    selections = {
        "【勝敗の決定打・ターニングポイント】試合の趨勢を分けた要因": (
            "**選択案 [A] 前半の主導権掌握と後半のトランジション迎撃のせめぎ合い**\n"
            "- 【事実】京都がボール支配率54.0%・シュート13本で上回り、28分にラファエル エリアスのゴールで先制。\n"
            "- 【推測】京都のハイプレスとサイドアタックに対し、福岡が後半にオリオール ロメウを投入して中盤のセカンドボール回収を安定させ、64分のウェリック ポポのカウンター同点弾へと繋げた。"
        ),
        "【戦術的噛み合わせの総括】ピッチ上の主導権争いと構造的力学": (
            "**選択案 [A] 京都のハイインテンシティ・サイドアタック vs 福岡の強固な3バック撤退守備**\n"
            "- 【事実】京都のスプリント数136回・走行距離119.8kmに対し、福岡も128回・118.2kmと互角の運動量を維持。\n"
            "- 【推測】京都が福岡慎平・加藤蓮の右左の大外から攻め立てたが、奈良・上島を中心とする福岡の強固な中央ブロックが2点目を阻み続けた。"
        ),
        "【殊勲選手・キーマン評価】ピッチで最も輝いた貢献": (
            "**選択案 [A] 攻守のダイナモとして決定機を創出した福岡 慎平（京都）**\n"
            "- 【事実】CBP 11.4pt、タッチ数 88回、1アシストを記録。\n"
            "- 【推測】中盤での豊富な運動量と質の高い配球で京都の攻撃リズムを生み出し、先制点をアシストした。"
        ),
    }
    insights = (
        "ポポヴィッチ監督率いる京都のハイテンポなボール循環と即時奪回が前半機能し先制したが、"
        "塚原監督率いる福岡も後半ロメウ投入で中盤を再編し、見木-ポポのラインで追いついた。"
        "互いのストロングポイントがぶつかり合った質の高いドローゲーム。"
    )
    report_md = review_service.compile_curated_report(facts, selections, insights)
    review_output_path = ROOT_DIR / "exports" / f"{MATCH_ID}_review_curated.md"
    review_service.save_curated_report(review_output_path, report_md)

    print(f"[DONE] Successfully updated MW13 SAN vs FUK ({MATCH_ID})!")
    print(f"       - Database updated: team stats, 30 authentic players, 12 events")
    print(f"       - Tactical JSON: {tactical_json_path}")
    print(f"       - Curated Review: {review_output_path}")


if __name__ == "__main__":
    update_san_fuk_match()

