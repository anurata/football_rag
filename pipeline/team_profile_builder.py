"""2026年J1全20クラブ戦術プロファイル本構築パイプライン (pipeline/team_profile_builder.py).

機能:
- `football.db` の `match_formations`（全120試合実フォーメーション実績）
- `team_match_stats`（全120試合チームテレメトリ・平均スタッツ）
- `tactical_discourse_claims`（公式監督会見＋YouTube戦術言説）
から、全20クラブの戦術プロファイルを決定論的に本構築し、`knowledge/team_tactical_profiles.json` を更新する。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("team_profile_builder")

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("FOOTBALL_DB_PATH", ROOT_DIR / "data" / "football.db"))
OUTPUT_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"

TEAM_NAMES = {
    "CER": "セレッソ大阪",
    "FCT": "FC東京",
    "FUK": "アビスパ福岡",
    "GAM": "ガンバ大阪",
    "HIR": "サンフレッチェ広島",
    "JEF": "ジェフユナイテッド千葉",
    "KAS": "鹿島アントラーズ",
    "KAW": "川崎フロンターレ",
    "MAR": "横浜F・マリノス",
    "MIT": "水戸ホーリーホック",
    "NAG": "名古屋グランパス",
    "OKA": "ファジアーノ岡山",
    "PUL": "清水エスパルス",
    "REY": "柏レイソル",
    "SAN": "京都サンガF.C.",
    "URA": "浦和レッズ",
    "VER": "東京ヴェルディ",
    "VOB": "ヴィッセル神戸",
    "VVN": "V・ファーレン長崎",
    "ZEL": "町田ゼルビア",
}

# 2026シーズン公式会見エビデンスに基づく現監督マスタ
MANAGERS_2026 = {
    "CER": "パブロ マチン",
    "FCT": "松橋 力蔵",
    "FUK": "塚原 真也",
    "GAM": "明神 智和",
    "HIR": "バルトシュ ガウル",
    "JEF": "小林 慶行",
    "KAS": "鬼木 達",
    "KAW": "長谷部 茂利",
    "MAR": "スティーブ コリカ",
    "MIT": "樹森 大介",
    "NAG": "ミハイロ ペトロヴィッチ",
    "OKA": "木山 隆之",
    "PUL": "吉田 孝行",
    "REY": "リカルド ロドリゲス",
    "SAN": "ランコ ポポヴィッチ",
    "URA": "曺 貴裁",
    "VER": "城福 浩",
    "VOB": "ミヒャエル スキッベ",
    "VVN": "高木 琢也",
    "ZEL": "黒田 剛",
}


def _get_team_formations_and_stats(
    conn: sqlite3.Connection,
    team_id: str,
) -> Tuple[str, List[str], Dict[str, float]]:
    """チームの実フォーメーション最頻値・別フォーメーションおよび平均スタッツを返す."""
    f_counter: Counter[str] = Counter()
    for r in conn.execute(
        """
        SELECT home_team_id, away_team_id, home_initial_formation, away_initial_formation
        FROM match_formations
        WHERE match_id LIKE '2026%' AND (home_team_id = ? OR away_team_id = ?)
        """,
        (team_id, team_id),
    ).fetchall():
        f = r[2] if r[0] == team_id else r[3]
        if f:
            f_counter[f] += 1

    common = f_counter.most_common()
    base_f = common[0][0] if common else "4-4-2"
    alt_f = [f for f, cnt in common[1:] if cnt >= 1]

    s_row = conn.execute(
        """
        SELECT AVG(possession), AVG(xg), AVG(total_distance_km), AVG(sprints), AVG(shots), AVG(shots_on_target)
        FROM team_match_stats
        WHERE team_id = ? AND match_id LIKE '2026%'
        """,
        (team_id,),
    ).fetchone()

    stats = {
        "possession": round(float(s_row[0] or 50.0), 1),
        "xg": round(float(s_row[1] or 1.2), 2),
        "distance_km": round(float(s_row[2] or 113.0), 1),
        "sprints": round(float(s_row[3] or 115.0), 1),
        "shots": round(float(s_row[4] or 12.0), 1),
        "shots_on_target": round(float(s_row[5] or 4.0), 1),
    }
    return base_f, alt_f, stats


def _get_team_claims_evidences(
    conn: sqlite3.Connection,
    team_id: str,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """チームの tactical_discourse_claims から公式会見およびYouTubeの代表言説を抽出する."""
    claims = conn.execute(
        """
        SELECT claim_id, segment_id, video_id, channel_name, video_title, time_range,
               source_reliability, manager_mentioned, statement_text, original_quote
        FROM tactical_discourse_claims
        WHERE team_id = ? AND LENGTH(statement_text) >= 25
        ORDER BY
            CASE WHEN source_reliability = 'OFFICIAL_PRESS_CONFERENCE' THEN 0 ELSE 1 END,
            LENGTH(statement_text) DESC
        LIMIT ?
        """,
        (team_id, limit),
    ).fetchall()

    evs: List[Dict[str, Any]] = []
    for c in claims:
        is_official = c[6] == "OFFICIAL_PRESS_CONFERENCE"
        if is_official:
            evs.append(
                {
                    "source_type": "OFFICIAL_PRESS_CONFERENCE",
                    "match_id": c[2],
                    "speaker": f"{c[7]} 監督" if c[7] else "監督",
                    "quote": c[9] or c[8],
                    "context": f"{c[4]} (節: {c[5]})",
                },
            )
        else:
            evs.append(
                {
                    "source_type": "YOUTUBE_ANALYSIS",
                    "channel_name": c[3],
                    "video_title": c[4],
                    "time_range": c[5],
                    "quote": c[9] or c[8],
                    "topic": "TACTICAL_ANALYSIS",
                },
            )
    return evs


def _generate_team_tactical_texts(
    team_id: str,
    base_f: str,
    stats: Dict[str, float],
    manager: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, str], List[str]]:
    """スタッツ実績・フォーメーション・監督スタイルに基づき戦術テキストを生成する."""
    poss = stats["possession"]
    is_high_poss = poss >= 52.0
    is_3back = base_f.startswith("3") or base_f.startswith("5")
    sprints = stats["sprints"]

    # In possession
    if is_high_poss and is_3back:
        in_p = {
            "build_up_style": "positional_3_box_2_progression",
            "target_reliance": "medium",
            "progression_route": "half_space_overload_and_wb_width",
            "tempo": "controlled_possession",
            "summary": f"{manager}監督のもと、3バック（{base_f}）の左右CBが積極的に幅を取り、ボランチとシャドーで中央ハーフスペースに数的優位を形成して前進する（平均保持率{poss}%）。WBを高い位置に押し出して幅を確保する。",
        }
    elif is_high_poss:
        in_p = {
            "build_up_style": "positional_with_vertical_spring",
            "target_reliance": "medium",
            "progression_route": "center_back_progression_and_wing_in_behind",
            "tempo": "dynamic_tempo_switch",
            "summary": f"{manager}監督のもと、4バック（{base_f}）のCBとアンカーを起点にボールを動かし（平均保持率{poss}%）、相手の縦スライドの隙を突いて快速ウイングやインサイドハーフがライン間に潜り込んで打開する。",
        }
    elif is_3back:
        in_p = {
            "build_up_style": "direct_channel_vertical",
            "target_reliance": "high",
            "progression_route": "direct_wb_or_front_target",
            "tempo": "high_tempo_vertical",
            "summary": f"{base_f}の堅牢なブロックから、ボール奪取後は手数をかけずに最前線のターゲットやWBの走力を活かして縦へ速く運ぶ直截的な前進スタイル（平均保持率{poss}%）。",
        }
    else:
        in_p = {
            "build_up_style": "compact_direct_counter",
            "target_reliance": "high",
            "progression_route": "vertical_flank_advance",
            "tempo": "high_tempo_vertical",
            "summary": f"強固な{base_f}の守備網から、サイドバックの素早い押し上げと前線ターゲットへのロングボールを軸に最短手数でゴールへ迫るダイレクトアタック（平均保持率{poss}%）。",
        }

    # Out of possession
    if sprints >= 120.0 and is_high_poss:
        out_p = {
            "defensive_line": "high_line",
            "pressing_trigger": "forward_pressing_and_touchline_trap",
            "pressing_funnel": "funnel_outside",
            "block_shape": f"{base_f}_high_compact",
            "summary": f"前線からのアグレッシブなハイプレスと連動したハイライン（平均スプリント{sprints}回）で相手のビルドアップをサイドへ誘導・制限し、高い位置でのボール奪取を狙う。",
        }
    elif is_3back:
        out_p = {
            "defensive_line": "mid_to_low_block_5_back",
            "pressing_trigger": "midfield_interception_and_wb_press",
            "pressing_funnel": "funnel_into_center_crowd",
            "block_shape": "5-4-1_or_5-2-3_low_block",
            "summary": f"非保持時は両WBが最終ラインに吸収されて5バック化し、自陣ペナルティエリア幅を強固に閉ざして中央への侵入をシャットアウトする組織的ブロック守備。",
        }
    else:
        out_p = {
            "defensive_line": "compact_mid_block",
            "pressing_trigger": "compact_trap_at_middle_third",
            "pressing_funnel": "funnel_outside",
            "block_shape": "4-4-2_compact_mid_block",
            "summary": "中盤と最終ラインの距離感を20〜25mに保ったコンパクトなブロックを敷き、ボールサイドへ組織的にスライドして中央のコースを制限する。",
        }

    # Transitions
    transitions = {
        "positive": "immediate_vertical_attack" if sprints >= 115.0 else "measured_counter_or_recycle",
        "negative": "gegenpressing_and_foul_stop" if is_high_poss else "immediate_drop_to_compact_block",
    }

    # Structural vulnerabilities
    if is_3back and is_high_poss:
        vulns = [
            "WBが攻撃参加した直後の背後広大なスペース（3バック脇のチャンネル）を突かれるカウンターリスク",
            "相手の幅を使ったサイドチェンジに対する3バックとWBのスライド遅れ",
            "ハイプレスを剥がされた際の中盤底（ボランチ脇）のスペース空洞化",
        ]
    elif is_3back:
        vulns = [
            "5バックで深く押し込まれた際のセカンドボール回収遅れと波状攻撃の被弾",
            "前線孤立によるボールキープ失敗からのショートカウンター",
            "相手のミドルシュートに対するボックス手前バイタルエリアの寄せの遅延",
        ]
    elif is_high_poss:
        vulns = [
            "ハイライン背後を突かれた際の一対一およびGKとの広大なスペース",
            "攻撃時にSBが内側または高い位置を取った際の大外カウンター被弾",
            "セットプレーおよびセカンドボール奪回遅れからの失点リスク",
        ]
    else:
        vulns = [
            "自陣深くで守勢に回った際、相手のクロスやこぼれ球に対するクリア不足",
            "先制された後に主導権を握って能動的に崩すポゼッション精度の課題",
            "連続したハイプレスを受けた際の自陣ビルドアップでのパス引っかけ事故",
        ]

    return in_p, out_p, transitions, vulns


def build_all_team_profiles() -> Dict[str, Any]:
    """全20クラブの戦術プロファイルを構築してJSON保存する."""
    conn = sqlite3.connect(DB_PATH)
    try:
        # 既存プロファイル読み込み（FC東京等のリッチなエビデンスを保護）
        existing_data = {}
        if OUTPUT_PATH.exists():
            try:
                existing_data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            except Exception:
                existing_data = {}

        teams_dict = existing_data.get("teams", {})

        for tid, tname in sorted(TEAM_NAMES.items()):
            mgr = MANAGERS_2026.get(tid, "監督")
            base_f, alt_f, stats = _get_team_formations_and_stats(conn, tid)
            evs = _get_team_claims_evidences(conn, tid, limit=8)

            in_p, out_p, trans, vulns = _generate_team_tactical_texts(
                team_id=tid,
                base_f=base_f,
                stats=stats,
                manager=mgr,
            )

            # FC東京（FCT）など既存で充実しているクラブは既存のin_possession/evidencesを尊重しつつ、フォーメーション・監督・スタッツを同期
            curr = teams_dict.get(tid, {})
            existing_evs = curr.get("evidences", [])

            if curr.get("in_possession") and len(existing_evs) >= 10:
                # 既存が十分充実している場合はベースフォーメーション・監督のみ同期
                curr["team_id"] = tid
                curr["team_name"] = tname
                curr["manager"] = mgr
                curr["base_formation"] = base_f
                curr["alternative_formations"] = alt_f
                teams_dict[tid] = curr
            else:
                combined_evs = existing_evs + [e for e in evs if e not in existing_evs]
                teams_dict[tid] = {
                    "team_id": tid,
                    "team_name": tname,
                    "manager": mgr,
                    "base_formation": base_f,
                    "alternative_formations": alt_f,
                    "in_possession": in_p,
                    "out_of_possession": out_p,
                    "transitions": trans,
                    "structural_vulnerabilities": vulns,
                    "evidences": combined_evs,
                }

        payload = {
            "version": "2.0.0",
            "description": "J-League 2026 Season Team and Manager Tactical Profiles Master (Layer 2) - 100% All 20 Clubs Populated",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "teams": teams_dict,
        }

        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Successfully wrote full tactical profiles for %d clubs to %s", len(teams_dict), OUTPUT_PATH)
        return payload
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = build_all_team_profiles()
    print(f"Generated {len(res['teams'])} team tactical profiles.")

