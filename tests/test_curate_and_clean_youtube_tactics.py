"""
tests/test_curate_and_clean_youtube_tactics.py

Unit tests for two-tier YouTube video curation, context inheritance,
derby-safe filtering, and transcript phonetic normalization.
"""

from __future__ import annotations

import unittest

from scripts.curate_and_clean_youtube_tactics import (
    TacticalTranscriptCurator,
    format_seconds,
    normalize_transcript_text,
)


class TestCurateAndCleanYouTubeTactics(unittest.TestCase):
    """Test suite for TacticalTranscriptCurator."""

    def test_format_seconds(self) -> None:
        self.assertEqual(format_seconds(0.0), "00:00")
        self.assertEqual(format_seconds(65.0), "01:05")
        self.assertEqual(format_seconds(1200.0), "20:00")

    def test_normalize_transcript_text(self) -> None:
        raw_text = "[音楽] エ東京のマルセロ批安が[笑い] カシーフからパスを受けてペナ角に侵入した。"
        normalized = normalize_transcript_text(raw_text)
        self.assertNotIn("[音楽]", normalized)
        self.assertNotIn("[笑い]", normalized)
        self.assertIn("FC東京", normalized)
        self.assertIn("マルセロ・ヒアン", normalized)
        self.assertIn("佳史扶", normalized)
        self.assertIn("ペナルティエリア角（ポケット）", normalized)

    def test_dedicated_video_preserves_subject_omitted_tactics(self) -> None:
        mock_transcript = [
            {"text": "FC東京の松橋監督が動きました。", "start": 5.0, "duration": 3.0},
            {"text": "マルセロ・ヒアンの裏抜けを狙ったビルドアップですね。", "start": 10.0, "duration": 4.0},
            # 70s-100s: Subject omitted, pure tactical analysis (must be kept in dedicated video!)
            {
                "text": "ボランチとセンターバックの距離感が良く、ハーフスペースへ前進できていました。",
                "start": 70.0,
                "duration": 5.0,
            },
            {
                "text": "相手のハイプレスに対してもロングボールとショートカウンターを使い分けていました。",
                "start": 80.0,
                "duration": 5.0,
            },
            # 160s: Non-tactical chat (must be dropped)
            {"text": "今日の天気は晴れで気持ちよかったですね。", "start": 160.0, "duration": 3.0},
        ]

        curator = TacticalTranscriptCurator()
        segments = curator.scan_video_hotspots(
            video_id="test_vid_123",
            channel_name="TOKYO OVERLAY",
            official_title="第12節 FC東京戦術レビュー",
            transcript=mock_transcript,
            window_duration=60.0,
            step_duration=30.0,
        )

        self.assertGreaterEqual(len(segments), 1)
        combined_text = " ".join(s["verbatim_text"] for s in segments)
        self.assertIn("マルセロ・ヒアン", combined_text)
        self.assertIn("ハーフスペースへ前進", combined_text)
        self.assertNotIn("今日の天気は晴れ", combined_text)

    def test_standalone_verdy_rejected_but_tokyo_derby_kept(self) -> None:
        curator = TacticalTranscriptCurator()

        # 1. Standalone Verdy -> Rejected
        verdy_only = [
            {"text": "東京ヴェルディの戦術について話します。", "start": 5.0, "duration": 3.0},
            {"text": "ヴェルディのハイプレスが機能していました。", "start": 10.0, "duration": 3.0},
        ]
        segs_verdy = curator.scan_video_hotspots(
            video_id="test_verdy",
            channel_name="テストチャンネル",
            official_title="ヴェルディレビュー",
            transcript=verdy_only,
        )
        self.assertEqual(len(segs_verdy), 0)

        # 2. Tokyo Derby (FC Tokyo vs Tokyo Verdy) -> Kept!
        derby_transcript = [
            {
                "text": "東京ダービーでFC東京が4対0で完勝しました。稲村のビルドアップとヒアンの裏抜けが完璧でした。",
                "start": 5.0,
                "duration": 6.0,
            },
            {
                "text": "ヴェルディのハイプレスをボランチとサイドバックの配置で完全に剥がしました。",
                "start": 15.0,
                "duration": 5.0,
            },
        ]
        segs_derby = curator.scan_video_hotspots(
            video_id="test_derby",
            channel_name="ダメだ！フットボール",
            official_title="第10節ヴェルディ戦 完全試合すぎて伝説になるダービー爆勝【FC東京26-27】",
            transcript=derby_transcript,
        )
        self.assertEqual(len(segs_derby), 1)
        self.assertIn("東京ダービー", segs_derby[0]["verbatim_text"])

    def test_outdated_pre2026_video_rejected(self) -> None:
        curator = TacticalTranscriptCurator()
        old_2023_transcript = [
            {
                "text": "FC東京はエンリケと木本のセンターバックでビルドアップし、オリヴェイラに縦パスを入れた。",
                "start": 5.0,
                "duration": 5.0,
            },
        ]
        segs_old = curator.scan_video_hotspots(
            video_id="test_old_2023",
            channel_name="テストチャンネル",
            official_title="J1第6節 サガン鳥栖 vs FC東京",
            transcript=old_2023_transcript,
        )
        self.assertEqual(len(segs_old), 0)


if __name__ == "__main__":
    unittest.main()
