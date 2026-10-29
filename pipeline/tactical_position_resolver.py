"""Multi-source Tactical Position & Role Stint Resolver (pipeline/tactical_position_resolver.py).

Combines three complementary sources without over-relying on any single signal:
1. Yahoo `/summary` time-series formation snapshots (x, y pitch coordinates across substitutions)
2. Explicit formation/position descriptions in official match reports, press conferences, text live,
   and Layer 1/3 discourse claims (used to confirm or override diagram mistakes and capture shifts)
3. SPAIA zone/side indicators (`PASidePlayLCount` / `PASidePlayRCount`) strictly as non-decisive
   fluidity detectors (`BOTH_FLANKS`), never for hard single-position assignment.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from scrapers.yahoo_soccer import parse_yahoo_minute_label

logger = logging.getLogger("tactical_position_resolver")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_YAHOO_DIR = ROOT_DIR / "data" / "raw" / "yahoo"
DEFAULT_SPAIA_DIR = ROOT_DIR / "data" / "raw" / "spaia"
DEFAULT_MD_DIR = ROOT_DIR / "data" / "markdown" / "2026"

# 明示的ポジション記述ラベル -> (role, role_group, lane)
EXPLICIT_ROLE_LABELS: List[Tuple[str, Tuple[str, str, str]]] = [
    (r"(?:3バックの左|左CB|左センターバック)", ("LCB", "CB", "LEFT_HALF")),
    (r"(?:3バックの右|右CB|右センターバック)", ("RCB", "CB", "RIGHT_HALF")),
    (r"(?:3バックの中央|3バックの真ん中|中央CB)", ("CCB", "CB", "CENTER")),
    (r"(?:右SB|右サイドバック)", ("RSB", "FB", "RIGHT")),
    (r"(?:左SB|左サイドバック)", ("LSB", "FB", "LEFT")),
    (r"(?:右WB|右ウイングバック|右ウィングバック)", ("RWB", "WB", "RIGHT")),
    (r"(?:左WB|左ウイングバック|左ウィングバック)", ("LWB", "WB", "LEFT")),
    (r"(?:右WG|右ウイング|右ウィング|右SH|右サイドハーフ)", ("RWG", "WIDE_ATT", "RIGHT")),
    (r"(?:左WG|左ウイング|左ウィング|左SH|左サイドハーフ)", ("LWG", "WIDE_ATT", "LEFT")),
    (r"(?:トップ下)", ("OMF", "SHADOW", "CENTER")),
    (r"(?:シャドー)", ("RST", "SHADOW", "CENTER")),
    (r"(?:アンカー|ボランチ)", ("DMF", "DMF", "CENTER")),
    (r"(?:1トップ|ワントップ|センターフォワード)", ("CF", "CF", "CENTER")),
]

FLUIDITY_TEXT_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"右でも左でも|左右を入れ替|ポジションを入れ替|両サイド|逆サイドに流れ"), "BOTH_FLANKS"),
    (re.compile(r"3バック化|ビルドアップ時は3枚|可変|最終ラインに落ち"), "FLUID_BUILDUP"),
    (re.compile(r"(?:後半から|途中から).{0,12}(?:SB|WB|ウイングバック|サイドバック|ボランチ|3バック)|途中から.{0,12}下が"), "ROLE_SHIFTED"),
]

MID_GAME_KEYWORDS = ("後半から", "後半は", "途中から", "交代後", "ポジションを移", "に下げ", "に回っ")


def _clean_name_key(name: str) -> str:
    """空白や中黒を除去した氏名照合キーを返す."""
    return re.sub(r"[\s　・]+", "", name or "")


def _parse_sub_out_minute(sub_info: str) -> Optional[int]:
    """'アウト後半18分' などから退場・交代OUT時刻を取得する."""
    if not sub_info or "アウト" not in sub_info:
        return None
    return parse_yahoo_minute_label(sub_info)


class TacticalPositionResolver:
    """マルチソース合議により試合別・時間帯別の選手ポジションと流動タグを解決・格納する."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        yahoo_dir: Path = DEFAULT_YAHOO_DIR,
        spaia_dir: Path = DEFAULT_SPAIA_DIR,
        md_dir: Path = DEFAULT_MD_DIR,
    ) -> None:
        self.db_path = db_path
        self.yahoo_dir = yahoo_dir
        self.spaia_dir = spaia_dir
        self.md_dir = md_dir
        self.ensure_tables()
        self._emp_by_num, self._emp_by_name = self._load_emp_lookups()

    def ensure_tables(self) -> None:
        """football.db に match_formations と player_match_positions テーブルを作成する."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS match_formations (
                    match_id TEXT PRIMARY KEY,
                    home_team_id TEXT NOT NULL,
                    away_team_id TEXT NOT NULL,
                    home_initial_formation TEXT,
                    away_initial_formation TEXT,
                    home_formations_json TEXT,
                    away_formations_json TEXT,
                    formation_confidence TEXT
                )
                """,
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS player_match_positions (
                    match_id TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    player_key TEXT NOT NULL,
                    player_id TEXT,
                    player_name TEXT NOT NULL,
                    number INTEGER,
                    registered_pos TEXT,
                    is_starter INTEGER NOT NULL DEFAULT 0,
                    minutes_estimated INTEGER NOT NULL DEFAULT 0,
                    primary_role TEXT NOT NULL,
                    primary_role_group TEXT NOT NULL,
                    primary_lane TEXT NOT NULL,
                    role_stints_json TEXT NOT NULL,
                    fluidity_tags_json TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (match_id, team_id, player_key)
                )
                """,
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pmp_match_team
                ON player_match_positions (match_id, team_id)
                """,
            )
            conn.commit()
        finally:
            conn.close()

    def _load_emp_lookups(self) -> Tuple[Dict[Tuple[str, str], str], Dict[Tuple[str, str], str]]:
        """entity_master_players から (team_id, number) と (team_id, clean_name) の辞書を構築する."""
        by_num: Dict[Tuple[str, str], str] = {}
        by_name: Dict[Tuple[str, str], str] = {}
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT player_id, team_id, number, canonical_name FROM entity_master_players",
            )
            for pid, tid, num, cname in cur.fetchall():
                if tid and num is not None:
                    by_num[(tid, str(num))] = pid
                if tid and cname:
                    by_name[(tid, _clean_name_key(cname))] = pid
        finally:
            conn.close()
        return (by_num, by_name)

    def _resolve_player_id(self, team_id: str, number: str, player_name: str) -> Optional[str]:
        """チームIDと背番号または氏名から entity_master_players.player_id を解決する."""
        ckey = _clean_name_key(player_name)
        if ckey and (team_id, ckey) in self._emp_by_name:
            return self._emp_by_name[(team_id, ckey)]
        if number and (team_id, str(number)) in self._emp_by_num:
            return self._emp_by_num[(team_id, str(number))]
        return None

    # ------------------------------------------------------------------
    # Source 1: Yahoo /summary 時間帯別フォーメーション図からのスティント構築
    # ------------------------------------------------------------------

    def build_stints_from_snapshots(
        self,
        snapshots: List[Dict[str, Any]],
        side_key: str,
        lineup_side: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """1チーム分のスナップショット列から選手ごとの時間帯スティント辞書を構築する."""
        sub_out_map: Dict[str, int] = {}
        starter_nums: Set[str] = set()
        reg_pos_map: Dict[str, str] = {}
        full_name_map: Dict[str, str] = {}

        for p in lineup_side.get("starters", []):
            num = str(p.get("number", ""))
            starter_nums.add(num)
            reg_pos_map[num] = p.get("registered_pos", "")
            full_name_map[num] = p.get("player_name", "")
            out_m = _parse_sub_out_minute(p.get("sub_info", ""))
            if out_m is not None:
                sub_out_map[num] = out_m

        for p in lineup_side.get("bench", []):
            num = str(p.get("number", ""))
            reg_pos_map[num] = p.get("registered_pos", "")
            full_name_map[num] = p.get("player_name", "")
            out_m = _parse_sub_out_minute(p.get("sub_info", ""))
            if out_m is not None:
                sub_out_map[num] = out_m

        raw_segments_by_num: Dict[str, List[Dict[str, Any]]] = {}
        players_field = f"{side_key}_players"
        total_snaps = len(snapshots)

        for idx, snap in enumerate(snapshots):
            start_min = int(snap.get("minute_approx", 0))
            next_min = (
                int(snapshots[idx + 1].get("minute_approx", 90))
                if idx + 1 < total_snaps
                else 90
            )
            if next_min < start_min:
                next_min = max(start_min, 90)

            for pl in snap.get(players_field, []):
                num = str(pl.get("number", ""))
                if not num:
                    continue
                end_min = next_min
                if num in sub_out_map and start_min <= sub_out_map[num] < end_min:
                    end_min = sub_out_map[num]

                if num not in full_name_map and pl.get("player_name"):
                    full_name_map[num] = pl["player_name"]
                if not reg_pos_map.get(num) and pl.get("registered_pos"):
                    reg_pos_map[num] = pl["registered_pos"]

                raw_segments_by_num.setdefault(num, []).append(
                    {
                        "from_min": start_min,
                        "to_min": max(start_min + 1, end_min) if end_min == start_min else end_min,
                        "role": pl.get("inferred_role", "MF"),
                        "role_group": pl.get("role_group", "CMF"),
                        "lane": pl.get("inferred_lane", "CENTER"),
                    },
                )

        resolved: Dict[str, Dict[str, Any]] = {}
        for num, segs in raw_segments_by_num.items():
            merged = self._merge_adjacent_stints(segs)
            resolved[num] = {
                "number": int(num) if num.isdigit() else None,
                "number_str": num,
                "player_name": full_name_map.get(num, f"#{num}"),
                "registered_pos": reg_pos_map.get(num, ""),
                "is_starter": 1 if num in starter_nums else 0,
                "stints": merged,
            }
        return resolved

    def _merge_adjacent_stints(self, segs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """連続する同一ロールの区間を1つのスティントにマージする."""
        if not segs:
            return []
        merged: List[Dict[str, Any]] = [dict(segs[0])]
        for seg in segs[1:]:
            prev = merged[-1]
            if prev["role"] == seg["role"] and prev["lane"] == seg["lane"]:
                prev["to_min"] = max(prev["to_min"], seg["to_min"])
            else:
                merged.append(dict(seg))
        return merged

    # ------------------------------------------------------------------
    # Source 2: 公式戦評・会見・テキスト速報・7層言説からの記述手掛かり抽出
    # ------------------------------------------------------------------

    def extract_match_textual_clues(
        self,
        match_id: str,
        yahoo_game_id: Optional[str],
        team_players: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """試合関連テキストからフォーメーション記述と選手別のロール・流動記述を抽出する."""
        sentences = self._collect_match_sentences(match_id, yahoo_game_id)
        mentioned_formations = set(re.findall(r"\b([345]-\d(?:-\d){1,2})\b", "\n".join(sentences)))

        player_clues: Dict[str, Dict[str, Any]] = {}
        for tid, names in team_players.items():
            for full_name in names:
                short_tokens = self._build_player_tokens(full_name)
                clues = self._scan_sentences_for_player(sentences, short_tokens)
                if clues["explicit_roles"] or clues["fluidity_tags"]:
                    player_clues[f"{tid}:{full_name}"] = clues

        return {
            "formations_in_text": sorted(mentioned_formations),
            "player_clues": player_clues,
        }

    def _collect_match_sentences(
        self,
        match_id: str,
        yahoo_game_id: Optional[str],
    ) -> List[str]:
        """公式MDとYahooテキスト速報から文リストを収集する."""
        chunks: List[str] = []
        md_file = self.md_dir / f"{match_id}.md"
        if md_file.exists():
            chunks.append(md_file.read_text(encoding="utf-8"))

        for cand_id in filter(None, [match_id, yahoo_game_id]):
            txt_file = self.yahoo_dir / f"{cand_id}_text.json"
            if txt_file.exists():
                try:
                    tdata = json.loads(txt_file.read_text(encoding="utf-8"))
                    for item in tdata.get("timeline", []):
                        if item.get("text"):
                            chunks.append(item["text"])
                except Exception:
                    pass
                break

        raw_text = "\n".join(chunks)
        return [s.strip() for s in re.split(r"[。！？\n]+", raw_text) if len(s.strip()) >= 6]

    def _build_player_tokens(self, full_name: str) -> List[str]:
        """選手フルネームから文内検索用のトークン（フルネームおよび2文字以上の姓）を作る."""
        tokens = [full_name, full_name.replace(" ", "")]
        parts = [p for p in re.split(r"[\s　]+", full_name) if len(p) >= 2]
        if parts:
            tokens.append(parts[0])
        return list(dict.fromkeys(tokens))

    def _player_bound_to_role(self, sent: str, tokens: List[str], role_expr: str) -> bool:
        """文中で選手名とポジション表現が直接係り受けしているか判定する（他選手のロール誤結合を防止）."""
        tok_union = "|".join(re.escape(t) for t in tokens if t)
        if not tok_union:
            return False
        pattern = (
            rf"(?:{role_expr}(?:の|に入った|で先発した|を務めた|起用の)\s*(?:{tok_union}))"
            rf"|(?:(?:{tok_union})(?:選手)?\s*(?:は|が|を|も).{{0,10}}{role_expr})"
        )
        return bool(re.search(pattern, sent))

    def _scan_sentences_for_player(
        self,
        sentences: List[str],
        tokens: List[str],
    ) -> Dict[str, Any]:
        """対象選手名を含む文から明示ロールと流動性タグを抽出する."""
        explicit_roles: List[Dict[str, Any]] = []
        fluid_tags: Set[str] = set()

        for sent in sentences:
            if not any(tok in sent for tok in tokens):
                continue
            is_mid_game = any(kw in sent for kw in MID_GAME_KEYWORDS)
            for role_expr, (role, rgroup, lane) in EXPLICIT_ROLE_LABELS:
                if self._player_bound_to_role(sent, tokens, role_expr):
                    explicit_roles.append(
                        {
                            "role": role,
                            "role_group": rgroup,
                            "lane": lane,
                            "is_mid_game": is_mid_game,
                            "quote": sent[:140],
                        },
                    )
            for fpat, ftag in FLUIDITY_TEXT_PATTERNS:
                if fpat.search(sent):
                    fluid_tags.add(ftag)

        return {
            "explicit_roles": explicit_roles,
            "fluidity_tags": sorted(fluid_tags),
        }

    # ------------------------------------------------------------------
    # Source 3: SPAIA 左右PA脇指標による非決定的・両サイド担当シグナル検知
    # ------------------------------------------------------------------

    def extract_spaia_fluidity_map(
        self,
        match_id: str,
        yahoo_game_id: Optional[str],
    ) -> Dict[str, Dict[str, Any]]:
        """詳細SPAIA JSONがある場合のみ、左右両サイドで同等にプレーした選手を検知する."""
        for cand_id in filter(None, [yahoo_game_id, match_id]):
            sp_file = self.spaia_dir / f"{cand_id}_player_stats.json"
            if not sp_file.exists():
                continue
            try:
                data = json.loads(sp_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            plist = data.get("player_stats")
            if not isinstance(plist, list):
                continue

            fluid_map: Dict[str, Dict[str, Any]] = {}
            for p in plist:
                name_key = _clean_name_key(p.get("Name", ""))
                left_c = int(p.get("PASidePlayLCount") or 0)
                right_c = int(p.get("PASidePlayRCount") or 0)
                total_lr = left_c + right_c
                if total_lr >= 6 and left_c >= 3 and right_c >= 3:
                    ratio_l = left_c / total_lr
                    if 0.30 <= ratio_l <= 0.70:
                        fluid_map[name_key] = {
                            "pa_side_left": left_c,
                            "pa_side_right": right_c,
                            "both_flanks_signal": True,
                        }
            return fluid_map
        return {}

    # ------------------------------------------------------------------
    # 合議・統合（Reconciliation）とDB保存
    # ------------------------------------------------------------------

    def reconcile_player_position(
        self,
        team_id: str,
        base_entry: Dict[str, Any],
        text_clue: Optional[Dict[str, Any]],
        spaia_clue: Optional[Dict[str, Any]],
        team_form_confirmed: bool,
    ) -> Dict[str, Any]:
        """Yahoo座標スティント、言語記述、SPAIA補助シグナルを統合して最終レコードを作る."""
        stints = [dict(s) for s in base_entry["stints"]]
        fluid_tags: Set[str] = set()
        evidence: Dict[str, Any] = {"sources": ["yahoo_summary_diagram"]}

        # スナップショット推移からの自動流動検知
        distinct_groups = {s["role_group"] for s in stints}
        if len(distinct_groups) >= 2:
            fluid_tags.add("ROLE_SHIFTED")

        lanes_seen = {s["lane"] for s in stints}
        has_right = bool(lanes_seen & {"RIGHT", "RIGHT_HALF"})
        has_left = bool(lanes_seen & {"LEFT", "LEFT_HALF"})
        if has_right and has_left:
            fluid_tags.add("BOTH_FLANKS")

        confidence = "HIGH" if team_form_confirmed else "MEDIUM"

        # 言語記述による検証・誤りオーバーライド・途中シフト補完
        if text_clue:
            for t in text_clue.get("fluidity_tags", []):
                fluid_tags.add(t)
            exp_roles = text_clue.get("explicit_roles", [])
            if exp_roles:
                evidence["sources"].append("textual_description")
                evidence["text_quotes"] = [r["quote"] for r in exp_roles[:2]]
                stint_groups = {s["role_group"] for s in stints}
                first_exp = exp_roles[0]

                if first_exp["role_group"] in stint_groups:
                    confidence = "CONFIRMED"
                elif first_exp["is_mid_game"]:
                    # 後半途中のコンバート記述を補完
                    fluid_tags.add("ROLE_SHIFTED")
                    stints.append(
                        {
                            "from_min": 60,
                            "to_min": 90,
                            "role": first_exp["role"],
                            "role_group": first_exp["role_group"],
                            "lane": first_exp["lane"],
                        },
                    )
                    confidence = "TEXT_CORRECTED"
                else:
                    # 初期フォーメーション図の誤りと判定し該当ロール区間を記述で補正
                    if stints:
                        orig_role = stints[0]["role"]
                        for st in stints:
                            if st["role"] == orig_role:
                                st["role"] = first_exp["role"]
                                st["role_group"] = first_exp["role_group"]
                                st["lane"] = first_exp["lane"]
                    confidence = "TEXT_CORRECTED"

        # SPAIA 両サイド検知（ロール自体は決め打ち変更せず BOTH_FLANKS タグのみ付与）
        if spaia_clue and spaia_clue.get("both_flanks_signal"):
            fluid_tags.add("BOTH_FLANKS")
            evidence["sources"].append("spaia_side_balance")
            evidence["spaia_lr"] = {
                "left": spaia_clue["pa_side_left"],
                "right": spaia_clue["pa_side_right"],
            }

        if "ROLE_SHIFTED" in fluid_tags and confidence not in ("CONFIRMED", "TEXT_CORRECTED"):
            confidence = "FLUID_MULTI_ROLE"

        # 主ロールは最長出場区間（同長なら先発区間）を採用
        longest_stint = max(
            stints,
            key=lambda s: (s["to_min"] - s["from_min"], -s["from_min"]),
        )
        total_mins = sum(max(0, s["to_min"] - s["from_min"]) for s in stints)

        num_str = base_entry["number_str"]
        p_name = base_entry["player_name"]
        pid = self._resolve_player_id(team_id, num_str, p_name)
        player_key = pid or f"{team_id}_{num_str}"

        return {
            "team_id": team_id,
            "player_key": player_key,
            "player_id": pid,
            "player_name": p_name,
            "number": base_entry["number"],
            "registered_pos": base_entry["registered_pos"],
            "is_starter": base_entry["is_starter"],
            "minutes_estimated": min(95, total_mins),
            "primary_role": longest_stint["role"],
            "primary_role_group": longest_stint["role_group"],
            "primary_lane": longest_stint["lane"],
            "role_stints": stints,
            "fluidity_tags": sorted(fluid_tags),
            "confidence": confidence,
            "evidence": evidence,
        }

    def resolve_and_store_match(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
    ) -> Dict[str, Any]:
        """単一試合のポジション・フォーメーションを解決してSQLiteへ保存する."""
        summary_file = self.yahoo_dir / f"{match_id}_summary.json"
        if not summary_file.exists():
            return {"match_id": match_id, "resolved_players": 0}

        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        yahoo_gid = summary.get("game_id")
        snapshots = summary.get("formation_snapshots", [])
        lineup = summary.get("lineup", {})
        if not snapshots:
            return {"match_id": match_id, "resolved_players": 0}

        home_base = self.build_stints_from_snapshots(snapshots, "home", lineup.get("home", {}))
        away_base = self.build_stints_from_snapshots(snapshots, "away", lineup.get("away", {}))

        team_player_names = {
            home_team_id: [v["player_name"] for v in home_base.values()],
            away_team_id: [v["player_name"] for v in away_base.values()],
        }
        text_clues = self.extract_match_textual_clues(match_id, yahoo_gid, team_player_names)
        spaia_clues = self.extract_spaia_fluidity_map(match_id, yahoo_gid)

        h_forms = list(dict.fromkeys(s.get("home_formation", "") for s in snapshots if s.get("home_formation")))
        a_forms = list(dict.fromkeys(s.get("away_formation", "") for s in snapshots if s.get("away_formation")))
        forms_in_text = set(text_clues.get("formations_in_text", []))

        h_confirmed = not forms_in_text or bool(set(h_forms) & forms_in_text)
        a_confirmed = not forms_in_text or bool(set(a_forms) & forms_in_text)

        records: List[Dict[str, Any]] = []
        for tid, base_map, confirmed in [
            (home_team_id, home_base, h_confirmed),
            (away_team_id, away_base, a_confirmed),
        ]:
            for entry in base_map.values():
                pname = entry["player_name"]
                tclue = text_clues["player_clues"].get(f"{tid}:{pname}")
                sclue = spaia_clues.get(_clean_name_key(pname))
                rec = self.reconcile_player_position(tid, entry, tclue, sclue, confirmed)
                records.append(rec)

        self._save_match_records(
            match_id=match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            h_forms=h_forms,
            a_forms=a_forms,
            form_conf="CONFIRMED" if (h_confirmed and a_confirmed and forms_in_text) else "HIGH",
            records=records,
        )
        return {
            "match_id": match_id,
            "resolved_players": len(records),
            "home_formation": h_forms[0] if h_forms else "",
            "away_formation": a_forms[0] if a_forms else "",
        }

    def _save_match_records(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
        h_forms: List[str],
        a_forms: List[str],
        form_conf: str,
        records: List[Dict[str, Any]],
    ) -> None:
        """解決済みのフォーメーションと選手別ポジションをSQLiteへ一括UPSERTする."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO match_formations (
                    match_id, home_team_id, away_team_id,
                    home_initial_formation, away_initial_formation,
                    home_formations_json, away_formations_json, formation_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    home_team_id,
                    away_team_id,
                    h_forms[0] if h_forms else "",
                    a_forms[0] if a_forms else "",
                    json.dumps(h_forms, ensure_ascii=False),
                    json.dumps(a_forms, ensure_ascii=False),
                    form_conf,
                ),
            )
            rows = [
                (
                    match_id,
                    r["team_id"],
                    r["player_key"],
                    r["player_id"],
                    r["player_name"],
                    r["number"],
                    r["registered_pos"],
                    r["is_starter"],
                    r["minutes_estimated"],
                    r["primary_role"],
                    r["primary_role_group"],
                    r["primary_lane"],
                    json.dumps(r["role_stints"], ensure_ascii=False),
                    json.dumps(r["fluidity_tags"], ensure_ascii=False),
                    r["confidence"],
                    json.dumps(r["evidence"], ensure_ascii=False),
                )
                for r in records
            ]
            cur.executemany(
                """
                INSERT OR REPLACE INTO player_match_positions (
                    match_id, team_id, player_key, player_id, player_name,
                    number, registered_pos, is_starter, minutes_estimated,
                    primary_role, primary_role_group, primary_lane,
                    role_stints_json, fluidity_tags_json, confidence, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def resolve_all_2026_matches(self) -> Dict[str, Any]:
        """football.db 内の 2026 シーズン全120試合を一括解決・格納する."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT match_id, home_team_id, away_team_id FROM matches WHERE season = 2026 ORDER BY date, match_id",
            )
            matches = cur.fetchall()
        finally:
            conn.close()

        resolved_matches = 0
        total_players = 0
        for mid, h_id, a_id in matches:
            res = self.resolve_and_store_match(mid, h_id, a_id)
            if res["resolved_players"] > 0:
                resolved_matches += 1
                total_players += res["resolved_players"]

        return {
            "matches_processed": len(matches),
            "matches_resolved": resolved_matches,
            "total_player_positions": total_players,
        }
