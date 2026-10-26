"""
Semantic serializer for football match data.
Converts normalized coordinates (x, y) and match stats into rich tactical narratives
and generates 4 standardized chunks per match for vector indexing.
"""

from typing import List, Optional, Dict, Any
from pipeline.models import (
    MatchBundleModel,
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    SerializedChunkModel,
)


def get_x_zone(x: Optional[float]) -> str:
    """Translate normalized X coordinate (0-100) to longitudinal zone name."""
    if x is None:
        return "エリア不明"
    if x <= 33.0:
        return "自陣ビルドアップ"
    if x <= 66.0:
        return "ミドルゾーン"
    if x <= 83.0:
        return "ファイナルサード"
    return "ボックス内・ゴール前"


def get_y_zone(y: Optional[float]) -> str:
    """Translate normalized Y coordinate (0-100) to lateral zone name."""
    if y is None:
        return "レーン不明"
    if y <= 20.0:
        return "右大外"
    if y <= 38.0:
        return "右ハーフスペース"
    if y <= 61.0:
        return "中央（バイタル）"
    if y <= 79.0:
        return "左ハーフスペース"
    return "左大外"


def get_tactical_zone(x: Optional[float], y: Optional[float]) -> str:
    """Combine X and Y into a tactical zone name."""
    if x is None or y is None:
        return "位置不明"
    x_name = get_x_zone(x)
    y_name = get_y_zone(y)
    return f"{x_name}・{y_name}"


def _format_stat_row(label: str, home_val: Any, away_val: Any) -> str:
    """Helper to format a single markdown table row."""
    h_str = "-" if home_val is None else str(home_val)
    a_str = "-" if away_val is None else str(away_val)
    return f"| {label} | {h_str} | {a_str} |\n"


def format_stats_table(bundle: MatchBundleModel) -> str:
    """Generate Markdown comparison tables for full match, 1st half, and 2nd half stats."""
    home_id = bundle.match.home_team_id
    away_id = bundle.match.away_team_id

    periods = ["ALL", "1H", "2H"]
    period_labels = {
        "ALL": "フルタイム (90分)",
        "1H": "前半 (1H)",
        "2H": "後半 (2H)",
    }

    lines = []
    for p in periods:
        h_stats = next(
            (s for s in bundle.team_stats if s.team_id == home_id and s.period == p),
            None,
        )
        a_stats = next(
            (s for s in bundle.team_stats if s.team_id == away_id and s.period == p),
            None,
        )

        lines.append(f"#### ■ スタッツ比較: {period_labels[p]}\n\n")
        lines.append(f"| 指標 | {home_id} (HOME) | {away_id} (AWAY) |\n")
        lines.append("| :--- | :---: | :---: |\n")

        lines.append(
            _format_stat_row(
                "ポゼッション率 (%)",
                None if not h_stats else h_stats.possession,
                None if not a_stats else a_stats.possession,
            ),
        )
        lines.append(
            _format_stat_row(
                "ゴール期待値 (xG)",
                None if not h_stats else h_stats.xg,
                None if not a_stats else a_stats.xg,
            ),
        )
        lines.append(
            _format_stat_row(
                "シュート数",
                None if not h_stats else h_stats.shots,
                None if not a_stats else a_stats.shots,
            ),
        )
        lines.append(
            _format_stat_row(
                "枠内シュート数",
                None if not h_stats else h_stats.shots_on_target,
                None if not a_stats else a_stats.shots_on_target,
            ),
        )
        lines.append(
            _format_stat_row(
                "ビッグチャンス数",
                None if not h_stats else h_stats.big_chances,
                None if not a_stats else a_stats.big_chances,
            ),
        )
        lines.append(
            _format_stat_row(
                "敵陣パス成功数",
                None if not h_stats else h_stats.final_third_passes,
                None if not a_stats else a_stats.final_third_passes,
            ),
        )
        lines.append(
            _format_stat_row(
                "総走行距離 (km)",
                None if not h_stats else h_stats.total_distance_km,
                None if not a_stats else a_stats.total_distance_km,
            ),
        )
        lines.append(
            _format_stat_row(
                "スプリント回数",
                None if not h_stats else h_stats.sprints,
                None if not a_stats else a_stats.sprints,
            ),
        )
        lines.append("\n")

    return "".join(lines)


