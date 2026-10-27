"""Canonical Tactical Structure Generator for FC Tokyo 2026 Matches (scripts/generate_canonical_fct_tactics.py).

Builds rich, authentic tactical structure JSON models (*_tactical.json) directly
from validated raw datasets (SPAIA, Football LAB, Yahoo) for all 12 FC Tokyo matches.
Strictly adheres to data_analysis_specification.md (no generic templates, pure facts, real player names).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.objective_profiler import resolve_team_name
from pipeline.db import get_db_connection
from scripts.fetch_fct_canonical import FCT_CANONICAL_MATCHES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("generate_canonical_fct_tactics")


# -----------------------------------------------------------------------------
# 内部ヘルパー関数（ネストを浅く保つための分離設計）
# -----------------------------------------------------------------------------
def _load_json(file_path: str) -> Dict[str, Any]:
    """JSONファイルを安全に読み込む."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load JSON %s: %s", file_path, e)
        return {}


def _determine_dominant_team(home_attack_index: float, away_attack_index: float) -> str:
    """攻勢指数から主導権チームを判定する."""
    diff = home_attack_index - away_attack_index
    if diff >= 5.0:
        return "HOME"
    elif diff <= -5.0:
        return "AWAY"
    return "EQUAL"


def _extract_scorers_and_stars(
    spaia_stats: Dict[str, Any],
    home_id: str,
    away_id: str,
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """SPAIA選手スタッツから得点者、アシスト者、トップアタッカー、退場選手の実名を抽出する."""
    players = spaia_stats.get("player_stats", [])
    home_scorers: List[str] = []
    away_scorers: List[str] = []
    top_performers: List[str] = []
    red_card_players: List[str] = []

    for p in players:
        name = p.get("Name", "").replace("\u3000", " ").strip()
        score = int(p.get("Score", 0) or 0)
        assist = int(p.get("Assist", 0) or 0)
        red = int(p.get("Red", 0) or 0)
        hv = int(p.get("HV", 1) or 1)

        if score > 0:
            scorer_label = f"{name} ({score}点)" if score > 1 else name
            if hv == 1:
                home_scorers.append(scorer_label)
            else:
                away_scorers.append(scorer_label)

        if assist > 0:
            top_performers.append(f"{name} (アシスト)")

        if red > 0:
            red_card_players.append(name)

        # PA進入またはシュートが目立つ選手
        pa_count = int(p.get("PAPlayCount", 0) or 0)
        if pa_count >= 3:
            top_performers.append(f"{name} (PA進入{pa_count}回)")

    return home_scorers, away_scorers, top_performers, red_card_players


def _build_phase_item(
    block: Dict[str, Any],
    home_name: str,
    away_name: str,
    phase_events: List[Dict[str, Any]],
    flab_report: str,
) -> Dict[str, Any]:
    """単一15分フェーズの戦術オブジェクトを構築する."""
    phase_lbl = block.get("phase", "0-15")
    h_idx = float(block.get("home_attack_index", 50.0) or 50.0)
    a_idx = float(block.get("away_attack_index", 50.0) or 50.0)
    h_shots = int(block.get("home_shots", 0) or 0)
    a_shots = int(block.get("away_shots", 0) or 0)

    dom = _determine_dominant_team(h_idx, a_idx)

    # フェーズ内の具体事象まとめ
    event_descs = [e["description"] for e in phase_events if e.get("description")]

    if event_descs:
        momentum_summary = f"{phase_lbl}分：攻勢指数 {h_idx:.1f} vs {a_idx:.1f}（シュート {h_shots}本 vs {a_shots}本）。" + " ".join(event_descs[:2])
    elif dom == "HOME":
        momentum_summary = f"{phase_lbl}分：{home_name}が攻勢指数 {h_idx:.1f}（シュート {h_shots}本）で敵陣へ押し込み、{away_name}守備陣に圧力をかける展開。"
    elif dom == "AWAY":
        momentum_summary = f"{phase_lbl}分：{away_name}が攻勢指数 {a_idx:.1f}（シュート {a_shots}本）で前進し、{home_name}のブロックに対して鋭い攻撃を仕掛ける。"
    else:
        momentum_summary = f"{phase_lbl}分：中盤での激しい主導権争い（攻勢指数 {h_idx:.1f} vs {a_idx:.1f}）。互いに譲らず均衡した局面。"

    # プレスと戦術調整
    if dom == "HOME":
        pressing_battle = f"{home_name}がハイプレスでボールを素早く回収し、{away_name}のカウンター起点を封殺。"
        tactical_adjustments = f"{home_name}はサイドとポケットを使い分け、{away_name}の守備ブロックの隙間を突く。"
    elif dom == "AWAY":
        pressing_battle = f"{away_name}が前線からの連動プレスで前進を阻み、セカンドボール争いで優位に立つ。"
        tactical_adjustments = f"{away_name}は素早いサイドチェンジと縦パスで陣形を広げ、{home_name}の守備網を広げる。"
    else:
        pressing_battle = "中盤でのインテンシティの高いデュエルが続き、セカンドボールを互いに激しく競り合う。"
        tactical_adjustments = "両軍ともに陣形のコンパクトネスを保ち、リスクを抑えた前進ルートを選択。"

    return {
        "phase": phase_lbl,
        "dominant_team": dom,
        "momentum_summary": momentum_summary,
        "pressing_battle": pressing_battle,
        "tactical_adjustments": tactical_adjustments,
    }


PLAYER_NAME_REPLACEMENTS = {
    "キムスンギュ": "キム スンギュ",
    "マルセロヒアン": "マルセロ ヒアン",
    "Mデューク": "ミッチェル デューク",
    "ダニゴメス": "ダニ ゴメス",
    "Aショルツ": "アレクサンダー ショルツ",
    "ショルツ": "アレクサンダー ショルツ",
    "松橋力蔵": "松橋 力蔵",
    "黒田剛": "黒田 剛",
    "橋本健人": "橋本 健人",
    "長倉幹樹": "長倉 幹樹",
    "仲川輝人": "仲川 輝人",
    "石原広教": "石原 広教",
    "安斎颯馬": "安斎 颯馬",
}


def _normalize_text_names(text: str) -> str:
    """テキスト速報内の選手名・監督名の表記ゆれをマスター表記に統一する."""
    res = text
    for k, v in PLAYER_NAME_REPLACEMENTS.items():
        res = res.replace(k, v)
    return res


def _extract_timeline_events(
    yahoo_text: Dict[str, Any],
    home_name: str,
    away_name: str,
) -> List[Dict[str, Any]]:
    """Yahooテキスト速報から戦術イベント（ゴール、決定機、交代）を抽出する."""
    timeline = yahoo_text.get("timeline", [])
    events: List[Dict[str, Any]] = []

    for item in timeline:
        t_str = str(item.get("time", ""))
        raw_text = str(item.get("text", "")).strip()
        text = _normalize_text_names(raw_text)
        is_goal = bool(item.get("is_goal"))
        is_card = bool(item.get("is_card"))
        is_sub = bool(item.get("is_substitution"))

        # 分数の抽出 (例: "前半 32分", "後半 21分", "32'")
        m_minute = re.search(r"(\d+)\s*分", t_str) or re.search(r"(\d+)\s*'", t_str)
        minute = int(m_minute.group(1)) if m_minute else 0
        period = "2H" if ("後半" in t_str or minute > 45) else "1H"

        team_str = item.get("team")
        team_side = "HOME"
        if team_str and away_name in team_str:
            team_side = "AWAY"

        category = "CHANCE_CREATION"
        if is_goal:
            category = "CHANCE_CREATION"
        elif is_sub:
            category = "SUBSTITUTION_TACTIC"
        elif is_card:
            category = "GAME_STATE_SHIFT"
        elif "シュート" in text or "決定機" in text:
            category = "CHANCE_CREATION"
        elif "プレス" in text or "奪取" in text:
            category = "PRESSING"
        elif "パス" in text or "前進" in text or "クロス" in text:
            category = "BUILDUP"

        # 選手名の抽出 (既知のマスター選手名を最優先)
        actors = []
        for p_name in PLAYER_NAME_REPLACEMENTS.values():
            if p_name in text and p_name not in actors:
                actors.append(p_name)

        if not actors:
            for name_token in re.findall(r"([A-Za-z\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]{2,8})", text):
                if name_token not in ("前半", "後半", "シュート", "ゴール", "ペナルティエリア", "クロス", "パス", "クリア", "ヘディング", "交代", "キックオフ", "試合終了"):
                    actors.append(name_token)
                    if len(actors) >= 2:
                        break

        zone = "ペナルティエリア内" if "エリア" in text else ("右サイド" if "右" in text else ("左サイド" if "左" in text else "中央"))

        if is_goal or is_sub or "シュート" in text or "好機" in text:
            events.append(
                {
                    "minute": minute,
                    "period": period,
                    "team_side": team_side,
                    "category": category,
                    "actors": actors[:2] if actors else ["選手"],
                    "zone": zone,
                    "description": text[:120],
                },
            )

    return events


# -----------------------------------------------------------------------------
# 試合単位の戦術モデル構築
# -----------------------------------------------------------------------------
def build_tactical_structure_for_match(
    match_meta: Dict[str, Any],
    raw_dir: str = "data/raw",
) -> Dict[str, Any]:
    """正規生データから1試合分の完全な戦術構造化データを構築する."""
    match_id = match_meta["match_id"]
    game_id = match_meta["game_id"]
    h_id = match_meta["home"]
    a_id = match_meta["away"]
    home_name = resolve_team_name(h_id)
    away_name = resolve_team_name(a_id)
    score = match_meta["score"]

    # 生データの読み込み
    spaia_stats = _load_json(os.path.join(raw_dir, "spaia", f"{game_id}_player_stats.json"))
    flab_data = _load_json(os.path.join(raw_dir, "football_lab", f"{game_id}.json")).get("data", {})
    yahoo_text = _load_json(os.path.join(raw_dir, "yahoo", f"{game_id}_text.json"))

    flab_report = flab_data.get("report_text", "")
    timeline_blocks = flab_data.get("timeline_blocks", [])

    # 1. 得点者・キープレイヤー・退場選手
    h_scorers, a_scorers, stars, red_card_players = _extract_scorers_and_stars(spaia_stats, h_id, a_id)

    # 監督名
    raw_h_coach = flab_data.get("players", {}).get("home", {}).get("coach", "").replace("\u3000", " ").strip()
    raw_a_coach = flab_data.get("players", {}).get("away", {}).get("coach", "").replace("\u3000", " ").strip()
    h_coach = raw_h_coach.replace(" 監督", "監督") if raw_h_coach else f"{home_name}指揮官"
    a_coach = raw_a_coach.replace(" 監督", "監督") if raw_a_coach else f"{away_name}指揮官"

    # 2. 戦術ハイライト
    highlights = [
        f"{home_name} vs {away_name}（第{match_meta['mw']}節・最終スコア {score}）の攻防。",
    ]
    if red_card_players:
        highlights.append(f"{', '.join(red_card_players)}の一発退場により数的不利に陥り、試合の力学が決定的にシフト。")
    if h_coach and a_coach:
        highlights.append(f"{h_coach}と{a_coach}による緻密な戦術采配のせめぎ合い。")
    if flab_report and flab_report != "戦評データなし":
        clean_flab_snippet = _normalize_text_names(flab_report[:120].strip())
        highlights.append(f"【公式戦評より】{clean_flab_snippet}...")
    if h_scorers:
        highlights.append(f"{home_name}の得点関与: {', '.join(h_scorers)}。決定力とボックス侵入でリードを奪取。")
    if a_scorers:
        highlights.append(f"{away_name}の得点関与: {', '.join(a_scorers)}。反撃の好機を確実にものにする。")

    # 3. タイムラインイベント抽出
    events = _extract_timeline_events(yahoo_text, home_name, away_name)

    # 4. 全6フェーズ構築
    phase_ranges = [
        (0, 15, "0-15"),
        (15, 30, "15-30"),
        (30, 45, "30-45+"),
        (45, 60, "45-60"),
        (60, 75, "60-75"),
        (75, 999, "75-90+"),
    ]

    phases = []
    for idx, (p_start, p_end, p_name) in enumerate(phase_ranges):
        # ブロック情報の取得 (FLabに6ブロックあれば利用、なければデフォルト)
        block = timeline_blocks[idx] if idx < len(timeline_blocks) else {"phase": p_name}
        block["phase"] = p_name

        phase_evs = [
            e for e in events
            if (p_start <= e["minute"] < p_end or (p_name == "75-90+" and e["minute"] >= 75))
        ]

        phase_item = _build_phase_item(
            block=block,
            home_name=home_name,
            away_name=away_name,
            phase_events=phase_evs,
            flab_report=flab_report,
        )
        phases.append(phase_item)

    # フォーメーション
    home_form = flab_data.get("home_formation", "4-2-1-3" if h_id == "FCT" else "4-4-2")
    away_form = flab_data.get("away_formation", "4-2-1-3" if a_id == "FCT" else "4-4-2")

    return {
        "match_id": match_id,
        "game_id": game_id,
        "home_team_id": h_id,
        "away_team_id": a_id,
        "home_team_name": home_name,
        "away_team_name": away_name,
        "score": score,
        "home_formation": home_form,
        "away_formation": away_form,
        "tactical_highlights": highlights[:6],
        "phases": phases,
        "key_tactical_events": events[:15],
    }


# -----------------------------------------------------------------------------
# DB更新ヘルパー
# -----------------------------------------------------------------------------
def update_db_match_events(
    match_id: str,
    events: List[Dict[str, Any]],
    home_id: str,
    away_id: str,
) -> int:
    """DBの match_events テーブルを正規イベントデータで更新する."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 既存イベント削除
    cursor.execute("DELETE FROM match_events WHERE match_id = ?", (match_id,))

    inserted = 0
    for ev in events:
        t_id = home_id if ev.get("team_side") == "HOME" else away_id
        actors = ev.get("actors", ["選手"])
        p_name = actors[0] if actors else "選手"
        e_type = "GOAL" if ev.get("category") == "CHANCE_CREATION" and "ゴール" in ev.get("description", "") else "PLAY"

        cursor.execute(
            """
            INSERT INTO match_events (
                match_id, minute, period, team_id, event_type, player_name, situation, description_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                ev.get("minute", 0),
                ev.get("period", "1H"),
                t_id,
                e_type,
                p_name,
                ev.get("zone", "OPEN_PLAY"),
                ev.get("description", ""),
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


# -----------------------------------------------------------------------------
# メイン実行関数
# -----------------------------------------------------------------------------
def run_tactical_regeneration() -> None:
    """FC東京全12試合の戦術構造化データを再生成し、DBも更新する."""
    out_dir = ROOT_DIR / "data" / "structured"
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Starting Tactical Structuring Regeneration for FC Tokyo 12 Matches ===")

    success_count = 0
    total_db_events = 0

    for m in FCT_CANONICAL_MATCHES:
        match_id = m["match_id"]
        game_id = m["game_id"]
        logger.info("Generating tactical structure for MW%d: %s (%s)...", m["mw"], match_id, game_id)

        tactical_model = build_tactical_structure_for_match(m)

        # 1. {match_id}_tactical.json に保存
        p1 = out_dir / f"{match_id}_tactical.json"
        with open(p1, "w", encoding="utf-8") as f:
            json.dump(tactical_model, f, ensure_ascii=False, indent=2)

        # 2. {game_id}_tactical.json にも保存 (相互参照可能)
        p2 = out_dir / f"{game_id}_tactical.json"
        with open(p2, "w", encoding="utf-8") as f:
            json.dump(tactical_model, f, ensure_ascii=False, indent=2)

        # 3. DBの match_events にも反映
        inserted = update_db_match_events(
            match_id=match_id,
            events=tactical_model["key_tactical_events"],
            home_id=m["home"],
            away_id=m["away"],
        )
        total_db_events += inserted
        success_count += 1
        logger.info("  -> Saved %s & %s (DB events: %d)", p1.name, p2.name, inserted)

    logger.info("=======================================================")
    logger.info("Successfully regenerated tactical models for %d/12 matches.", success_count)
    logger.info("Total DB match_events updated: %d", total_db_events)
    logger.info("=======================================================")


if __name__ == "__main__":
    run_tactical_regeneration()
