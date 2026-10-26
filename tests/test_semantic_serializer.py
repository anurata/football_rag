"""
Unit tests for pipeline/semantic_serializer.py.
Validates coordinate-to-zone translation and 4 standardized chunks serialization.
"""

import unittest
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)
from pipeline.semantic_serializer import (
    SemanticSerializer,
    get_x_zone,
    get_y_zone,
    get_tactical_zone,
)


class TestSemanticSerializer(unittest.TestCase):
    """Test suite for coordinate translation and tactical chunk serialization."""

    def setUp(self):
        self.serializer = SemanticSerializer()

    def test_coordinate_zone_mappings(self):
        """Verify 100x100 normalized coordinates translate into tactical zones."""
        # X-axis tests
        self.assertEqual(get_x_zone(15.0), "自陣ビルドアップ")
        self.assertEqual(get_x_zone(33.0), "自陣ビルドアップ")
        self.assertEqual(get_x_zone(50.0), "ミドルゾーン")
        self.assertEqual(get_x_zone(66.0), "ミドルゾーン")
        self.assertEqual(get_x_zone(75.0), "ファイナルサード")
        self.assertEqual(get_x_zone(83.0), "ファイナルサード")
        self.assertEqual(get_x_zone(90.0), "ボックス内・ゴール前")
        self.assertEqual(get_x_zone(100.0), "ボックス内・ゴール前")
        self.assertEqual(get_x_zone(None), "エリア不明")

        # Y-axis tests
        self.assertEqual(get_y_zone(10.0), "右大外")
        self.assertEqual(get_y_zone(20.0), "右大外")
        self.assertEqual(get_y_zone(30.0), "右ハーフスペース")
        self.assertEqual(get_y_zone(38.0), "右ハーフスペース")
        self.assertEqual(get_y_zone(50.0), "中央（バイタル）")
        self.assertEqual(get_y_zone(61.0), "中央（バイタル）")
        self.assertEqual(get_y_zone(70.0), "左ハーフスペース")
        self.assertEqual(get_y_zone(79.0), "左ハーフスペース")
        self.assertEqual(get_y_zone(90.0), "左大外")
        self.assertEqual(get_y_zone(None), "レーン不明")

        # Combined tactical zone
        self.assertEqual(
            get_tactical_zone(75.0, 70.0),
            "ファイナルサード・左ハーフスペース",
        )
        self.assertEqual(
            get_tactical_zone(92.0, 50.0),
            "ボックス内・ゴール前・中央（バイタル）",
        )
        self.assertEqual(get_tactical_zone(None, 50.0), "位置不明")

    def _build_test_bundle(self) -> MatchBundleModel:
        """Create sample match bundle for testing serialization."""
        match = MatchModel(
            match_id="20261021_FCT_KAS",
            season=2026,
            matchweek=34,
            date="2026-10-21",
            home_team_id="FCT",
            away_team_id="KAS",
            home_score=2,
            away_score=1,
            stadium="味の素スタジアム",
            weather="晴",
            pitch_condition="良芝",
        )

        team_stats = [
            TeamMatchStatsModel(
                match_id=match.match_id,
                team_id="FCT",
                period="ALL",
                possession=55.4,
                xg=2.15,
                shots=15,
                shots_on_target=6,
                big_chances=3,
                final_third_passes=88,
                total_distance_km=114.2,
                sprints=135,
            ),
            TeamMatchStatsModel(
                match_id=match.match_id,
                team_id="KAS",
                period="ALL",
                possession=44.6,
                xg=1.05,
                shots=8,
                shots_on_target=3,
                big_chances=1,
                final_third_passes=54,
                total_distance_km=112.8,
                sprints=122,
            ),
            TeamMatchStatsModel(
                match_id=match.match_id,
                team_id="FCT",
                period="1H",
                possession=58.0,
                xg=1.20,
                shots=8,
            ),
            TeamMatchStatsModel(
                match_id=match.match_id,
                team_id="KAS",
                period="1H",
                possession=42.0,
                xg=0.35,
                shots=3,
            ),
            TeamMatchStatsModel(
                match_id=match.match_id,
                team_id="FCT",
                period="2H",
                possession=52.8,
                xg=0.95,
                shots=7,
            ),
            TeamMatchStatsModel(
                match_id=match.match_id,
                team_id="KAS",
                period="2H",
                possession=47.2,
                xg=0.70,
                shots=5,
            ),
        ]

        player_stats = [
            PlayerMatchStatsModel(
                match_id=match.match_id,
                player_name="小泉 慶",
                team_id="FCT",
                is_starter=True,
                position="MF",
                avg_x=52.5,
                avg_y=48.0,
            ),
            PlayerMatchStatsModel(
                match_id=match.match_id,
                player_name="俵積田 晃太",
                team_id="FCT",
                is_starter=True,
                position="FW",
                avg_x=72.0,
                avg_y=85.0,
            ),
            PlayerMatchStatsModel(
                match_id=match.match_id,
                player_name="鈴木 優磨",
                team_id="KAS",
                is_starter=True,
                position="FW",
                avg_x=68.0,
                avg_y=50.0,
            ),
        ]

        events = [
            MatchEventModel(
                event_id="EV_01",
                match_id=match.match_id,
                minute=12,
                period="1H",
                team_id="FCT",
                player_name="俵積田 晃太",
                event_type="SHOT",
                coord_x=75.0,
                coord_y=72.0,
                xg=0.12,
                description_text="左サイドからの鋭いカットインシュート",
            ),
            MatchEventModel(
                event_id="EV_02",
                match_id=match.match_id,
                minute=34,
                period="1H",
                team_id="FCT",
                player_name="ディエゴ オリヴェイラ",
                event_type="GOAL",
                coord_x=91.0,
                coord_y=51.0,
                xg=0.48,
                description_text="中央でのラストパスを落ち着いて流し込む",
            ),
            MatchEventModel(
                event_id="EV_03",
                match_id=match.match_id,
                minute=68,
                period="2H",
                team_id="KAS",
                player_name="知念 慶",
                event_type="GOAL",
                coord_x=88.0,
                coord_y=46.0,
                xg=0.35,
                description_text="CKのこぼれ球をボレーで押し込む",
            ),
        ]

        reviews = [
            MatchReviewModel(
                match_id=match.match_id,
                review_type="OFFICIAL_REPORT",
                title="首位攻防戦を制したFC東京が勝点3を獲得",
                content_text="立ち上がりから前線プレスが機能したFC東京が主導権を握った。",
            ),
            MatchReviewModel(
                match_id=match.match_id,
                review_type="HOME_COACH",
                speaker_name="クラモフスキー",
                speaker_team_id="FCT",
                title="プラン通りの積極的なプレスが実を結んだ",
                content_text="選手たちが規律を守り、左サイドからの前進を効果的に実行してくれた。",
            ),
            MatchReviewModel(
                match_id=match.match_id,
                review_type="AWAY_COACH",
                speaker_name="ポポヴィッチ",
                speaker_team_id="KAS",
                title="前半の立ち上がりに相手の勢いに飲まれた",
                content_text="後半は修正して押し込めたが、前半の失点が重くのしかかった。",
            ),
            MatchReviewModel(
                match_id=match.match_id,
                review_type="HOME_PLAYER",
                speaker_name="小泉 慶",
                speaker_team_id="FCT",
                title="中盤でのセカンドボール争いで優位に立てた",
                content_text="相手のボランチに対して常に先手を打ってアプローチできた。",
            ),
        ]

        return MatchBundleModel(
            match=match,
            team_stats=team_stats,
            player_stats=player_stats,
            events=events,
            reviews=reviews,
        )

    def test_serialize_bundle_returns_exact_4_chunks(self):
        """Bundle serialization must yield exactly 4 distinct chunks."""
        bundle = self._build_test_bundle()
        chunks = self.serializer.serialize_bundle(bundle)

        self.assertEqual(len(chunks), 4, "Must produce exactly 4 chunks")
        chunk_types = [c.chunk_type for c in chunks]
        expected_types = [
            "match_summary_and_stats",
            "tactical_timeline_and_zones",
            "manager_interviews",
            "player_interviews",
        ]
        self.assertEqual(chunk_types, expected_types)

        # Check chunk_id format
        for c in chunks:
            self.assertTrue(c.chunk_id.startswith(bundle.match.match_id))
            self.assertEqual(c.match_id, bundle.match.match_id)
            self.assertIn("teams", c.metadata)
            self.assertEqual(c.metadata["teams"], "FCT vs KAS")

    def test_chunk1_summary_and_stats_content(self):
        """Verify chunk 1 contents: official report and markdown stats table."""
        bundle = self._build_test_bundle()
        chunk = self.serializer.serialize_summary_and_stats_chunk(bundle)

        self.assertIn("首位攻防戦を制したFC東京", chunk.content)
        self.assertIn("ポゼッション率 (%)", chunk.content)
        self.assertIn("ゴール期待値 (xG)", chunk.content)
        self.assertIn("55.4", chunk.content)
        self.assertIn("114.2", chunk.content)
        self.assertIn("フルタイム (90分)", chunk.content)
        self.assertIn("前半 (1H)", chunk.content)
        self.assertIn("後半 (2H)", chunk.content)

    def test_chunk2_tactical_timeline_content(self):
        """Verify chunk 2 contents: 15-min phases and tactical zones."""
        bundle = self._build_test_bundle()
        chunk = self.serializer.serialize_tactical_timeline_chunk(bundle)

        self.assertIn("第1フェーズ (0〜15分)", chunk.content)
        self.assertIn("第3フェーズ (31〜45分+)", chunk.content)
        self.assertIn("第5フェーズ (61〜75分)", chunk.content)
        self.assertIn("俵積田 晃太", chunk.content)
        self.assertIn("ファイナルサード・左ハーフスペース", chunk.content)
        self.assertIn("ボックス内・ゴール前・中央（バイタル）", chunk.content)
        self.assertIn("チーム重心", chunk.content)
        self.assertIn("小泉 慶", chunk.content)

    def test_chunk3_manager_interviews_content(self):
        """Verify chunk 3 contents: coach comments."""
        bundle = self._build_test_bundle()
        chunk = self.serializer.serialize_manager_interviews_chunk(bundle)

        self.assertIn("クラモフスキー 監督", chunk.content)
        self.assertIn("ポポヴィッチ 監督", chunk.content)
        self.assertIn("プラン通りの積極的なプレス", chunk.content)
        self.assertIn("前半の立ち上がりに相手の勢いに飲まれた", chunk.content)

    def test_chunk4_player_interviews_content(self):
        """Verify chunk 4 contents: player comments."""
        bundle = self._build_test_bundle()
        chunk = self.serializer.serialize_player_interviews_chunk(bundle)

        self.assertIn("小泉 慶 選手", chunk.content)
        self.assertIn("中盤でのセカンドボール争いで優位に立てた", chunk.content)


if __name__ == "__main__":
    unittest.main()
