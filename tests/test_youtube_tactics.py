"""
tests/test_youtube_tactics.py

Unit tests for YouTube tactical channel ingestion (14 channels, lockupViewModel + search)
and team profile merging.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ingest_youtube_tactics import (
    CONFIG_PATH,
    PROFILES_PATH,
    YouTubeTacticalIngester,
    clean_transcript_text,
    extract_video_candidates_from_html,
    load_json_safely,
    save_json_safely,
)


class TestYouTubeTacticsIngester(unittest.TestCase):
    """Test suite for YouTubeTacticalIngester."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.config_path = self.test_root / "channels.json"
        self.history_path = self.test_root / "history.json"
        self.raw_dir = self.test_root / "raw"
        self.profiles_path = self.test_root / "profiles.json"

        mock_config = {
            "channels": [
                {
                    "channel_id": "test_ch_1",
                    "name": "Test Channel 1",
                    "url": "https://www.youtube.com/@test1",
                    "priority": 1,
                    "scan_mode": "FULL_CHANNEL",
                    "target_teams": ["FCT"],
                },
            ],
        }
        save_json_safely(self.config_path, mock_config)

        mock_profiles = {
            "teams": {
                "FCT": {
                    "team_id": "FCT",
                    "team_name": "FC東京",
                    "manager": "松橋 力蔵",
                    "base_formation": "4-2-1-3",
                    "evidences": [],
                },
            },
        }
        save_json_safely(self.profiles_path, mock_profiles)

        self.ingester = YouTubeTacticalIngester(
            config_path=self.config_path,
            history_path=self.history_path,
            raw_dir=self.raw_dir,
            profiles_path=self.profiles_path,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_extract_video_candidates_regex_fallback(self) -> None:
        html_sample = (
            "<div>"
            '"videoId":"abcdefghijk","title":{"runs":[{"text":"FC東京のハイライン戦術を徹底分析"}]}'
            '"videoId":"lmnopqrstuv","title":{"runs":[{"text":"町田ゼルビアのロングスロー対策"}]}'
            '"videoId":"abcdefghijk"'
            "</div>"
        )
        candidates = extract_video_candidates_from_html(html_sample)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0], ("abcdefghijk", "FC東京のハイライン戦術を徹底分析"))
        self.assertEqual(candidates[1], ("lmnopqrstuv", "町田ゼルビアのロングスロー対策"))

    def test_extract_video_candidates_lockup_view_model(self) -> None:
        yt_data = {
            "contents": [
                {
                    "richItemRenderer": {
                        "content": {
                            "lockupViewModel": {
                                "contentId": "v0z4_OY9txA",
                                "metadata": {
                                    "lockupMetadataViewModel": {
                                        "title": {
                                            "content": "第10節ヴェルディ戦 完全試合すぎて伝説になるダービー爆勝【FC東京26-27】",
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            ],
        }
        html_sample = f"<script>var ytInitialData = {json.dumps(yt_data, ensure_ascii=False)};</script>"
        candidates = extract_video_candidates_from_html(html_sample)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "v0z4_OY9txA")
        self.assertIn("FC東京26-27", candidates[0][1])

    def test_clean_transcript_text(self) -> None:
        raw_transcript = [
            {"text": "こんにちは。", "start": 0.0, "duration": 1.5},
            {"text": "今回はFC東京の", "start": 1.5, "duration": 2.0},
            {"text": "守備戦術について話します。", "start": 3.5, "duration": 2.5},
        ]
        merged = clean_transcript_text(raw_transcript)
        self.assertEqual(merged, "こんにちは。 今回はFC東京の 守備戦術について話します。")

    def test_history_recording_and_deduplication(self) -> None:
        self.assertFalse(self.ingester.is_video_processed("vid_1234567"))

        self.ingester.record_history(
            video_id="vid_1234567",
            channel_id="test_ch_1",
            title="Sample Tactical Review",
            status="SUCCESS",
        )
        self.assertTrue(self.ingester.is_video_processed("vid_1234567"))

        reloaded = YouTubeTacticalIngester(
            config_path=self.config_path,
            history_path=self.history_path,
            raw_dir=self.raw_dir,
            profiles_path=self.profiles_path,
        )
        self.assertTrue(reloaded.is_video_processed("vid_1234567"))

    def test_extract_tactical_insights_rule_based(self) -> None:
        sample_text = (
            "松橋力蔵監督率いるFC東京は、稲村とショルツのビルドアップから"
            "マルセロ・ヒアンの裏抜けを起点とした速い前進を試みます。"
        )
        title = "【戦術解説】FC東京の攻撃構造と力蔵サッカー"

        insights = self.ingester.extract_tactical_insights_rule_based(
            transcript_text=sample_text,
            video_title=title,
        )
        self.assertTrue(any(ins["team_id"] == "FCT" for ins in insights))
        fct_insight = [ins for ins in insights if ins["team_id"] == "FCT"][0]
        self.assertEqual(fct_insight["team_name"], "FC東京")
        self.assertIn("松橋", fct_insight["matched_keywords"])

    def test_merge_evidence_into_profiles_idempotent(self) -> None:
        insights = [
            {
                "team_id": "FCT",
                "team_name": "FC東京",
                "matched_keywords": ["松橋", "FC東京"],
                "key_quote": "ハイプレスからのショートカウンターが生命線",
                "confidence": "HIGH",
            },
        ]

        self.ingester.merge_evidence_into_profiles(
            insights=insights,
            video_id="test_vid_001",
            video_title="FC東京レビュー",
            channel_name="トーキョウ二元論",
        )

        profiles = load_json_safely(self.profiles_path)
        fct_evidences = profiles["teams"]["FCT"]["evidences"]
        self.assertEqual(len(fct_evidences), 1)

        self.ingester.merge_evidence_into_profiles(
            insights=insights,
            video_id="test_vid_001",
            video_title="FC東京レビュー",
            channel_name="トーキョウ二元論",
        )
        profiles_after = load_json_safely(self.profiles_path)
        self.assertEqual(len(profiles_after["teams"]["FCT"]["evidences"]), 1)

    def test_production_config_schema_14_channels(self) -> None:
        """Verify production config/youtube_tactical_channels.json has all 14 channels & scan modes."""
        self.assertTrue(CONFIG_PATH.exists())
        config = load_json_safely(CONFIG_PATH)
        channels = config.get("channels", [])
        self.assertEqual(len(channels), 14)

        by_id = {c["channel_id"]: c for c in channels}
        expected_ids = [
            "tokyo_nigennron",
            "tokyo_overlay",
            "damedafootball",
            "J1zenbumiru",
            "ryoheihayashi",
            "narahashidaigomi",
            "jri_gunonakanohito",
            "MILKsoccer_academy",
            "FootballZONEweb",
            "jron",
            "purechan",
            "leothefootballtv",
            "goatfootball",
            "shukyu_meganes",
        ]
        for cid in expected_ids:
            self.assertIn(cid, by_id)

        # Ensure full scan mode on the 3 dedicated/full-target channels
        self.assertEqual(by_id["tokyo_nigennron"]["scan_mode"], "FULL_CHANNEL")
        self.assertEqual(by_id["tokyo_overlay"]["scan_mode"], "FULL_CHANNEL")
        self.assertEqual(by_id["damedafootball"]["scan_mode"], "FULL_CHANNEL")

    def test_production_team_tactical_profiles_schema(self) -> None:
        """Verify production knowledge/team_tactical_profiles.json is valid."""
        self.assertTrue(PROFILES_PATH.exists())
        data = load_json_safely(PROFILES_PATH)
        teams = data.get("teams", {})
        self.assertIn("FCT", teams)
        self.assertEqual(teams["FCT"]["manager"], "松橋 力蔵")


if __name__ == "__main__":
    unittest.main()
