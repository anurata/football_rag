"""RawMatchFetcher（生データ一括取得ツール）の単体テスト (tests/test_fetch_raw_matches.py)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pipeline.normalizer import EntityNormalizer
from pipeline.text_live_structurer import TextLiveStructurer
from scrapers.football_lab import FootballLabScraper
from scrapers.schedule_crawler import ScheduleCrawler
from scrapers.spaia_soccer import SpaiasoccerScraper
from scrapers.yahoo_soccer import YahooSoccerScraper
from scripts.fetch_raw_matches import (
    RawMatchFetcher,
    build_arg_parser,
    parse_matchweek_range,
)


class TestFetchRawMatches(unittest.TestCase):
    """RawMatchFetcherの動作検証テストケース."""

    def setUp(self) -> None:
        """テスト用の一時ディレクトリとモックを準備する."""
        self.test_dir = tempfile.mkdtemp()
        self.md_dir = os.path.join(self.test_dir, "markdown")
        self.raw_dir = os.path.join(self.test_dir, "raw")
        self.structured_dir = os.path.join(self.test_dir, "structured")

        self.mock_normalizer = MagicMock(spec=EntityNormalizer)
        self.mock_crawler = MagicMock(spec=ScheduleCrawler)
        self.mock_yahoo = MagicMock(spec=YahooSoccerScraper)
        self.mock_spaia = MagicMock(spec=SpaiasoccerScraper)
        self.mock_flab = MagicMock(spec=FootballLabScraper)
        self.mock_structurer = MagicMock(spec=TextLiveStructurer)

        # チーム名解決のモック
        self.mock_normalizer.normalize_team_name.side_effect = lambda x: (
            "FCT" if "東京" in str(x) else ("MIT" if "水戸" in str(x) else x)
        )

        self.fetcher = RawMatchFetcher(
            raw_dir=self.raw_dir,
            markdown_dir=self.md_dir,
            structured_dir=self.structured_dir,
            normalizer=self.mock_normalizer,
            schedule_crawler=self.mock_crawler,
            yahoo_scraper=self.mock_yahoo,
            spaia_scraper=self.mock_spaia,
            football_lab_scraper=self.mock_flab,
            text_live_structurer=self.mock_structurer,
        )

    def tearDown(self) -> None:
        """一時ディレクトリをクリーンアップする."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    # -------------------------------------------------------------------------
    # 節指定パースのテスト
    # -------------------------------------------------------------------------

    def test_parse_matchweek_range_single(self) -> None:
        """単一節指定 ('12') のパース検証."""
        start_mw, end_mw = parse_matchweek_range("12")
        self.assertEqual(start_mw, 12)
        self.assertEqual(end_mw, 12)

    def test_parse_matchweek_range_span(self) -> None:
        """範囲指定 ('1-12') のパース検証."""
        start_mw, end_mw = parse_matchweek_range("1-12")
        self.assertEqual(start_mw, 1)
        self.assertEqual(end_mw, 12)

    def test_parse_matchweek_range_none(self) -> None:
        """None指定時のデフォルト範囲検証."""
        start_mw, end_mw = parse_matchweek_range(None)
        self.assertEqual(start_mw, 1)
        self.assertEqual(end_mw, 38)

    # -------------------------------------------------------------------------
    # 試合ディスカバリ & フィルタリングのテスト
    # -------------------------------------------------------------------------

    def test_discover_matches_by_game_id(self) -> None:
        """game_id直接指定時のディスカバリ検証."""
        matches = self.fetcher.discover_matches(
            season=2026,
            game_id="2026102505",
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["game_id"], "2026102505")
        self.assertEqual(matches[0]["season"], 2026)

    def test_discover_matches_filter_team(self) -> None:
        """特定チーム（FC東京）によるフィルタリング検証."""
        self.mock_crawler.build_schedule.return_value = [
            {
                "year": 2026,
                "matchweek": 12,
                "mmdd": "1025",
                "daily_match_index": 5,
                "home_team_id": "FCT",
                "away_team_id": "MIT",
                "home_team_raw": "FC東京",
                "away_team_raw": "水戸",
            },
            {
                "year": 2026,
                "matchweek": 12,
                "mmdd": "1025",
                "daily_match_index": 2,
                "home_team_id": "NAG",
                "away_team_id": "YFM",
                "home_team_raw": "名古屋",
                "away_team_raw": "横浜FM",
            },
        ]

        matches = self.fetcher.discover_matches(
            season=2026,
            start_mw=12,
            end_mw=12,
            team_query="FC東京",
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["game_id"], "2026102505")
        self.assertEqual(matches[0]["home_team_id"], "FCT")

    # -------------------------------------------------------------------------
    # キャッシュ判定テスト
    # -------------------------------------------------------------------------

    def test_cache_detection(self) -> None:
        """キャッシュ存在判定のテスト."""
        game_id = "2026102505"

        # 初期状態は未キャッシュ
        self.assertFalse(self.fetcher.is_yahoo_cached(game_id))
        self.assertFalse(self.fetcher.is_spaia_cached(game_id))
        self.assertFalse(self.fetcher.is_football_lab_cached(game_id))

        # Yahooファイルを作成
        stats_path = os.path.join(self.fetcher.yahoo_dir, f"{game_id}_stats.json")
        text_path = os.path.join(self.fetcher.yahoo_dir, f"{game_id}_text.json")
        with open(stats_path, "w", encoding="utf-8") as f:
            f.write("x" * 200)
        with open(text_path, "w", encoding="utf-8") as f:
            f.write("x" * 200)

        self.assertTrue(self.fetcher.is_yahoo_cached(game_id))
        self.assertFalse(self.fetcher.is_spaia_cached(game_id))
        self.assertFalse(self.fetcher.is_football_lab_cached(game_id))

        # SPAIAファイルを作成
        comments_path = os.path.join(self.fetcher.spaia_dir, f"{game_id}_comments.json")
        player_path = os.path.join(self.fetcher.spaia_dir, f"{game_id}_player_stats.json")
        with open(comments_path, "w", encoding="utf-8") as f:
            f.write("x" * 200)
        with open(player_path, "w", encoding="utf-8") as f:
            f.write("x" * 200)

        self.assertTrue(self.fetcher.is_spaia_cached(game_id))

        # Football LABファイルを作成
        flab_json = os.path.join(self.fetcher.flab_dir, f"{game_id}.json")
        with open(flab_json, "w", encoding="utf-8") as f:
            f.write("x" * 200)

        self.assertTrue(self.fetcher.is_football_lab_cached(game_id))

    def test_should_fetch_game_logic(self) -> None:
        """should_fetch_gameの各種フラグ判定テスト."""
        game_id = "2026102505"

        # キャッシュなし -> 全3ソース必要
        need_y, need_s, need_f = self.fetcher.should_fetch_game(
            game_id,
            source="all",
            force=False,
        )
        self.assertTrue(need_y)
        self.assertTrue(need_s)
        self.assertTrue(need_f)

        # source="football_lab" のみ
        need_y, need_s, need_f = self.fetcher.should_fetch_game(
            game_id,
            source="football_lab",
            force=False,
        )
        self.assertFalse(need_y)
        self.assertFalse(need_s)
        self.assertTrue(need_f)

        # Football LABのみキャッシュ作成
        with open(os.path.join(self.fetcher.flab_dir, f"{game_id}.json"), "w") as f:
            f.write("x" * 200)

        # source="all" -> Yahoo/SPAIA必要、Football LAB不要
        need_y, need_s, need_f = self.fetcher.should_fetch_game(
            game_id,
            source="all",
            force=False,
        )
        self.assertTrue(need_y)
        self.assertTrue(need_s)
        self.assertFalse(need_f)

        # force=True -> キャッシュあっても全ソース必要
        need_y, need_s, need_f = self.fetcher.should_fetch_game(
            game_id,
            source="all",
            force=True,
        )
        self.assertTrue(need_y)
        self.assertTrue(need_s)
        self.assertTrue(need_f)

    # -------------------------------------------------------------------------
    # 一括取得処理 (run_batch) のテスト
    # -------------------------------------------------------------------------

    def test_fetch_single_game_execution_all_sources(self) -> None:
        """fetch_single_gameによる全3スクレイパー呼び出しテスト."""
        self.mock_yahoo.save_raw_data.return_value = {
            "stats_path": "path/to/stats",
            "text_path": "path/to/text",
        }
        self.mock_spaia.save_raw_data.return_value = {
            "comments_path": "path/to/comments",
            "stats_path": "path/to/pstats",
        }
        self.mock_flab.save_raw_data.return_value = {
            "json_path": "path/to/flab_json",
            "markdown_path": "path/to/flab_md",
        }

        res = self.fetcher.fetch_single_game(
            game_id="2026102505",
            date_str="2026-10-25",
            home_team_id="FCT",
            away_team_id="MIT",
            source="all",
        )
        self.assertFalse(res["skipped"])
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(len(res["saved_files"]), 6)
        self.assertIn("yahoo_stats_path", res["saved_files"])
        self.assertIn("spaia_stats_path", res["saved_files"])
        self.assertIn("football_lab_json_path", res["saved_files"])

        self.mock_yahoo.save_raw_data.assert_called_once()
        self.mock_spaia.save_raw_data.assert_called_once()
        self.mock_flab.save_raw_data.assert_called_once()

    def test_run_batch_dry_run(self) -> None:
        """Dry-runモードの実行テスト."""
        self.mock_crawler.build_schedule.return_value = [
            {
                "year": 2026,
                "matchweek": 1,
                "mmdd": "0808",
                "daily_match_index": 2,
                "home_team_id": "FCT",
                "away_team_id": "MAC",
                "home_team_raw": "FC東京",
                "away_team_raw": "町田",
            },
        ]

        summary = self.fetcher.run_batch(
            season=2026,
            start_mw=1,
            end_mw=1,
            dry_run=True,
        )

        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["total"], 1)
        self.mock_yahoo.save_raw_data.assert_not_called()
        self.mock_spaia.save_raw_data.assert_not_called()
        self.mock_flab.save_raw_data.assert_not_called()

    def test_arg_parser(self) -> None:
        """CLIパーサーの引数受取テスト."""
        parser = build_arg_parser()
        args = parser.parse_args([
            "--season", "2026",
            "-mw", "12",
            "-t", "FC東京",
            "-s", "football_lab",
            "--force",
            "--delay", "0.5",
            "--structure-ai",
        ])

        self.assertEqual(args.season, 2026)
        self.assertEqual(args.matchweek, "12")
        self.assertEqual(args.team, "FC東京")
        self.assertEqual(args.source, "football_lab")
        self.assertTrue(args.force)
        self.assertEqual(args.delay, 0.5)
        self.assertTrue(args.structure_ai)

    def test_run_batch_with_structure_ai(self) -> None:
        """--structure-ai フラグ指定時のバッチAI構造化呼び出しテスト."""
        self.mock_crawler.build_schedule.return_value = [
            {
                "year": 2026,
                "matchweek": 1,
                "mmdd": "0808",
                "daily_match_index": 2,
                "home_team_id": "FCT",
                "away_team_id": "MAC",
                "home_team_raw": "FC東京",
                "away_team_raw": "町田",
            },
        ]
        self.mock_yahoo.save_raw_data.return_value = {"stats_path": "dummy_stats"}
        self.mock_spaia.save_raw_data.return_value = {"comments_path": "dummy_comments"}
        self.mock_flab.save_raw_data.return_value = {"json_path": "dummy_json"}

        summary = self.fetcher.run_batch(
            season=2026,
            start_mw=1,
            end_mw=1,
            structure_ai=True,
            delay=0.0,
        )

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["success"], 1)
        # text_live_structurer.structure_match が呼び出されたことを検証
        self.mock_structurer.structure_match.assert_called_once_with(
            game_id="2026080802",
            force_refresh=False,
        )


if __name__ == "__main__":
    unittest.main()

