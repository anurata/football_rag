"""
7-Layer Discourse Decomposer & SQLite Repository (pipeline/discourse_layer_decomposer.py).

Separates interleaved YouTube / media tactical commentary into the 7 Layers defined in
TACTICAL_PHILOSOPHY_AND_MANIFESTO.md:
  Layer 1: 客観事実 (Hard Facts / Reported Stats & Lineups)
  Layer 2: 先人の知見 (Tactical Heuristics & Universal Principles)
  Layer 3: 事象説明 (Grounded Causal Explanation of Match Phenomena)
  Layer 4: 仮説構築 (Hypothesis on Coach Intent & Game Plan)
  Layer 5: 物語とナラティブ (Season Arc, Redemption & Derby Drama)
  Layer 6: 大胆な未来予測 (Bold Match / Transfer Forecasting)
  Layer 7: 願望とロマン (Supporter & Pundit Aspiration & Romance)

Primary Mode: Gemini Structured JSON Extraction (via GeminiTacticalClient).
Fallback Mode: Deterministic Linguistic & Tactical Marker Classifier.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.gemini_client import GeminiTacticalClient

logger = logging.getLogger("discourse_layer_decomposer")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"

LAYER_NAMES: Dict[int, str] = {
    1: "L1_HARD_FACT",
    2: "L2_TACTICAL_HEURISTICS",
    3: "L3_GROUNDED_EXPLANATION",
    4: "L4_HYPOTHESIS_GENERATION",
    5: "L5_NARRATIVE_DRAMA",
    6: "L6_BOLD_FORECASTING",
    7: "L7_ASPIRATION_ROMANCE",
}

DECOMPOSER_SYSTEM_PROMPT = """あなたはJリーグ戦術言説の『虚実のグラデーション（7レイヤー）』構造化アナリストです。
与えられたYouTube戦術解説セグメント（生の発言テキスト）を読み、その中に混在している主張・言説を文脈ごとに分離し、以下の7レイヤーのいずれかに厳密に分類してJSON出力してください。

【7レイヤーの厳密定義】
- Layer 1 (客観事実): スコア、パス本数・保持率・スプリント数などの数値、スタメン配置、何分の交代・得点・警告といった客観的記録。
- Layer 2 (先人の知見): 特定の1試合を超えた普遍的なサッカー戦術原則・空間理論・役割類型（例：「左利きCBが運べるとビルドアップ構造を1人で解決できる」「2トップをボランチで監視するとライン間の縦パスは消えるが外回りは許容される」）。
- Layer 3 (事象説明): ピッチ上で起きた現象に対する論理的因果説明（例：「後半4-2-3-1に修正してトップ下を置いたことで相手ボランチを引き出し、CBに時間が生まれて前進できた」）。
- Layer 4 (仮説構築): 指揮官の胸中・ゲームプランや選手の意図に対する推論（例：「監督はリードしても塩漬けにせず90分間敵陣で制圧し続ける意図があるのではないか」「前半を抑えめにして後半勝負をかけるプランだったと思われる」）。
- Layer 5 (物語とナラティブ): 過去の敗戦・ミスからの雪辱、選手の成長・覚醒、ダービーの因縁など時間軸のドラマ（例：「過去の失点ミスを完全に帳消しにし、絶対の守護神へと信頼を取り戻した」）。
- Layer 6 (大胆な未来予測): 次節プレビューでの展開・スコア予想、出場機会や移籍市場の去就推理（例：「次節相手はローブロックを敷くが、カウンターの裏をCBのロングフィード一発で突いて先制するだろう」）。
- Layer 7 (願望とロマン): 話者やサポーターの純粋な情熱・祈り・期待（例：「今年こそ言い訳なしで優勝してほしい」「この選手にはヨーロッパへ羽ばたいてほしい」）。