def _get_phase_index(minute: Optional[int]) -> int:
    """Classify match minute into 6 distinct 15-minute phases (0 to 5)."""
    if minute is None:
        return 0
    if minute <= 15:
        return 0
    if minute <= 30:
        return 1
    if minute <= 45:
        return 2
    if minute <= 60:
        return 3
    if minute <= 75:
        return 4
    return 5


def format_timeline_phases(bundle: MatchBundleModel) -> str:
    """Format match events into 6 distinct 15-minute chronological phases."""
    phase_names = [
        "第1フェーズ (0〜15分): 立ち上がり・配置の探り合い",
        "第2フェーズ (16〜30分): 序盤の主導権争いと構造的攻防",
        "第3フェーズ (31〜45分+): 前半終盤の攻防と先制点の攻防",
        "第4フェーズ (46〜60分): 後半立ち上がり・修正の衝突",
        "第5フェーズ (61〜75分): ベンチワーク・交代カードの投入",
        "第6フェーズ (76〜90分+): 終盤の総力戦・リスクテイク",
    ]

    phase_events: List[List[MatchEventModel]] = [[] for _ in range(6)]
    for ev in bundle.events:
        idx = _get_phase_index(ev.minute)
        phase_events[idx].append(ev)

    lines = ["### ■ 15分刻みタイムライン展開と重要イベント\n\n"]
    for i, p_title in enumerate(phase_names):
        lines.append(f"#### {p_title}\n")
        events_in_phase = phase_events[i]
        if not events_in_phase:
            lines.append("- 特筆すべき決定機やイベントなし（膠着状態）\n\n")
            continue

        for ev in sorted(events_in_phase, key=lambda e: e.minute or 0):
            min_str = f"{ev.minute}分" if ev.minute is not None else "時間未定"
            team_str = f"[{ev.team_id}]" if ev.team_id else ""
            zone_desc = f" ({ev.zone_name})" if ev.zone_name else ""
            if not zone_desc and ev.coord_x is not None and ev.coord_y is not None:
                zone_desc = f" ({get_tactical_zone(ev.coord_x, ev.coord_y)})"

            xg_desc = f" [xG: {ev.xg:.2f}]" if ev.xg is not None else ""
            desc = f": {ev.description_text}" if ev.description_text else ""
            player = f" {ev.player_name}" if ev.player_name else ""

            lines.append(f"- **{min_str}** {team_str} {ev.event_type}{player}{zone_desc}{xg_desc}{desc}\n")
        lines.append("\n")

    return "".join(lines)


def format_formation_and_zones(bundle: MatchBundleModel) -> str:
    """Summarize tactical formation bias and average positions from player stats."""
    home_id = bundle.match.home_team_id
    away_id = bundle.match.away_team_id

    lines = ["### ■ 実質平均ポジションと攻撃偏重エリア分析\n\n"]

    for team_id in [home_id, away_id]:
        players = [
            p for p in bundle.player_stats
            if p.team_id == team_id and p.is_starter and p.avg_x is not None and p.avg_y is not None
        ]
        if not players:
            lines.append(f"#### 【{team_id}】平均座標データ未登録\n\n")
            continue

        avg_team_x = sum(p.avg_x for p in players) / len(players)
        avg_team_y = sum(p.avg_y for p in players) / len(players)

        # Lateral zone bias
        left_count = sum(1 for p in players if p.avg_y >= 62.0)
        center_count = sum(1 for p in players if 39.0 <= p.avg_y <= 61.0)
        right_count = sum(1 for p in players if p.avg_y <= 38.0)

        bias = "中央バランス型"
        if left_count >= right_count + 2:
            bias = "左サイド偏重アタック"
        elif right_count >= left_count + 2:
            bias = "右サイド偏重アタック"

        lines.append(f"#### 【{team_id}】\n")
        lines.append(
            f"- **チーム重心 (平均X / 平均Y)**: {avg_team_x:.1f} ({get_x_zone(avg_team_x)}) / "
            f"{avg_team_y:.1f} ({get_y_zone(avg_team_y)})\n",
        )
        lines.append(f"- **攻撃サイド傾向**: {bias} (左: {left_count}人, 中央: {center_count}人, 右: {right_count}人)\n")
        lines.append("- **先発主力選手の戦術ゾーン配置**:\n")

        for p in sorted(players, key=lambda x: x.avg_x or 0, reverse=True):
            zone = get_tactical_zone(p.avg_x, p.avg_y)
            pos_label = f" ({p.position})" if p.position else ""
            lines.append(
                f"  - {p.player_name}{pos_label}: 平均座標({p.avg_x:.1f}, {p.avg_y:.1f}) -> {zone}\n",
            )
        lines.append("\n")

    return "".join(lines)


