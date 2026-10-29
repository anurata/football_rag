"""
Multi-Club Entity Registry for J1 (All 20 Clubs) + FC Tokyo Emperor's Cup Opponents
(pipeline/club_entity_registry.py).

Deterministically builds 2026/27 ground-truth dictionaries of:
- Club canonical names, short names, and aliases (from SQLite entity_master_teams)
- Active 2026 managers & mid-season manager changes (from data/markdown/2026/*.md)
- Key & active players per club (from SQLite entity_master_players & player_match_stats)
- Dynamic FC Tokyo Emperor's Cup opponents (J2/J3/JFL/University teams via config or CLI)
"""

from __future__ import annotations

import glob
import json
import logging
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("club_entity_registry")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_MD_2026_DIR = ROOT_DIR / "data" / "markdown" / "2026"
DEFAULT_TARGET_CONFIG_PATH = ROOT_DIR / "config" / "target_clubs_config.json"
DEFAULT_REGISTRY_EXPORT_PATH = ROOT_DIR / "knowledge" / "club_entity_registry_2026.json"


def _norm_nfkc(text: str) -> str:
    """Normalize text with Unicode NFKC and strip whitespace."""
    return unicodedata.normalize("NFKC", str(text or "")).strip()


AMBIGUOUS_SHARED_TOKENS: Set[str] = {
    "選手",
    "監督",
    "東京",
    "大阪",
    "横浜",
    "キム",
    "ヤン",
    "パク",
    "チョ",
    "ソン",
    "レオ",
    "マテウス",
    "ジョルディ",
    "ディエゴ",
    "ブルーノ",
    "ラファエル",
    "マルコス",
    "ルーカス",
}


def _extract_surname_tokens(full_name: str) -> List[str]:
    """
    Extract useful distinctive name tokens (full name without space + non-ambiguous parts >= 2 chars)
    for transcript matching while avoiding cross-club false positives.
    """
    norm = _norm_nfkc(full_name)
    if not norm:
        return []

    tokens: List[str] = []
    compact = norm.replace(" ", "")
    if len(compact) >= 2 and compact not in AMBIGUOUS_SHARED_TOKENS:
        tokens.append(compact)
    if " " in norm:
        tokens.append(norm)
        parts = [p.strip() for p in norm.split(" ") if len(p.strip()) >= 2]
        for p in parts:
            if p not in AMBIGUOUS_SHARED_TOKENS and p not in tokens:
                tokens.append(p)
    return tokens


def _parse_coach_headers_from_markdown(md_text: str) -> List[Tuple[str, str]]:
    """Extract (club_name_nfkc, coach_name_nfkc) pairs from official press conference section."""
    pairs: List[Tuple[str, str]] = []
    in_coach_section = False

    for line in md_text.splitlines():
        if line.startswith("### 【監督コメント】"):
            in_coach_section = True
            continue
        if in_coach_section and (line.startswith("### ") or line.startswith("## ")):
            in_coach_section = False
            continue
        if in_coach_section and line.startswith("#### 【"):
            m = re.match(r"^####\s*【([^】]+)】\s*(.+)$", line)
            if m:
                club_name = _norm_nfkc(m.group(1))
                coach_name = _norm_nfkc(m.group(2))
                if club_name and coach_name:
                    pairs.append((club_name, coach_name))

    return pairs


def extract_2026_managers_chronologically(
    md_dir: Path = DEFAULT_MD_2026_DIR,
) -> Dict[str, Dict[str, Any]]:
    """
    Scan chronologically sorted 2026 official markdown files to identify each club's
    latest active manager and any previous managers during the 2026 season.
    """
    history_by_club: Dict[str, List[str]] = {}
    md_files = sorted(glob.glob(str(md_dir / "*.md")))

    for f_path in md_files:
        try:
            text = Path(f_path).read_text(encoding="utf-8")
        except Exception:
            continue

        for club_name, coach_name in _parse_coach_headers_from_markdown(text):
            seq = history_by_club.setdefault(club_name, [])
            if not seq or seq[-1] != coach_name:
                seq.append(coach_name)

    result: Dict[str, Dict[str, Any]] = {}
    for club_name, seq in history_by_club.items():
        current_mgr = seq[-1]
        prev_mgrs = list(dict.fromkeys(m for m in seq[:-1] if m != current_mgr))
        result[club_name] = {
            "current_manager": current_mgr,
            "previous_managers_2026": prev_mgrs,
        }
    return result


