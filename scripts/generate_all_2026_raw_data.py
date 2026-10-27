"""
Batch Generator for 2026 J-League Season Raw Data (scripts/generate_all_2026_raw_data.py).
Generates comprehensive raw JSON datasets under:
- data/raw/football_lab/{game_id}.json
- data/raw/spaia/{game_id}_comments.json
- data/raw/spaia/{game_id}_player_stats.json
- data/raw/yahoo/{game_id}_stats.json
- data/raw/yahoo/{game_id}_text.json
based on data/markdown/2026/*.md and data/football.db.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from agent.objective_profiler import resolve_team_name, TEAM_NAME_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_all_2026_raw_data")


def parse_markdown_metadata(md_text: str) -> Dict[str, Any]:
    """Parse header details from match markdown."""
    info = {}
    m_url = re.search(r"\*\*対象URL\*\*:\s*(\S+)", md_text)
    if m_url:
        info["url"] = m_url.group(1)

    m_mw = re.search(r"\*\*節数\*\*:\s*第?(\d+)節?", md_text)
    if m_mw:
        info["matchweek"] = int(m_mw.group(1))

    m_date = re.search(r"\*\*開催日時\*\*:\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})", md_text)
    if m_date:
        info["date"] = m_date.group(1).replace("/", "-")

    m_stad = re.search(r"\*\*スタジアム\*\*:\s*(.+)", md_text)
    if m_stad:
        info["stadium"] = m_stad.group(1).strip()

    m_att = re.search(r"\*\*入場者数\*\*:\s*([\d,]+)人?", md_text)
    if m_att:
        info["attendance"] = int(m_att.group(1).replace(",", ""))

    m_clim = re.search(r"\*\*天候・気候\*\*:\s*(.+)", md_text)
    if m_clim:
        info["climate"] = m_clim.group(1).strip()

    m_res = re.search(r"\*\*試合結果\*\*:\s*(\d+)\s*[-−]\s*(\d+)", md_text)
    if m_res:
        info["home_score"] = int(m_res.group(1))
        info["away_score"] = int(m_res.group(2))

    m_sc = re.search(r"\*\*得点経過\*\*:\s*(.+)", md_text)
    if m_sc:
        info["scorers_text"] = m_sc.group(1).strip()

    # Match report
    m_rep = re.search(r"## 【2\. 公式マッチレポート】\s*\n([\s\S]*?)(?=\n## 【3\.|\Z)", md_text)
    if m_rep:
        info["report_text"] = m_rep.group(1).strip()

    return info


def parse_markdown_stats(md_text: str) -> Dict[str, Dict[str, Any]]:
    """Parse stats table from markdown."""
    stats = {"home": {}, "away": {}}
    tbl = re.search(r"### 【チームスタッツ比較】[\s\S]*?\n\n", md_text)
    if not tbl:
        return stats

    for line in tbl.group(0).splitlines():
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3 and parts[0] != "指標":
                label = parts[0]
                h_v = parts[1]
                a_v = parts[2]
                if "シュート数" in label and "枠内" not in label:
                    stats["home"]["shots"] = _safe_int(h_v)
                    stats["away"]["shots"] = _safe_int(a_v)
                elif "枠内シュート数" in label:
                    stats["home"]["shots_on_target"] = _safe_int(h_v)
                    stats["away"]["shots_on_target"] = _safe_int(a_v)
                elif "ボール支配率" in label:
                    stats["home"]["possession"] = _safe_float(h_v.replace("%", ""))
                    stats["away"]["possession"] = _safe_float(a_v.replace("%", ""))
                elif "パス成功率" in label:
                    stats["home"]["pass_success"] = _safe_float(h_v.replace("%", ""))
                    stats["away"]["pass_success"] = _safe_float(a_v.replace("%", ""))
                elif "走行距離" in label:
                    stats["home"]["distance_km"] = _safe_float(h_v.replace("km", ""))
                    stats["away"]["distance_km"] = _safe_float(a_v.replace("km", ""))
                elif "スプリント" in label:
                    stats["home"]["sprints"] = _safe_int(h_v)
                    stats["away"]["sprints"] = _safe_int(a_v)
                elif "コーナーキック" in label:
                    stats["home"]["corner_kicks"] = _safe_int(h_v)
                    stats["away"]["corner_kicks"] = _safe_int(a_v)
                elif "フリーキック" in label:
                    stats["home"]["free_kicks"] = _safe_int(h_v)
                    stats["away"]["free_kicks"] = _safe_int(a_v)
                elif "オフサイド数" in label:
                    stats["home"]["offsides"] = _safe_int(h_v)
                    stats["away"]["offsides"] = _safe_int(a_v)
                elif "警告・退場" in label:
                    stats["home"]["cards"] = h_v
                    stats["away"]["cards"] = a_v
    return stats


def parse_markdown_comments(md_text: str) -> Dict[str, Any]:
    """Parse manager and player interviews."""
    comments = {
        "home_coach": {"name": "", "comment": ""},
        "away_coach": {"name": "", "comment": ""},
        "home_players": [],
        "away_players": [],
    }

    # Coaches
    m_hc = re.search(r"#### 【([^】]+)】([^\n]+?)\s*\n([\s\S]*?)(?=\n####|\n###|\Z)", md_text)
    if m_hc:
        comments["home_coach"] = {
            "team_label": m_hc.group(1).strip(),
            "name": m_hc.group(2).strip(),
            "comment": m_hc.group(3).strip(),
        }

    # Find second coach
    coach_matches = list(re.finditer(r"#### 【([^】]+)】([^\n]+?)\s*\n([\s\S]*?)(?=\n#### 【|\n### 【選手コメント】|\Z)", md_text))
    if len(coach_matches) >= 2:
        comments["away_coach"] = {
            "team_label": coach_matches[1].group(1).strip(),
            "name": coach_matches[1].group(2).strip(),
            "comment": coach_matches[1].group(3).strip(),
        }

    # Player comments
    p_sec = re.search(r"### 【選手コメント】\s*\n([\s\S]*?)(?=\n## |\Z)", md_text)
    if p_sec:
        p_matches = list(re.finditer(r"#### 【([^】]+)】([^\n]+?)\s*\n([\s\S]*?)(?=\n#### 【|\Z)", p_sec.group(1)))
        for pm in p_matches:
            item = {
                "team_label": pm.group(1).strip(),
                "player_name": pm.group(2).strip(),
                "comment": pm.group(3).strip(),
            }
            comments["home_players"].append(item)

    return comments


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        clean = re.sub(r"[^0-9]", "", str(val))
        return int(clean) if clean else default
    except Exception:
        return default


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        clean = re.sub(r"[^0-9.]", "", str(val))
        return float(clean) if clean else default
    except Exception:
        return default


def main() -> None:
    """Generate all 2026 raw files from markdown and database."""
    md_dir = ROOT_DIR / "data" / "markdown" / "2026"
    raw_flab_dir = ROOT_DIR / "data" / "raw" / "football_lab"
    raw_spaia_dir = ROOT_DIR / "data" / "raw" / "spaia"
    raw_yahoo_dir = ROOT_DIR / "data" / "raw" / "yahoo"

    raw_flab_dir.mkdir(parents=True, exist_ok=True)
    raw_spaia_dir.mkdir(parents=True, exist_ok=True)
    raw_yahoo_dir.mkdir(parents=True, exist_ok=True)

    md_files = sorted(list(md_dir.glob("*.md")))
    logger.info("Found %d markdown match files in %s", len(md_files), md_dir)

    success_count = 0

    for md_path in md_files:
        match_id = md_path.stem
        # e.g. 20260808_FCT_ZEL
        parts = match_id.split("_")
        if len(parts) >= 3:
            date_str = parts[0]
            home_id = parts[1]
            away_id = parts[2]
        else:
            date_str = "20261025"
            home_id = "HOME"
            away_id = "AWAY"

        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()

        meta = parse_markdown_metadata(md_text)
        stats = parse_markdown_stats(md_text)
        comments = parse_markdown_comments(md_text)

        home_name = resolve_team_name(home_id)
        away_name = resolve_team_name(away_id)
        h_score = meta.get("home_score", 0)
        a_score = meta.get("away_score", 0)

        # ----------------------------------------------------------------------
        # 1. Football LAB raw JSON
        # ----------------------------------------------------------------------
        flab_json_path = raw_flab_dir / f"{match_id}.json"
        flab_data = {
            "match_id": match_id,
            "date": meta.get("date", f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"),
            "season": 2026,
            "matchweek": meta.get("matchweek", 1),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "home_team_name": home_name,
            "away_team_name": away_name,
            "score": f"{h_score} - {a_score}",
            "stadium": meta.get("stadium", ""),
            "attendance": meta.get("attendance", 0),
            "climate": meta.get("climate", ""),
            "data": {
                "title": f"{home_name} vs {away_name} 2026/27 マッチレポート",
                "url": meta.get("url", ""),
                "report_text": meta.get("report_text", ""),
                "team_stats": stats,
                "scorers_text": meta.get("scorers_text", ""),
                "coaches": {
                    "home": comments.get("home_coach", {}),
                    "away": comments.get("away_coach", {}),
                },
                "player_comments": comments.get("home_players", []),
            },
        }
        with open(flab_json_path, "w", encoding="utf-8") as f:
            json.dump(flab_data, f, ensure_ascii=False, indent=2)

        # ----------------------------------------------------------------------
        # 2. SPAIA comments & player stats raw JSON
        # ----------------------------------------------------------------------
        spaia_comments_path = raw_spaia_dir / f"{match_id}_comments.json"
        spaia_comments_data = {
            "match_id": match_id,
            "home_team": home_name,
            "away_team": away_name,
            "home_coach": comments.get("home_coach", {}),
            "away_coach": comments.get("away_coach", {}),
            "player_interviews": comments.get("home_players", []),
            "official_summary": meta.get("report_text", ""),
        }
        with open(spaia_comments_path, "w", encoding="utf-8") as f:
            json.dump(spaia_comments_data, f, ensure_ascii=False, indent=2)

        spaia_player_path = raw_spaia_dir / f"{match_id}_player_stats.json"
        spaia_player_data = {
            "match_id": match_id,
            "stats_summary": stats,
            "scorers": meta.get("scorers_text", ""),
        }
        with open(spaia_player_path, "w", encoding="utf-8") as f:
            json.dump(spaia_player_data, f, ensure_ascii=False, indent=2)

        # ----------------------------------------------------------------------
        # 3. Yahoo stats & text raw JSON
        # ----------------------------------------------------------------------
        yahoo_stats_path = raw_yahoo_dir / f"{match_id}_stats.json"
        yahoo_stats_data = {
            "match_id": match_id,
            "home_team": home_name,
            "away_team": away_name,
            "score": {"home": h_score, "away": a_score},
            "team_stats": stats,
            "venue": meta.get("stadium", ""),
            "weather": meta.get("climate", ""),
            "spectators": meta.get("attendance", 0),
        }
        with open(yahoo_stats_path, "w", encoding="utf-8") as f:
            json.dump(yahoo_stats_data, f, ensure_ascii=False, indent=2)

        yahoo_text_path = raw_yahoo_dir / f"{match_id}_text.json"
        yahoo_text_data = {
            "match_id": match_id,
            "headline": f"【J1第{meta.get('matchweek', 1)}節】{home_name} vs {away_name}",
            "text_report": meta.get("report_text", ""),
            "key_events": meta.get("scorers_text", ""),
        }
        with open(yahoo_text_path, "w", encoding="utf-8") as f:
            json.dump(yahoo_text_data, f, ensure_ascii=False, indent=2)

        success_count += 1

    logger.info(
        "Successfully generated raw datasets for %d matches under data/raw/ (flab, spaia, yahoo)!",
        success_count,
    )


if __name__ == "__main__":
    main()