【絶対遵守ルール（改ざん防止）】
1. 発言内に存在しない事実や言葉を創作することは厳禁です。
2. 音声認識崩れやあだ名がある場合、【候補クラブ所属選手】に存在する選手のみ実名補完を許可し、リストにない他クラブ選手名を勝手に推測して当てはめることは厳禁です（不明な場合は発言のまま記載）。
3. `original_quote` には必ず入力テキスト内の該当箇所をそのまま抜粋してください。
4. 挨拶やチャンネル登録呼びかけ等の無意味な雑談は除外してください。
5. 言及対象のクラブID（候補リストから選択）を `team_id` に設定してください。
"""

GEMINI_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "claims": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "truth_layer": {"type": "INTEGER"},
                    "team_id": {"type": "STRING"},
                    "manager_mentioned": {"type": "STRING"},
                    "players_mentioned": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                    "statement_text": {"type": "STRING"},
                    "original_quote": {"type": "STRING"},
                },
                "required": [
                    "truth_layer",
                    "team_id",
                    "statement_text",
                    "original_quote",
                ],
            },
        },
    },
    "required": ["claims"],
}


def compute_claim_id(segment_id: str, team_id: str, truth_layer: int, quote: str) -> str:
    """Create deterministic unique hash ID for idempotent storage."""
    raw_key = f"{segment_id}|{team_id}|{truth_layer}|{quote[:80]}"
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:14]
    return f"CLM_{segment_id}_{digest}"


def split_into_discourse_units(verbatim_text: str) -> List[str]:
    """
    Split continuous Japanese ASR transcript into meaningful 1-3 sentence discourse units.
    Handles transcripts both with punctuation (。) and space-separated ASR chunks.
    """
    text = verbatim_text.strip()
    if not text:
        return []

    # First split by Japanese sentence-ending punctuation or clear discourse markers
    raw_parts = re.split(r"(?<=[。！？!?])\s*|\s+(?=ただ|しかし|一方で|なぜなら|というのは|そして|さらに|まとめ)", text)
    units: List[str] = []
    buf = ""

    for part in raw_parts:
        p = part.strip()
        if not p:
            continue
        if len(buf) + len(p) < 160:
            buf = f"{buf} {p}".strip() if buf else p
        else:
            if len(buf) >= 25:
                units.append(buf)
            buf = p

    if len(buf) >= 25:
        units.append(buf)

    # If ASR had zero punctuation and produced one giant block, chunk every ~150 chars on spaces
    final_units: List[str] = []
    for u in units:
        if len(u) <= 220:
            final_units.append(u)
        else:
            words = u.split(" ")
            chunk = ""
            for w in words:
                if len(chunk) + len(w) + 1 <= 170:
                    chunk = f"{chunk} {w}".strip() if chunk else w
                else:
                    if len(chunk) >= 25:
                        final_units.append(chunk)
                    chunk = w
            if len(chunk) >= 25:
                final_units.append(chunk)

    return final_units


def classify_unit_layer_deterministic(unit_text: str, video_title: str = "") -> int:
    """
    Classify a single discourse unit into Layer 1..7 deterministically
    using linguistic modality, causal markers, and numerical fact density.
    """
    is_preview = "プレビュー" in video_title or "予想" in video_title

    # Layer 7: Aspiration & Romance (desires, prayers, emotional hopes)
    if re.search(
        r"してほしい|てほしい|見たい|願って|祈り|優勝したい|夢ある|期待したくなる|笑えよ|取らせたい",
        unit_text,
    ):
        return 7

    # Layer 6: Bold Forecasting (future match predictions, transfer speculation)
    if re.search(
        r"予想スコア|新天地|移籍市場|狙う可能性|次節は|来るでしょう|入ってくるよな|行ってこいで|先制するだろう",
        unit_text,
    ) or (is_preview and re.search(r"だろう|でしょう|はず|予想|と思います", unit_text)):
        return 6

    # Layer 5: Narrative Drama (redemption, history, club DNA, season arc)
    if re.search(
        r"帳消し|超消し|伝説になる|ドラマ|雪辱|借りは返|選んだ道を|伝統的なDNA|覚醒|歴史|神を見た|完全試合",
        unit_text,
    ):
        return 5

    # Layer 4: Hypothesis Generation (inferring coach intent / hidden game plan)
    if re.search(
        r"ではないか|じゃないのかな|狙いがあったんじゃ|意図があって|プラン|思ってるでしょ|考えたと思|可能性も",
        unit_text,
    ):
        return 4

    # Layer 2: Tactical Heuristics (universal football principles & positional theory)
    if re.search(
        r"ゲームメーカーがいると|仕組みを\s*1\s*人で解決|一般的に|原則として|サッカーを見る時|役割分担|セオリー|というのはそもそも",
        unit_text,
    ):
        return 2

    # Layer 3: Grounded Explanation (causal explanation of match mechanics)
    if re.search(
        r"なぜなら|なんでかって|からこそ|によって|たことで|ため|要因|機能して|剥がし|修正|優位性|抑え|封じ",
        unit_text,
    ):
        return 3

    # Layer 1: Hard Facts (numerical stats, minutes, substitutions, starting XI)
    if re.search(
        r"\d+\s*(?:分|対|本|%|回|点|番|cm)|スタメン|クリーンシート|イエロー|コーナーキック|パス本数|保持率",
        unit_text,
    ):
        return 1

    return 3


class TacticalDiscourseRepository:
    """SQLite persistence layer for 7-layer tactical discourse claims."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Create tactical_discourse_claims table and indexes idempotently."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tactical_discourse_claims (
                    claim_id TEXT PRIMARY KEY,
                    segment_id TEXT NOT NULL,
                    video_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    video_title TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    time_range TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    manager_mentioned TEXT,
                    players_mentioned_json TEXT,
                    truth_layer INTEGER NOT NULL,
                    layer_name TEXT NOT NULL,
                    source_reliability TEXT NOT NULL,
                    statement_text TEXT NOT NULL,
                    original_quote TEXT NOT NULL,
                    extraction_method TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_claims_team_layer "
                "ON tactical_discourse_claims(team_id, truth_layer)",
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_claims_video "
                "ON tactical_discourse_claims(video_id)",
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_claims(self, claims: List[Dict[str, Any]]) -> int:
        """Insert or replace decomposed 7-layer claims into SQLite."""
        if not claims:
            return 0

        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            rows = [
                (
                    c["claim_id"],
                    c["segment_id"],
                    c["video_id"],
                    c["channel_name"],
                    c["video_title"],
                    c["video_url"],
                    c["time_range"],
                    c["team_id"],
                    c.get("manager_mentioned", ""),
                    json.dumps(c.get("players_mentioned", []), ensure_ascii=False),
                    int(c["truth_layer"]),
                    c["layer_name"],
                    c["source_reliability"],
                    c["statement_text"],
                    c["original_quote"],
                    c["extraction_method"],
                    c["created_at"],
                )
                for c in claims
            ]
            cur.executemany(
                """
                INSERT OR REPLACE INTO tactical_discourse_claims (
                    claim_id, segment_id, video_id, channel_name, video_title,
                    video_url, time_range, team_id, manager_mentioned,
                    players_mentioned_json, truth_layer, layer_name,
                    source_reliability, statement_text, original_quote,
                    extraction_method, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def query_claims(
        self,
        team_id: Optional[str] = None,
        layers: Optional[List[int]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query stored claims filtered by club and/or specific truth layers (1..7)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            clauses: List[str] = []
            params: List[Any] = []

            if team_id:
                clauses.append("team_id = ?")
                params.append(team_id)
            if layers:
                placeholders = ",".join("?" for _ in layers)
                clauses.append(f"truth_layer IN ({placeholders})")
                params.extend(layers)

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = (
                f"SELECT * FROM tactical_discourse_claims {where_sql} "
                f"ORDER BY truth_layer ASC, claim_id ASC LIMIT ?"
            )
            params.append(limit)

            cur = conn.cursor()
            cur.execute(sql, params)
            results: List[Dict[str, Any]] = []
            for r in cur.fetchall():
                d = dict(r)
                d["players_mentioned"] = json.loads(d.pop("players_mentioned_json") or "[]")
                results.append(d)
            return results
        finally:
            conn.close()

    def count_by_team_and_layer(self) -> Dict[str, Dict[int, int]]:
        """Return summary counts of stored claims grouped by team_id and truth_layer."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT team_id, truth_layer, COUNT(*)
                FROM tactical_discourse_claims
                GROUP BY team_id, truth_layer
                ORDER BY team_id, truth_layer
                """,
            )
            summary: Dict[str, Dict[int, int]] = {}
            for tid, layer, cnt in cur.fetchall():
                summary.setdefault(tid, {})[int(layer)] = int(cnt)
            return summary
        finally:
            conn.close()


class DiscourseLayerDecomposer:
    """
    Hybrid 7-layer discourse separator:
    Uses Gemini structured extraction when available and enabled,
    gracefully falling back to deterministic linguistic classification.
    """

    def __init__(
        self,
        gemini_client: Optional[GeminiTacticalClient] = None,
        club_profiles: Optional[Dict[str, Dict[str, Any]]] = None,
        use_gemini: bool = True,
    ) -> None:
        self.client = gemini_client or GeminiTacticalClient()
        self.club_profiles = club_profiles or {}
        self.use_gemini = use_gemini

    def _detect_entities_in_quote(
        self,
        quote: str,
        candidate_team_ids: List[str],
    ) -> Tuple[str, str, List[str]]:
        """Identify primary team_id, manager, and players mentioned in a quote."""
        best_team = candidate_team_ids[0] if candidate_team_ids else "FCT"
        best_score = -1
        matched_mgr = ""
        matched_players: List[str] = []

        search_ids = candidate_team_ids or list(self.club_profiles.keys())
        for tid in search_ids:
            prof = self.club_profiles.get(tid)
            if not prof:
                continue
            hits = sum(1 for kw in prof.get("entity_keywords", []) if kw in quote)
            if hits > best_score:
                best_score = hits
                best_team = tid

        prof = self.club_profiles.get(best_team, {})
        mgr = prof.get("current_manager", "")
        if mgr:
            mgr_parts = [p for p in mgr.split(" ") if len(p) >= 2]
            if any(p in quote for p in [mgr.replace(" ", ""), *mgr_parts]):
                matched_mgr = mgr

        for pl in prof.get("key_players", []):
            pl_parts = [p for p in pl.split(" ") if len(p) >= 2]
            if any(p in quote for p in [pl.replace(" ", ""), *pl_parts]):
                matched_players.append(pl)

        return (best_team, matched_mgr, matched_players[:5])

    def _build_claim_record(
        self,
        segment: Dict[str, Any],
        team_id: str,
        truth_layer: int,
        statement_text: str,
        original_quote: str,
        manager_mentioned: str,
        players_mentioned: List[str],
        method: str,
    ) -> Dict[str, Any]:
        """Format standardized 7-layer claim dict with provenance metadata."""
        clamped_layer = max(1, min(7, int(truth_layer)))
        reliability = (
            "YOUTUBE_REPORTED_FACT" if clamped_layer == 1 else "MEDIA_DISCOURSE"
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        seg_id = segment["segment_id"]

        return {
            "claim_id": compute_claim_id(seg_id, team_id, clamped_layer, original_quote),
            "segment_id": seg_id,
            "video_id": segment["video_id"],
            "channel_name": segment["channel_name"],
            "video_title": segment["video_title"],
            "video_url": segment["video_url"],
            "time_range": segment["time_range"],
            "team_id": team_id,
            "manager_mentioned": manager_mentioned,
            "players_mentioned": players_mentioned,
            "truth_layer": clamped_layer,
            "layer_name": LAYER_NAMES[clamped_layer],
            "source_reliability": reliability,
            "statement_text": statement_text.strip(),
            "original_quote": original_quote.strip(),
            "extraction_method": method,
            "created_at": now_iso,
        }

    def _decompose_via_gemini(
        self,
        segment: Dict[str, Any],
        candidate_team_ids: List[str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Attempt structured 7-layer extraction via Gemini API."""
        if not self.use_gemini or not self.client.is_available() or self.client.mock_mode:
            return None

        club_hint_lines = []
        for tid in candidate_team_ids:
            p = self.club_profiles.get(tid, {})
            roster_str = "、".join(p.get("key_players", [])[:14])
            club_hint_lines.append(
                f"- {tid}: {p.get('canonical_name', tid)} "
                f"(現監督: {p.get('current_manager', '不明')} | 所属主力: {roster_str})",
            )
        clubs_context = "\n".join(club_hint_lines) if club_hint_lines else "- FCT: FC東京"

        user_prompt = (
            f"【動画タイトル】: {segment['video_title']}\n"
            f"【チャンネル】: {segment['channel_name']} ({segment['time_range']})\n"
            f"【候補クラブID一覧】:\n{clubs_context}\n\n"
            f"【対象セグメント発言全文】:\n{segment['verbatim_text']}\n"
        )

        raw_json = self.client.generate_structured(
            system_prompt=DECOMPOSER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=GEMINI_RESPONSE_SCHEMA,
            temperature=0.1,
        )
        if not raw_json:
            return None

        try:
            parsed = json.loads(raw_json)
            raw_claims = parsed.get("claims", [])
        except Exception as e:
            logger.warning("Failed to parse Gemini structured claims JSON: %s", e)
            return None

        records: List[Dict[str, Any]] = []
        default_tid = candidate_team_ids[0] if candidate_team_ids else "FCT"
        valid_ids = set(self.club_profiles.keys()) | set(candidate_team_ids) | {"FCT"}

        for item in raw_claims:
            quote = str(item.get("original_quote", "")).strip()
            stmt = str(item.get("statement_text", "")).strip()
            if len(quote) < 10 or len(stmt) < 10:
                continue

            tid = str(item.get("team_id", default_tid)).strip()
            if tid not in valid_ids:
                tid = default_tid

            records.append(
                self._build_claim_record(
                    segment=segment,
                    team_id=tid,
                    truth_layer=int(item.get("truth_layer", 3)),
                    statement_text=stmt,
                    original_quote=quote,
                    manager_mentioned=str(item.get("manager_mentioned", "")).strip(),
                    players_mentioned=list(item.get("players_mentioned", [])),
                    method="gemini_structured",
                ),
            )

        return records if records else None

    def _decompose_deterministic(
        self,
        segment: Dict[str, Any],
        candidate_team_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Fallback deterministic sentence/unit splitter and 7-layer classifier."""
        units = split_into_discourse_units(segment.get("verbatim_text", ""))
        records: List[Dict[str, Any]] = []

        for unit in units:
            layer = classify_unit_layer_deterministic(
                unit_text=unit,
                video_title=segment.get("video_title", ""),
            )
            tid, mgr, players = self._detect_entities_in_quote(unit, candidate_team_ids)
            records.append(
                self._build_claim_record(
                    segment=segment,
                    team_id=tid,
                    truth_layer=layer,
                    statement_text=unit,
                    original_quote=unit,
                    manager_mentioned=mgr,
                    players_mentioned=players,
                    method="deterministic_rule",
                ),
            )

        return records

    def decompose_segment(
        self,
        segment: Dict[str, Any],
        candidate_team_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Decompose a single transcript segment into Layer 1..7 claim records."""
        cands = candidate_team_ids or ["FCT"]
        gemini_records = self._decompose_via_gemini(segment, cands)
        if gemini_records is not None:
            return gemini_records
        return self._decompose_deterministic(segment, cands)