def format_manager_interviews(bundle: MatchBundleModel) -> str:
    """Format manager interviews and match reviews into structured text."""
    coach_reviews = [
        r for r in bundle.reviews
        if r.review_type in ["HOME_COACH", "AWAY_COACH"]
    ]
    if not coach_reviews:
        return "監督会見コメントは登録されていません。\n"

    lines = ["### ■ 監督試合後会見コメント全文・戦術的意図\n\n"]
    for r in coach_reviews:
        spk = r.speaker_name or "監督"
        team = f"[{r.speaker_team_id}] " if r.speaker_team_id else ""
        lines.append(f"#### {team}{spk} 監督\n")
        if r.title:
            lines.append(f"**見出し**: {r.title}\n\n")
        lines.append(f"{r.content_text.strip()}\n\n")

    return "".join(lines)


def format_player_interviews(bundle: MatchBundleModel) -> str:
    """Format player interviews into structured text."""
    player_reviews = [
        r for r in bundle.reviews
        if r.review_type in ["HOME_PLAYER", "AWAY_PLAYER"]
    ]
    if not player_reviews:
        return "選手試合後インタビューは登録されていません。\n"

    lines = ["### ■ 選手試合後インタビュー全文・ピッチ証言\n\n"]
    for r in player_reviews:
        spk = r.speaker_name or "選手"
        team = f"[{r.speaker_team_id}] " if r.speaker_team_id else ""
        lines.append(f"#### {team}{spk} 選手\n")
        if r.title:
            lines.append(f"**見出し**: {r.title}\n\n")
        lines.append(f"{r.content_text.strip()}\n\n")

    return "".join(lines)


