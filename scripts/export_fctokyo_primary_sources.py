"""
Export Comprehensive Primary Sources Dossier for FC Tokyo (scripts/export_fctokyo_primary_sources.py).

Combines:
1. Curated YouTube Tactical Videos & Segments (Two-tier context-aware scan & phonetic normalized verbatim speech).
2. Official J1 Match Reports, Coach Press Conferences (Matsuhashi), and Player Interviews (All 12 matches).
3. Player Physical, Dominant Foot, and Running Telemetry Specifications (Layer 1 Ground Truth).
"""

from __future__ import annotations

import glob
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"
OUTPUT_PATH = ROOT_DIR / "exports" / "fctokyo_primary_sources.md"
CURATED_SEGMENTS_PATH = ROOT_DIR / "data" / "curated" / "youtube_tactical_segments.json"
MARKDOWN_DIR = ROOT_DIR / "data" / "markdown" / "2026"


def load_curated_youtube_payload() -> Dict[str, Any]:
    """Load curated and normalized YouTube videos and tactical segments."""
    if not CURATED_SEGMENTS_PATH.exists():
        return {"videos": [], "segments": []}
    try:
        with open(CURATED_SEGMENTS_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            return {
                "videos": data.get("videos", []),
                "segments": data.get("segments", []),
            }
    except Exception:
        return {"videos": [], "segments": []}


def load_official_markdown_dossier() -> List[Dict[str, Any]]:
    """Scan data/markdown/2026/ for all FC Tokyo match reports, coach comments, and player quotes."""
    results: List[Dict[str, Any]] = []

    for f_path in sorted(glob.glob(str(MARKDOWN_DIR / "*FCT*.md"))):
        stem = Path(f_path).stem
        try:
            with open(f_path, "r", encoding="utf-8") as fp:
                text = fp.read()
        except Exception:
            continue

        lines = text.splitlines()
        title = lines[0].replace("#", "").strip() if lines else stem

        results.append(
            {
                "file_name": Path(f_path).name,
                "match_code": stem,
                "title": title,
                "full_text": text,
            },
        )

    return results


def load_fct_player_profiles() -> List[Dict[str, Any]]:
    """Query entity_master_players and match stats for FC Tokyo players."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    query = """
        SELECT
            emp.player_id,
            emp.canonical_name,
            emp.position,
            emp.number,
            emp.height_cm,
            emp.weight_kg,
            emp.dominant_foot,
            MAX(CAST(json_extract(pms.raw_stats_json, '$.max_speed_kmh') AS REAL)) as top_speed,
            ROUND(AVG(pms.distance_km), 2) as avg_distance,
            SUM(pms.sprints) as total_sprints,
            ROUND(SUM(pms.cbp_points), 1) as total_cbp,
            SUM(CAST(json_extract(pms.raw_stats_json, '$.spaia.pa_entries') AS INTEGER)) as total_pa_entries
        FROM entity_master_players emp
        LEFT JOIN player_match_stats pms ON emp.player_id = pms.player_id
        WHERE emp.team_id = 'FCT'
        GROUP BY emp.player_id
        ORDER BY emp.number ASC
    """
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()

    players: List[Dict[str, Any]] = []
    for r in rows:
        players.append(
            {
                "name": r["canonical_name"],
                "position": r["position"] or "-",
                "number": r["number"] or 0,
                "height": f"{r['height_cm']}cm" if r["height_cm"] else "-",
                "weight": f"{r['weight_kg']}kg" if r["weight_kg"] else "-",
                "foot": r["dominant_foot"] or "-",
                "top_speed": f"{r['top_speed']} km/h" if r["top_speed"] else "-",
                "avg_distance": f"{r['avg_distance']} km" if r["avg_distance"] else "-",
                "total_sprints": r["total_sprints"] or 0,
                "total_cbp": r["total_cbp"] or 0.0,
                "pa_entries": r["total_pa_entries"] or 0,
            },
        )
    return players


def _render_youtube_section(
    videos: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
) -> List[str]:
    """Render structured YouTube video list, summaries, and verbatim segments."""
    out: List[str] = [
        "## 1. 厳選YouTube戦術解説セグメント（二段階文脈スキャン＆発言整形済み一次ログ）",
        "",
        f"全14チャンネルから収集・粗スキャンを通過した **{len(videos)} 本の動画 / {len(segments)} 件の戦術セグメント** です。",
        "",
    ]

    seg_by_vid: Dict[str, List[Dict[str, Any]]] = {}
    for seg in segments:
        seg_by_vid.setdefault(seg["video_id"], []).append(seg)

    for v_idx, vid_meta in enumerate(videos, 1):
        vid = vid_meta["video_id"]
        v_segs = seg_by_vid.get(vid, [])
        out.append(f"### 1-{v_idx}. [{vid_meta['channel_name']}] {vid_meta['video_title']}")
        out.append(f"- **動画URL**: [{vid_meta['video_url']}]({vid_meta['video_url']})")
        out.append(f"- **戦術的要約**: {vid_meta.get('tactical_summary', '')}")
        out.append("")

        for s_idx, seg in enumerate(v_segs, 1):
            out.append(
                f"#### ({s_idx}) タイム区間 `{seg['time_range']}` | "
                f"トピック: `{seg['primary_topic']}` | [再生リンク]({seg['video_url']})",
            )
            out.append(f"> 「{seg['verbatim_text']}」")
            out.append("")

        out.append("---")
        out.append("")

    return out


def generate_markdown() -> str:
    """Generate professional primary sources markdown with curated segments."""
    yt_payload = load_curated_youtube_payload()
    videos = yt_payload["videos"]
    segments = yt_payload["segments"]
    official_mds = load_official_markdown_dossier()
    player_data = load_fct_player_profiles()

    lines: List[str] = [
        "# FC東京 戦術・監督・選手 一次情報集成 (Primary Sources Dossier)",
        "## Jリーグ戦術分析・観戦ガイドRAG システム 一次データ台帳",
        "",
        "> **【位置づけと品質基準】**: 本文書は、FC東京に関するすべての客観事実（Layer 1）および一次発言（メディア・YouTube戦術解説・J1公式戦評・監督＆選手会見）を集約したマスター台帳です。",
        "> - **二段階文脈キュレーション**: FC東京主題動画（トーキョウ二元論、TOKYO OVERLAY、ダメだ！フットボール、FC東京戦レビュー等）は主語省略箇所を含め戦術議論を網羅抽出し、J1横断動画はFC東京パートを文脈保持して切り出し。",
        "> - **改ざんなき発言整形**: 音声認識の固有名詞誤認識補正と文脈パラグラフ結合のみを行い、AIによる勝手な意訳・作文は一切排除。",
        "",
        "---",
        "",
        "## 目次",
        "1. [厳選YouTube戦術解説セグメント（二段階文脈スキャン＆発言整形済み一次ログ）](#1-厳選youtube戦術解説セグメント二段階文脈スキャン発言整形済み一次ログ)",
        "2. [J1公式戦評・松橋力蔵監督会見・選手インタビュー全文（2026年全12試合）](#2-j1公式戦評松橋力蔵監督会見選手インタビュー全文2026年全12試合)",
        "3. [FC東京所属選手 一次フィジカル・走力・利き足スペック台帳](#3-fc東京所属選手-一次フィジカル走力利き足スペック台帳)",
        "",
        "---",
        "",
    ]

    lines.extend(_render_youtube_section(videos, segments))

    lines.extend(
        [
            "## 2. J1公式戦評・松橋力蔵監督会見・選手インタビュー全文（2026年全12試合）",
            "",
            "Jリーグ公式サイトより取得された公式マッチレポート、松橋力蔵監督の記者会見全文、および選手の試合後生コメントです。",
            "",
        ],
    )

    for match in official_mds:
        lines.append(f"### ■ {match['title']} (`{match['file_name']}`)")
        lines.append("")
        lines.append(match["full_text"])
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.extend(
        [
            "## 3. FC東京所属選手 一次フィジカル・走力・利き足スペック台帳",
            "",
            "公式選手名鑑および全12試合の実測トラッキングデータから集約された客観事実（Layer 1）です。",
            "",
            "| 背番号 | 選手名 | ポジション | 身長 | 体重 | 利き足 | 最高速度 (km/h) | 平均走行 (km) | 総スプリント | 総CBP | PA進入 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ],
    )

    for p in player_data:
        row_str = (
            f"| #{p['number']} | **{p['name']}** | {p['position']} | {p['height']} | "
            f"{p['weight']} | {p['foot']} | {p['top_speed']} | {p['avg_distance']} | "
            f"{p['total_sprints']} | {p['total_cbp']} | {p['pa_entries']} |"
        )
        lines.append(row_str)

    lines.extend(
        [
            "",
            "---",
            "",
            "*Generated deterministically by `scripts/export_fctokyo_primary_sources.py` conforming to TACTICAL_PHILOSOPHY_AND_MANIFESTO.md*",
        ],
    )

    return "\n".join(lines)


def main() -> None:
    import sys

    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = generate_markdown()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Successfully generated FC Tokyo primary sources dossier -> {OUTPUT_PATH}")
    print(f"File size: {len(content):,} characters, {len(content.splitlines()):,} lines.")


if __name__ == "__main__":
    main()