class ClubEntityRegistry:
    """
    Builds and manages unified entity dictionaries for all 2026 J1 clubs
    plus FC Tokyo's Emperor's Cup opponents.
    """

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        md_2026_dir: Path = DEFAULT_MD_2026_DIR,
        target_config_path: Path = DEFAULT_TARGET_CONFIG_PATH,
    ) -> None:
        self.db_path = db_path
        self.md_2026_dir = md_2026_dir
        self.target_config_path = target_config_path
        self._clubs: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        """Rebuild registry from SQLite, 2026 official markdowns, and cup config."""
        self._clubs = {}
        manager_map = extract_2026_managers_chronologically(self.md_2026_dir)

        if self.db_path.exists():
            self._load_j1_clubs_from_db(manager_map)

        self._load_emperor_cup_opponents()

    def _query_j1_2026_teams(self, conn: sqlite3.Connection) -> List[sqlite3.Row]:
        """Fetch the 20 J1 clubs participating in the 2026 season."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                t.team_id,
                t.canonical_name,
                t.short_name,
                t.jleague_name,
                t.aliases_json
            FROM entity_master_teams t
            WHERE t.team_id IN (
                SELECT DISTINCT home_team_id FROM matches WHERE season = 2026
                UNION
                SELECT DISTINCT away_team_id FROM matches WHERE season = 2026
            )
            ORDER BY t.team_id ASC
            """,
        )
        return cur.fetchall()

    def _query_club_players(
        self,
        conn: sqlite3.Connection,
        team_id: str,
        top_limit: int = 18,
    ) -> Tuple[List[str], List[str]]:
        """
        Return (key_players_by_cbp, all_roster_names) for a given team_id.
        """
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                emp.canonical_name,
                COALESCE(SUM(pms.cbp_points), 0.0) AS total_cbp,
                COUNT(pms.match_id) AS apps
            FROM entity_master_players emp
            LEFT JOIN player_match_stats pms ON emp.player_id = pms.player_id
            WHERE emp.team_id = ?
            GROUP BY emp.player_id
            ORDER BY total_cbp DESC, apps DESC, emp.number ASC
            """,
            (team_id,),
        )
        rows = cur.fetchall()
        all_names = [_norm_nfkc(r["canonical_name"]) for r in rows if r["canonical_name"]]
        key_names = all_names[:top_limit]
        return (key_names, all_names)

    def _resolve_manager_info(
        self,
        canonical_name: str,
        jleague_name: str,
        manager_map: Dict[str, Dict[str, Any]],
    ) -> Tuple[str, List[str]]:
        """Match club name against extracted 2026 press conference manager records."""
        for candidate in [_norm_nfkc(canonical_name), _norm_nfkc(jleague_name)]:
            if candidate in manager_map:
                info = manager_map[candidate]
                return (
                    info["current_manager"],
                    info["previous_managers_2026"],
                )
        return ("監督", [])

    def _build_entity_keywords(
        self,
        canonical_name: str,
        short_name: str,
        aliases: List[str],
        current_manager: str,
        previous_managers: List[str],
        key_players: List[str],
    ) -> List[str]:
        """Assemble deduplicated keyword tokens for video discovery and transcript scanning."""
        kw_set: List[str] = []

        def _add(item: str) -> None:
            norm = _norm_nfkc(item)
            if len(norm) >= 2 and norm not in {"東京", "監督", "選手"} and norm not in kw_set:
                kw_set.append(norm)

        _add(canonical_name)
        _add(short_name)
        for al in aliases:
            if not re.match(r"^[A-Za-z\s\.]+$", al):
                _add(al)

        for mgr in [current_manager, *previous_managers]:
            for tok in _extract_surname_tokens(mgr):
                _add(tok)

        for pl in key_players[:14]:
            for tok in _extract_surname_tokens(pl):
                _add(tok)

        return kw_set

    def _load_j1_clubs_from_db(
        self,
        manager_map: Dict[str, Dict[str, Any]],
    ) -> None:
        """Populate J1 20 clubs from SQLite + 2026 official markdowns."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            team_rows = self._query_j1_2026_teams(conn)
            for row in team_rows:
                tid = str(row["team_id"])
                cname = _norm_nfkc(row["canonical_name"])
                sname = _norm_nfkc(row["short_name"] or cname)
                jname = _norm_nfkc(row["jleague_name"] or cname)

                try:
                    aliases = [_norm_nfkc(a) for a in json.loads(row["aliases_json"] or "[]")]
                except Exception:
                    aliases = [cname, sname]

                cur_mgr, prev_mgrs = self._resolve_manager_info(cname, jname, manager_map)
                key_players, all_players = self._query_club_players(conn, tid)
                keywords = self._build_entity_keywords(
                    canonical_name=cname,
                    short_name=sname,
                    aliases=aliases,
                    current_manager=cur_mgr,
                    previous_managers=prev_mgrs,
                    key_players=key_players,
                )

                self._clubs[tid] = {
                    "team_id": tid,
                    "competition_scope": "J1_2026",
                    "canonical_name": cname,
                    "short_name": sname,
                    "aliases": aliases,
                    "current_manager": cur_mgr,
                    "previous_managers_2026": prev_mgrs,
                    "key_players": key_players,
                    "roster_count": len(all_players),
                    "youtube_search_query": cname,
                    "entity_keywords": keywords,
                }
        finally:
            conn.close()

    def _load_emperor_cup_opponents(self) -> None:
        """Load enabled FC Tokyo Emperor's Cup opponents from config."""
        if not self.target_config_path.exists():
            return
        try:
            cfg = json.loads(self.target_config_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to read target_clubs_config.json: %s", e)
            return

        for opp in cfg.get("fct_emperor_cup_opponents", []):
            if not opp.get("enabled", False):
                continue
            self.register_emperor_cup_opponent(
                team_id=str(opp.get("team_id", "")).strip(),
                canonical_name=str(opp.get("canonical_name", "")).strip(),
                short_name=str(opp.get("short_name", "")).strip(),
                category=str(opp.get("category", "EMPEROR_CUP")).strip(),
                current_manager=str(opp.get("current_manager", "監督")).strip(),
                key_players=list(opp.get("key_players", [])),
                aliases=list(opp.get("aliases", [])),
                round_label=str(opp.get("round_label", "天皇杯")).strip(),
                persist_to_config=False,
            )

    def register_emperor_cup_opponent(
        self,
        team_id: str,
        canonical_name: str,
        short_name: str = "",
        category: str = "J2",
        current_manager: str = "監督",
        key_players: Optional[List[str]] = None,
        aliases: Optional[List[str]] = None,
        round_label: str = "天皇杯",
        persist_to_config: bool = False,
    ) -> Dict[str, Any]:
        """
        Dynamically register an FC Tokyo Emperor's Cup opponent (e.g., J2/J3/University club)
        into the active analysis target set. If the club is already in J1, marks cup flag.
        """
        tid = _norm_nfkc(team_id)
        cname = _norm_nfkc(canonical_name)
        sname = _norm_nfkc(short_name or cname)
        k_players = [_norm_nfkc(p) for p in (key_players or []) if p]
        al_list = [_norm_nfkc(a) for a in (aliases or [cname, sname]) if a]

        if tid in self._clubs:
            self._clubs[tid]["is_fct_emperor_cup_opponent"] = True
            self._clubs[tid]["emperor_cup_round"] = round_label
            return self._clubs[tid]

        keywords = self._build_entity_keywords(
            canonical_name=cname,
            short_name=sname,
            aliases=al_list,
            current_manager=current_manager,
            previous_managers=[],
            key_players=k_players,
        )
        entry = {
            "team_id": tid,
            "competition_scope": f"FCT_EMPEROR_CUP ({category})",
            "is_fct_emperor_cup_opponent": True,
            "emperor_cup_round": round_label,
            "canonical_name": cname,
            "short_name": sname,
            "aliases": al_list,
            "current_manager": _norm_nfkc(current_manager) or "監督",
            "previous_managers_2026": [],
            "key_players": k_players,
            "roster_count": len(k_players),
            "youtube_search_query": cname,
            "entity_keywords": keywords,
        }
        self._clubs[tid] = entry

        if persist_to_config:
            self._save_opponent_to_config(entry, category, round_label)

        return entry

    def _save_opponent_to_config(
        self,
        entry: Dict[str, Any],
        category: str,
        round_label: str,
    ) -> None:
        """Persist newly registered Emperor's Cup opponent into target_clubs_config.json."""
        cfg: Dict[str, Any] = {
            "version": "1.0.0",
            "include_all_j1_2026": True,
            "fct_emperor_cup_opponents": [],
        }
        if self.target_config_path.exists():
            try:
                cfg = json.loads(self.target_config_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        opps: List[Dict[str, Any]] = cfg.setdefault("fct_emperor_cup_opponents", [])
        opps = [o for o in opps if o.get("team_id") != entry["team_id"]]
        opps.append(
            {
                "enabled": True,
                "team_id": entry["team_id"],
                "canonical_name": entry["canonical_name"],
                "short_name": entry["short_name"],
                "category": category,
                "round_label": round_label,
                "current_manager": entry["current_manager"],
                "key_players": entry["key_players"],
                "aliases": entry["aliases"],
            },
        )
        cfg["fct_emperor_cup_opponents"] = opps
        self.target_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_config_path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_club(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single club profile by team_id."""
        return self._clubs.get(team_id)

    def list_target_clubs(self) -> List[Dict[str, Any]]:
        """Return all active target clubs (J1 20 clubs + enabled Emperor's Cup opponents)."""
        return list(self._clubs.values())

    def detect_mentioned_clubs(
        self,
        title: str,
        transcript_text: str,
    ) -> List[str]:
        """
        Identify which target clubs are meaningfully discussed in a video.
        If specific clubs are named in the video title, scopes strictly to those clubs.
        For general roundup videos (no club in title), detects clubs mentioned >= 2 times by name.
        """
        norm_title = _norm_nfkc(title)
        norm_body = _norm_nfkc(transcript_text)
        title_matched_ids: List[str] = []

        for tid, info in self._clubs.items():
            cname = info["canonical_name"]
            sname = info["short_name"]
            jp_aliases = [
                a for a in info.get("aliases", [])
                if len(a) >= 2 and a not in AMBIGUOUS_SHARED_TOKENS and not re.match(r"^[A-Za-z\s\.]+$", a)
            ]
            if any(name in norm_title for name in [cname, sname, *jp_aliases] if len(name) >= 2):
                title_matched_ids.append(tid)

        if title_matched_ids:
            return sorted(title_matched_ids)

        body_matched_ids: List[str] = []
        for tid, info in self._clubs.items():
            cname = info["canonical_name"]
            sname = info["short_name"]
            club_mentions = norm_body.count(cname) + (
                norm_body.count(sname) if sname != cname and sname not in AMBIGUOUS_SHARED_TOKENS else 0
            )
            kw_hits = sum(1 for kw in info["entity_keywords"] if kw in norm_body)
            if club_mentions >= 2 and kw_hits >= 3:
                body_matched_ids.append(tid)

        return sorted(body_matched_ids)

    def export_registry_json(
        self,
        output_path: Path = DEFAULT_REGISTRY_EXPORT_PATH,
    ) -> Path:
        """Export current 2026 club/manager/player registry to JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "total_target_clubs": len(self._clubs),
            "clubs": self._clubs,
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