class SemanticSerializer:
    """Serializes match data into 4 standardized chunks for vector search."""

    def _build_metadata(
        self,
        match: MatchModel,
        chunk_type: str,
        speaker_team: str = "BOTH",
        target_team: str = "ALL",
    ) -> Dict[str, Any]:
        """Construct common metadata dictionary for vector indexing."""
        return {
            "season": match.season,
            "matchweek": match.matchweek or 0,
            "match_id": match.match_id,
            "teams": f"{match.home_team_id} vs {match.away_team_id}",
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "chunk_type": chunk_type,
            "speaker_team": speaker_team,
            "target_team": target_team,
        }

    def serialize_summary_and_stats_chunk(self, bundle: MatchBundleModel) -> SerializedChunkModel:
        """Chunk 1: Official report narrative + match stats markdown comparison tables."""
        m = bundle.match
        report_review = next(
            (r for r in bundle.reviews if r.review_type == "OFFICIAL_REPORT"),
            None,
        )

        if report_review:
            report_body = []
            if report_review.title:
                report_body.append(f"**見出し**: {report_review.title}\n\n")
            report_body.append(report_review.content_text.strip())
            report_text = "".join(report_body)
        else:
            report_text = "公式マッチレポート本文未登録"

        header = (
            f"# 【試合概要・スタッツ】{m.season} J1 第{m.matchweek or '-'}節 "
            f"{m.home_team_id} vs {m.away_team_id}\n\n"
            f"- **スコア**: {m.home_team_id} {m.home_score if m.home_score is not None else '-'} - "
            f"{m.away_score if m.away_score is not None else '-'} {m.away_team_id}\n"
            f"- **開催日**: {m.date or '日程未定'}\n"
            f"- **スタジアム**: {m.stadium or '未定'} / 天候: {m.weather or '-'} / 芝: {m.pitch_condition or '-'}\n\n"
            f"### ■ 公式マッチレポート\n\n{report_text}\n\n"
        )


        stats_table = format_stats_table(bundle)
        content = header + stats_table

        metadata = self._build_metadata(
            match=m,
            chunk_type="match_summary_and_stats",
            speaker_team="BOTH",
            target_team="ALL",
        )

        return SerializedChunkModel(
            chunk_id=f"{m.match_id}_match_summary_and_stats",
            match_id=m.match_id,
            chunk_type="match_summary_and_stats",
            content=content,
            metadata=metadata,
        )

    def serialize_tactical_timeline_chunk(self, bundle: MatchBundleModel) -> SerializedChunkModel:
        """Chunk 2: 15-minute phase timeline + tactical zone positioning bias."""
        m = bundle.match
        header = (
            f"# 【戦術タイムライン・ゾーン推移】{m.season} J1 第{m.matchweek or '-'}節 "
            f"{m.home_team_id} vs {m.away_team_id}\n\n"
        )
        timeline_text = format_timeline_phases(bundle)
        formation_text = format_formation_and_zones(bundle)
        content = header + timeline_text + formation_text

        metadata = self._build_metadata(
            match=m,
            chunk_type="tactical_timeline_and_zones",
            speaker_team="BOTH",
            target_team="ALL",
        )

        return SerializedChunkModel(
            chunk_id=f"{m.match_id}_tactical_timeline_and_zones",
            match_id=m.match_id,
            chunk_type="tactical_timeline_and_zones",
            content=content,
            metadata=metadata,
        )

    def serialize_manager_interviews_chunk(self, bundle: MatchBundleModel) -> SerializedChunkModel:
        """Chunk 3: Both coaches' post-match interview transcripts."""
        m = bundle.match
        header = (
            f"# 【監督記者会見・戦術証言】{m.season} J1 第{m.matchweek or '-'}節 "
            f"{m.home_team_id} vs {m.away_team_id}\n\n"
        )
        interviews_text = format_manager_interviews(bundle)
        content = header + interviews_text

        metadata = self._build_metadata(
            match=m,
            chunk_type="manager_interviews",
            speaker_team="BOTH",
            target_team="ALL",
        )

        return SerializedChunkModel(
            chunk_id=f"{m.match_id}_manager_interviews",
            match_id=m.match_id,
            chunk_type="manager_interviews",
            content=content,
            metadata=metadata,
        )

    def serialize_player_interviews_chunk(self, bundle: MatchBundleModel) -> SerializedChunkModel:
        """Chunk 4: Players' post-match interview transcripts."""
        m = bundle.match
        header = (
            f"# 【選手インタビュー・ピッチ証言】{m.season} J1 第{m.matchweek or '-'}節 "
            f"{m.home_team_id} vs {m.away_team_id}\n\n"
        )
        interviews_text = format_player_interviews(bundle)
        content = header + interviews_text

        metadata = self._build_metadata(
            match=m,
            chunk_type="player_interviews",
            speaker_team="BOTH",
            target_team="ALL",
        )

        return SerializedChunkModel(
            chunk_id=f"{m.match_id}_player_interviews",
            match_id=m.match_id,
            chunk_type="player_interviews",
            content=content,
            metadata=metadata,
        )

    def serialize_bundle(self, bundle: MatchBundleModel) -> List[SerializedChunkModel]:
        """Serialize a full match bundle into exactly 4 standardized vector chunks."""
        return [
            self.serialize_summary_and_stats_chunk(bundle),
            self.serialize_tactical_timeline_chunk(bundle),
            self.serialize_manager_interviews_chunk(bundle),
            self.serialize_player_interviews_chunk(bundle),
        ]
