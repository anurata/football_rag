"""
Official Match Report, Coach Press Conference & Player Interview 7-Layer Ingester
& Multi-Club Primary Sources Dossier Exporter (pipeline/official_discourse_ingester.py).

Processes all 121 official 2026 J1 match markdowns across all 20 J1 clubs
(plus any registered FC Tokyo Emperor's Cup opponents):
  1. Parses official coach press conferences and player interviews without alteration.
  2. Separates statements into Manifesto Layers 1..7 with provenance tags
     (OFFICIAL_PRESS_CONFERENCE / OFFICIAL_PLAYER_INTERVIEW).
  3. Exports per-club Primary Sources Dossiers to exports/clubs/{TEAM_ID}_primary_sources.md.
"""

from __future__ import annotations

import glob
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline.club_entity_registry import ClubEntityRegistry
from pipeline.discourse_layer_decomposer import (
    LAYER_NAMES,
    TacticalDiscourseRepository,
    classify_unit_layer_deterministic,
    compute_claim_id,
    split_into_discourse_units,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_MD_2026_DIR = ROOT_DIR / "data" / "markdown" / "2026"
DEFAULT_CLUBS_EXPORT_DIR = ROOT_DIR / "exports" / "clubs"


def _norm(text: str) -> str:
    """NFKC normalize and strip string."""
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def parse_official_markdown(md_path: Path) -> Dict[str, Any]:
    """
    Parse an official J-League match markdown file into structured sections:
    metadata, match_report, coach_comments, and player_comments.
    """
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = lines[0].lstrip("#").strip() if lines else md_path.stem
    match_url = ""
    matchweek = ""
    score = ""

    for line in lines[:20]:
        if "**対象URL**:" in line:
            match_url = line.split("**対象URL**:", 1)[1].strip()
        elif "**節数**:" in line:
            matchweek = line.split("**節数**:", 1)[1].strip()
        elif "**試合結果**:" in line:
            score = line.split("**試合結果**:", 1)[1].strip()

    section_mode = ""
    cur_speaker_club = ""
    cur_speaker_name = ""
    cur_buf: List[str] = []

    coach_entries: List[Dict[str, str]] = []
    player_entries: List[Dict[str, str]] = []
    report_lines: List[str] = []

    def _flush_speaker() -> None:
        if not cur_speaker_club or not cur_buf:
            return
        # Keep answers, filter interviewer prompt lines starting with －－ or --
        answer_lines = [
            ln.strip()
            for ln in cur_buf
            if ln.strip() and not ln.strip().startswith(("－－", "--", "──"))
        ]
        raw_full = "\n".join(ln.strip() for ln in cur_buf if ln.strip())
        clean_answers = " ".join(answer_lines)
        if not clean_answers:
            return
        payload = {
            "club_name": _norm(cur_speaker_club),
            "speaker_name": _norm(cur_speaker_name),
            "answers_only": _norm(clean_answers),
            "full_qa": raw_full,
        }
        if section_mode == "COACH":
            coach_entries.append(payload)
        elif section_mode == "PLAYER":
            player_entries.append(payload)

    for line in lines:
        if line.startswith("## 【2. 公式マッチレポート】"):
            _flush_speaker()
            section_mode = "REPORT"
            cur_speaker_club, cur_speaker_name, cur_buf = "", "", []
            continue
        if line.startswith("### 【監督コメント】"):
            _flush_speaker()
            section_mode = "COACH"
            cur_speaker_club, cur_speaker_name, cur_buf = "", "", []
            continue
        if line.startswith("### 【選手コメント】"):
            _flush_speaker()
            section_mode = "PLAYER"
            cur_speaker_club, cur_speaker_name, cur_buf = "", "", []
            continue
        if line.startswith("## 【4.") or line.startswith("## 【5."):
            _flush_speaker()
            section_mode = "END"
            cur_speaker_club, cur_speaker_name, cur_buf = "", "", []
            continue

        if section_mode == "REPORT":
            if not line.startswith("#") and line.strip():
                report_lines.append(line.strip())
        elif section_mode in {"COACH", "PLAYER"}:
            if line.startswith("#### 【"):
                _flush_speaker()
                m = re.match(r"^####\s*【([^】]+)】\s*(.+)$", line)
                if m:
                    cur_speaker_club = m.group(1).strip()
                    cur_speaker_name = m.group(2).strip()
                cur_buf = []
            else:
                cur_buf.append(line)

    _flush_speaker()

    return {
        "match_code": md_path.stem,
        "title": _norm(title),
        "match_url": match_url or f"file://{md_path.name}",
        "matchweek": _norm(matchweek),
        "score": _norm(score),
        "match_report": " ".join(report_lines),
        "coach_comments": coach_entries,
        "player_comments": player_entries,
    }


def _build_club_name_lookup(registry: ClubEntityRegistry) -> Dict[str, str]:
    """Map normalized club names/aliases to team_id."""
    lookup: Dict[str, str] = {}
    for club in registry.list_target_clubs():
        tid = club["team_id"]
        lookup[_norm(club["canonical_name"])] = tid
        lookup[_norm(club["short_name"])] = tid
        for al in club.get("aliases", []):
            lookup[_norm(al)] = tid
    return lookup


def ingest_official_markdowns_into_layers(
    registry: ClubEntityRegistry,
    repo: TacticalDiscourseRepository,
    md_dir: Path = DEFAULT_MD_2026_DIR,
) -> Dict[str, int]:
    """
    Decompose all 2026 official coach press conferences and player interviews
    across all 20 J1 clubs into Layers 1..7 and persist into SQLite.
    """
    club_lookup = _build_club_name_lookup(registry)
    now_iso = datetime.now(timezone.utc).isoformat()
    claims_to_insert: List[Dict[str, Any]] = []
    files_count = 0

    for f_path in sorted(glob.glob(str(md_dir / "*.md"))):
        parsed = parse_official_markdown(Path(f_path))
        files_count += 1
        m_code = parsed["match_code"]
        m_url = parsed["match_url"]
        m_title = f"{parsed['matchweek']} {parsed['title']}"

        # 1. Coach press conferences
        for idx, c_item in enumerate(parsed["coach_comments"]):
            tid = club_lookup.get(c_item["club_name"])
            if not tid:
                continue
            coach_name = c_item["speaker_name"]
            seg_id = f"OFF_COACH_{m_code}_{tid}_{idx}"
            for unit in split_into_discourse_units(c_item["answers_only"]):
                layer = classify_unit_layer_deterministic(unit)
                claims_to_insert.append(
                    {
                        "claim_id": compute_claim_id(seg_id, tid, layer, unit),
                        "segment_id": seg_id,
                        "video_id": m_code,
                        "channel_name": "Jリーグ公式監督会見",
                        "video_title": m_title,
                        "video_url": m_url,
                        "time_range": parsed["matchweek"] or "試合後会見",
                        "team_id": tid,
                        "manager_mentioned": coach_name,
                        "players_mentioned": [],
                        "truth_layer": layer,
                        "layer_name": LAYER_NAMES[layer],
                        "source_reliability": "OFFICIAL_PRESS_CONFERENCE",
                        "statement_text": unit,
                        "original_quote": unit,
                        "extraction_method": "official_verbatim_split",
                        "created_at": now_iso,
                    },
                )

        # 2. Player interviews
        for idx, p_item in enumerate(parsed["player_comments"]):
            tid = club_lookup.get(p_item["club_name"])
            if not tid:
                continue
            player_name = p_item["speaker_name"]
            seg_id = f"OFF_PLAYER_{m_code}_{tid}_{idx}"
            for unit in split_into_discourse_units(p_item["answers_only"]):
                layer = classify_unit_layer_deterministic(unit)
                claims_to_insert.append(
                    {
                        "claim_id": compute_claim_id(seg_id, tid, layer, unit),
                        "segment_id": seg_id,
                        "video_id": m_code,
                        "channel_name": "Jリーグ公式選手コメント",
                        "video_title": m_title,
                        "video_url": m_url,
                        "time_range": parsed["matchweek"] or "試合後取材",
                        "team_id": tid,
                        "manager_mentioned": "",
                        "players_mentioned": [player_name],
                        "truth_layer": layer,
                        "layer_name": LAYER_NAMES[layer],
                        "source_reliability": "OFFICIAL_PLAYER_INTERVIEW",
                        "statement_text": unit,
                        "original_quote": unit,
                        "extraction_method": "official_verbatim_split",
                        "created_at": now_iso,
                    },
                )

    inserted = repo.upsert_claims(claims_to_insert)
    return {"markdown_files": files_count, "official_claims_upserted": inserted}


def _query_club_player_specs(db_path: Path, team_id: str) -> List[Dict[str, Any]]:
    """Query physical, foot, speed, and CBP telemetry for any club's roster."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                emp.canonical_name,
                emp.position,
                emp.number,
                emp.height_cm,
                emp.weight_kg,
                emp.dominant_foot,
                MAX(CAST(json_extract(pms.raw_stats_json, '$.max_speed_kmh') AS REAL)) AS top_speed,
                ROUND(AVG(pms.distance_km), 2) AS avg_distance,
                COALESCE(SUM(pms.sprints), 0) AS total_sprints,
                ROUND(COALESCE(SUM(pms.cbp_points), 0.0), 1) AS total_cbp
            FROM entity_master_players emp
            LEFT JOIN player_match_stats pms ON emp.player_id = pms.player_id
            WHERE emp.team_id = ?
            GROUP BY emp.player_id
            ORDER BY emp.number ASC
            """,
            (team_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def export_all_clubs_primary_dossiers(
    registry: ClubEntityRegistry,
    repo: TacticalDiscourseRepository,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_CLUBS_EXPORT_DIR,
) -> List[Path]:
    """
    Export standardized 7-Layer Primary Sources Dossiers for all target clubs
    (J1 20 clubs + enabled FC Tokyo Emperor's Cup opponents).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_files: List[Path] = []

    layer_jp_titles = {
        1: "Layer 1: 客観事実・数値記録 (Hard Facts)",
        2: "Layer 2: 先人の知見・戦術原則 (Tactical Heuristics)",
        3: "Layer 3: 事象説明・因果解明 (Grounded Explanation)",
        4: "Layer 4: 仮説構築・指揮官意図推論 (Hypothesis Generation)",
        5: "Layer 5: 物語とナラティブ (Narrative Drama)",
        6: "Layer 6: 大胆な未来予測 (Bold Forecasting)",
        7: "Layer 7: 願望とロマン (Aspiration & Romance)",
    }

    for club in registry.list_target_clubs():
        tid = club["team_id"]
        cname = club["canonical_name"]
        mgr = club["current_manager"]
        prev_mgrs = club.get("previous_managers_2026", [])
        mgr_line = f"{mgr}" + (f"（前任: {', '.join(prev_mgrs)}）" if prev_mgrs else "")

        lines: List[str] = [
            f"# {cname} ({tid}) 戦術・監督・選手 7層分離一次情報台帳",
            "",
            f"- **対象区分**: `{club.get('competition_scope', 'J1_2026')}`",
            f"- **2026現監督**: **{mgr_line}**",
            f"- **主力選手 (CBP上位)**: {', '.join(club.get('key_players', [])[:12]) or '（データ登録待ち）'}",
            "",
            "---",
            "",
            "## 1. 『虚実のグラデーション（Layer 1〜7）』分離格納済み言説",
            "",
        ]

        for layer_num in range(1, 8):
            claims = repo.query_claims(team_id=tid, layers=[layer_num], limit=25)
            lines.append(f"### {layer_jp_titles[layer_num]} （抽出数: {len(claims)}件表示）")
            if not claims:
                lines.append("- *（該当言説なし）*")
                lines.append("")
                continue

            for c in claims:
                src_badge = c["source_reliability"]
                speaker = c["manager_mentioned"] or ", ".join(c["players_mentioned"]) or c["channel_name"]
                lines.append(
                    f"- **[{src_badge} | {c['channel_name']} | {c['time_range']}] ({speaker})**: "
                    f"{c['statement_text']} ([原典]({c['video_url']}))",
                )
            lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 2. 所属選手 フィジカル・利き足・トラッキング台帳 (Layer 1 Ground Truth)",
                "",
                "| 背番号 | 選手名 | Pos | 身長 | 体重 | 利き足 | 最高速度 | 平均走行 | 総スプリント | 総CBP |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ],
        )

        roster = _query_club_player_specs(db_path, tid)
        for r in roster:
            h_str = f"{r['height_cm']}cm" if r["height_cm"] else "-"
            w_str = f"{r['weight_kg']}kg" if r["weight_kg"] else "-"
            spd_str = f"{r['top_speed']} km/h" if r["top_speed"] else "-"
            dist_str = f"{r['avg_distance']} km" if r["avg_distance"] else "-"
            lines.append(
                f"| #{r['number'] or 0} | **{r['canonical_name']}** | {r['position'] or '-'} | "
                f"{h_str} | {w_str} | {r['dominant_foot'] or '-'} | {spd_str} | "
                f"{dist_str} | {r['total_sprints']} | {r['total_cbp']} |",
            )

        out_file = output_dir / f"{tid}_primary_sources.md"
        out_file.write_text("\n".join(lines), encoding="utf-8")
        generated_files.append(out_file)

    return generated_files

