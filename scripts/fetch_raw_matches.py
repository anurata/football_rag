"""Jリーグ試合の生データ一括取得スクリプト (scripts/fetch_raw_matches.py).

指定されたシーズン・節・チーム・特定試合IDに基づいて、
Yahoo!サッカー、SPAIA、およびFootball LABから
スタッツ・テキスト速報・出場詳細成績・CBP等の
データを一括取得して data/raw/ および data/markdown/ に保存する.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# プロジェクトルートをsys.pathに追加
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.normalizer import EntityNormalizer
from pipeline.text_live_structurer import TextLiveStructurer
from scrapers.football_lab import FootballLabScraper
from scrapers.schedule_crawler import ScheduleCrawler
from scrapers.spaia_soccer import SpaiasoccerScraper
from scrapers.yahoo_soccer import YahooSoccerScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_raw_matches")


class RawMatchFetcher:
    """生データ（Yahoo!サッカー / SPAIA / Football LAB）の一括取得・保存オーケストレーター."""

    def __init__(
        self,
        raw_dir: str = "data/raw",
        markdown_dir: str = "data/markdown",
        structured_dir: str = "data/structured",
        normalizer: Optional[EntityNormalizer] = None,
        schedule_crawler: Optional[ScheduleCrawler] = None,
        yahoo_scraper: Optional[YahooSoccerScraper] = None,
        spaia_scraper: Optional[SpaiasoccerScraper] = None,
        football_lab_scraper: Optional[FootballLabScraper] = None,
        text_live_structurer: Optional[TextLiveStructurer] = None,
    ) -> None:
        """フェッチャーを初期化する."""
        self.raw_dir = raw_dir
        self.markdown_dir = markdown_dir
        self.structured_dir = structured_dir
        self.yahoo_dir = os.path.join(raw_dir, "yahoo")
        self.spaia_dir = os.path.join(raw_dir, "spaia")
        self.flab_dir = os.path.join(raw_dir, "football_lab")

        self.normalizer = normalizer or EntityNormalizer()
        self.schedule_crawler = schedule_crawler or ScheduleCrawler(
            normalizer=self.normalizer,
        )
        self.yahoo_scraper = yahoo_scraper or YahooSoccerScraper()
        self.spaia_scraper = spaia_scraper or SpaiasoccerScraper()
        self.football_lab_scraper = football_lab_scraper or FootballLabScraper()
        self.text_live_structurer = text_live_structurer or TextLiveStructurer(
            raw_dir=self.raw_dir,
            output_dir=self.structured_dir,
        )

        os.makedirs(self.yahoo_dir, exist_ok=True)
        os.makedirs(self.spaia_dir, exist_ok=True)
        os.makedirs(self.flab_dir, exist_ok=True)
        os.makedirs(self.markdown_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # 試合ディスカバリ & フィルタリング
    # -------------------------------------------------------------------------

    def discover_matches(
        self,
        season: int = 2026,
        start_mw: int = 1,
        end_mw: int = 38,
        team_query: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """条件に合致する試合メタ情報リストを特定する.

        Args:
            season: シーズン年度
            start_mw: 開始節
            end_mw: 終了節
            team_query: 対象チーム指定 (任意)
            game_id: 単一試合ID指定 (任意)

        Returns:
            対象試合辞書のリスト
        """
        if game_id:
            return self._build_single_game_entry(game_id, season)

        canonical_team_id = self._resolve_team_id(team_query)

        # ScheduleCrawlerを用いて公式スケジュールを構築
        try:
            schedule = self.schedule_crawler.build_schedule(
                year=season,
                start_mw=start_mw,
                end_mw=end_mw,
            )
        except Exception as e:
            logger.warning(
                "Failed to build schedule via ScheduleCrawler: %s. Falling back to empty schedule.",
                e,
            )
            schedule = []

        return self._filter_schedule_by_team(schedule, canonical_team_id)

    def _build_single_game_entry(
        self,
        game_id: str,
        season: int,
    ) -> List[Dict[str, Any]]:
        """直接指定されたgame_idのエントリを作成する（チーム情報を自動補完）."""
        clean_date = f"{game_id[:4]}-{game_id[4:6]}-{game_id[6:8]}" if len(game_id) >= 8 else ""

        # 1. ScheduleCrawlerのスケジュールから一致する試合を検索
        try:
            full_schedule = self.schedule_crawler.build_schedule(
                year=season,
                start_mw=1,
                end_mw=38,
            )
            for m in full_schedule:
                if self._extract_standard_game_id(m) == game_id:
                    m_copy = dict(m)
                    m_copy["game_id"] = game_id
                    return [m_copy]
        except Exception as e:
            logger.debug("ScheduleCrawler lookup skipped: %s", e)

        # 2. SPAIAメタ情報APIからの補完
        try:
            meta = self.spaia_scraper.fetch_game_meta(game_id)
            if meta:
                h_name = meta.get("HNameS", "Home")
                v_name = meta.get("VNameS", "Away")
                h_id = self.normalizer.normalize_team_name(h_name) or h_name
                v_id = self.normalizer.normalize_team_name(v_name) or v_name
                return [
                    {
                        "game_id": game_id,
                        "season": season,
                        "matchweek": None,
                        "date": clean_date,
                        "home_team_id": h_id,
                        "away_team_id": v_id,
                        "home_team_raw": h_name,
                        "away_team_raw": v_name,
                    },
                ]
        except Exception as e:
            logger.debug("SPAIA meta lookup skipped: %s", e)

        return [
            {
                "game_id": game_id,
                "season": season,
                "matchweek": None,
                "date": clean_date,
                "home_team_id": "UNKNOWN",
                "away_team_id": "UNKNOWN",
                "home_team_raw": "Home",
                "away_team_raw": "Away",
            },
        ]


    def _resolve_team_id(self, team_query: Optional[str]) -> Optional[str]:
        """チーム指定文字列を正規化team_idに解決する."""
        if not team_query:
            return None
        return self.normalizer.normalize_team_name(team_query) or team_query

    def _filter_schedule_by_team(
        self,
        schedule: List[Dict[str, Any]],
        canonical_team_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """スケジュールから指定チームの試合のみを抽出する."""
        results: List[Dict[str, Any]] = []

        for item in schedule:
            home_id = item.get("home_team_id")
            away_id = item.get("away_team_id")

            if canonical_team_id and (
                canonical_team_id != home_id and canonical_team_id != away_id
            ):
                continue

            game_id = self._extract_standard_game_id(item)
            item_copy = dict(item)
            item_copy["game_id"] = game_id
            results.append(item_copy)

        return results

    def _extract_standard_game_id(self, match_entry: Dict[str, Any]) -> str:
        """Jリーグ公式URLまたは日付・連番から標準game_id (YYYYMMDDNN) を生成する."""
        year = match_entry.get("year", 2026)
        mmdd = match_entry.get("mmdd", "0101")
        daily_idx = match_entry.get("daily_match_index", 1)
        return f"{year}{mmdd}{daily_idx:02d}"

    # -------------------------------------------------------------------------
    # キャッシュ確認 & 取得判定
    # -------------------------------------------------------------------------

    def is_yahoo_cached(self, game_id: str) -> bool:
        """Yahooのスタッツおよびテキスト速報が保存済みか判定する."""
        stats_file = os.path.join(self.yahoo_dir, f"{game_id}_stats.json")
        text_file = os.path.join(self.yahoo_dir, f"{game_id}_text.json")
        return (
            os.path.exists(stats_file)
            and os.path.getsize(stats_file) > 100
            and os.path.exists(text_file)
            and os.path.getsize(text_file) > 100
        )

    def is_spaia_cached(self, game_id: str) -> bool:
        """SPAIAのコメントおよび選手スタッツが保存済みか判定する."""
        comments_file = os.path.join(self.spaia_dir, f"{game_id}_comments.json")
        stats_file = os.path.join(self.spaia_dir, f"{game_id}_player_stats.json")
        return (
            os.path.exists(comments_file)
            and os.path.getsize(comments_file) > 100
            and os.path.exists(stats_file)
            and os.path.getsize(stats_file) > 100
        )

    def is_football_lab_cached(self, game_id: str) -> bool:
        """Football LABの生JSONまたはMarkdownが保存済みか判定する."""
        json_file = os.path.join(self.flab_dir, f"{game_id}.json")
        md_file = os.path.join(self.markdown_dir, f"{game_id}_flab.md")
        return (
            (os.path.exists(json_file) and os.path.getsize(json_file) > 100)
            or (os.path.exists(md_file) and os.path.getsize(md_file) > 500)
        )

    def should_fetch_game(
        self,
        game_id: str,
        source: str = "all",
        force: bool = False,
    ) -> Tuple[bool, bool, bool]:
        """各ソースの取得要否 (need_yahoo, need_spaia, need_flab) を判定する."""
        if force:
            need_yahoo = source in ("all", "yahoo")
            need_spaia = source in ("all", "spaia")
            need_flab = source in ("all", "football_lab")
            return need_yahoo, need_spaia, need_flab

        need_yahoo = source in ("all", "yahoo") and not self.is_yahoo_cached(game_id)
        need_spaia = source in ("all", "spaia") and not self.is_spaia_cached(game_id)
        need_flab = source in ("all", "football_lab") and not self.is_football_lab_cached(game_id)
        return need_yahoo, need_spaia, need_flab

    # -------------------------------------------------------------------------
    # 個別試合の生データ取得
    # -------------------------------------------------------------------------

    def fetch_single_game(
        self,
        game_id: str,
        date_str: str = "",
        home_team_id: str = "",
        away_team_id: str = "",
        source: str = "all",
        force: bool = False,
    ) -> Dict[str, Any]:
        """1試合分の生データを取得・保存する."""
        need_yahoo, need_spaia, need_flab = self.should_fetch_game(
            game_id=game_id,
            source=source,
            force=force,
        )

        saved_files: Dict[str, str] = {}
        errors: List[str] = []

        # 1. Yahoo!サッカー
        if need_yahoo:
            try:
                res_y = self.yahoo_scraper.save_raw_data(
                    game_id=game_id,
                    output_dir=self.yahoo_dir,
                )
                for k, v in res_y.items():
                    saved_files[f"yahoo_{k}"] = v
            except Exception as e:
                msg = f"Yahoo scraper failed for {game_id}: {e}"
                logger.error(msg)
                errors.append(msg)

        # 2. SPAIA
        if need_spaia:
            try:
                res_s = self.spaia_scraper.save_raw_data(
                    game_id=game_id,
                    output_dir=self.spaia_dir,
                )
                for k, v in res_s.items():
                    saved_files[f"spaia_{k}"] = v
            except Exception as e:
                msg = f"SPAIA scraper failed for {game_id}: {e}"
                logger.error(msg)
                errors.append(msg)

        # 3. Football LAB
        if need_flab:
            try:
                d_str = date_str or f"{game_id[:4]}-{game_id[4:6]}-{game_id[6:8]}"
                res_f = self.football_lab_scraper.save_raw_data(
                    match_id=game_id,
                    date_str=d_str,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    output_dir=self.flab_dir,
                    markdown_dir=self.markdown_dir,
                )
                for k, v in res_f.items():
                    saved_files[f"football_lab_{k}"] = v
            except Exception as e:
                msg = f"Football LAB scraper failed for {game_id}: {e}"
                logger.error(msg)
                errors.append(msg)

        is_skipped = not need_yahoo and not need_spaia and not need_flab
        return {
            "game_id": game_id,
            "skipped": is_skipped,
            "saved_files": saved_files,
            "errors": errors,
        }

    # -------------------------------------------------------------------------
    # バッチ一括取得実行
    # -------------------------------------------------------------------------

    def run_batch(
        self,
        season: int = 2026,
        start_mw: int = 1,
        end_mw: int = 38,
        team_query: Optional[str] = None,
        game_id: Optional[str] = None,
        source: str = "all",
        force: bool = False,
        delay: float = 1.0,
        dry_run: bool = False,
        structure_ai: bool = False,
    ) -> Dict[str, Any]:
        """指定条件の試合を一括取得するバッチ処理を実行する."""
        matches = self.discover_matches(
            season=season,
            start_mw=start_mw,
            end_mw=end_mw,
            team_query=team_query,
            game_id=game_id,
        )

        logger.info(
            "Found %d matches matching criteria (season=%d, mw=%d-%d, team=%s, game_id=%s, source=%s)",
            len(matches),
            season,
            start_mw,
            end_mw,
            team_query,
            game_id,
            source,
        )

        if dry_run:
            self._print_dry_run_summary(matches)
            return {
                "total": len(matches),
                "dry_run": True,
                "matches": matches,
            }

        success_count = 0
        skipped_count = 0
        error_count = 0
        results: List[Dict[str, Any]] = []

        for idx, match in enumerate(matches, start=1):
            g_id = match["game_id"]
            h_raw = match.get("home_team_raw", "")
            a_raw = match.get("away_team_raw", "")
            mw = match.get("matchweek", "?")
            d_str = match.get("date", "")
            h_id = match.get("home_team_id", "")
            a_id = match.get("away_team_id", "")

            logger.info(
                "[%d/%d] Processing %s (MW%s: %s vs %s)",
                idx,
                len(matches),
                g_id,
                mw,
                h_raw,
                a_raw,
            )

            res = self.fetch_single_game(
                game_id=g_id,
                date_str=d_str,
                home_team_id=h_id,
                away_team_id=a_id,
                source=source,
                force=force,
            )
            results.append(res)

            if res["skipped"]:
                skipped_count += 1
                logger.info("  -> Already cached. Skipped.")
            elif res["errors"]:
                error_count += 1
                logger.warning("  -> Completed with errors: %s", res["errors"])
            else:
                success_count += 1
                logger.info(
                    "  -> Successfully saved %d files: %s",
                    len(res["saved_files"]),
                    list(res["saved_files"].keys()),
                )

            # AI構造化のオプション実行
            if structure_ai:
                self._run_ai_structuring_for_game(g_id, force=force)

            # リクエスト待機（キャッシュスキップ時は待機しない）
            if not res["skipped"] and idx < len(matches) and delay > 0:
                time.sleep(delay)

        summary = {
            "total": len(matches),
            "success": success_count,
            "skipped": skipped_count,
            "errors": error_count,
            "results": results,
        }
        self._print_final_summary(summary)
        return summary

    def _run_ai_structuring_for_game(
        self,
        game_id: str,
        force: bool = False,
    ) -> None:
        """試合のテキスト速報をAI構造化し、Markdownファイルがあれば追記更新する."""
        try:
            logger.info("  -> Running AI tactical structuring for %s...", game_id)
            structure = self.text_live_structurer.structure_match(
                game_id=game_id,
                force_refresh=force,
            )
            # Markdownファイルへの追記（もし存在すれば）
            md_candidates = [
                os.path.join(self.markdown_dir, f"{game_id}_flab.md"),
                os.path.join(self.markdown_dir, f"{game_id}.md"),
            ]
            for md_path in md_candidates:
                if os.path.exists(md_path):
                    self.text_live_structurer.append_to_markdown_file(
                        markdown_path=md_path,
                        structure=structure,
                    )
        except Exception as e:
            logger.warning("AI structuring failed for %s: %s", game_id, e)


    def _print_dry_run_summary(self, matches: List[Dict[str, Any]]) -> None:
        """Dry-run時の対象試合一覧を表示する."""
        print("\n=== [Dry-Run] 取得対象試合一覧 ===")
        for m in matches:
            mw_str = f"第{m['matchweek']}節" if m.get("matchweek") else "単一指定"
            print(
                f"- {m['game_id']} | {mw_str} | {m.get('date')} | "
                f"{m.get('home_team_raw')} vs {m.get('away_team_raw')} (Score: {m.get('score', '-')})",
            )
        print(f"合計: {len(matches)} 試合\n")

    def _print_final_summary(self, summary: Dict[str, Any]) -> None:
        """処理完了時のサマリーを表示する."""
        print("\n=== 一括取得完了サマリー ===")
        print(f"総試合数: {summary['total']}")
        print(f"新規取得成功: {summary['success']}")
        print(f"キャッシュスキップ: {summary['skipped']}")
        print(f"エラー発生: {summary['errors']}")
        print("============================\n")


# -------------------------------------------------------------------------
# CLIエントリーポイント
# -------------------------------------------------------------------------

def parse_matchweek_range(mw_str: Optional[str]) -> Tuple[int, int]:
    """節指定文字列 ('12' または '1-12') を (start_mw, end_mw) に変換する."""
    if not mw_str:
        return 1, 38
    if "-" in mw_str:
        parts = mw_str.split("-")
        return int(parts[0]), int(parts[1])
    val = int(mw_str)
    return val, val


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI引数パーサーを構築する."""
    parser = argparse.ArgumentParser(
        description="Jリーグ試合データ（Yahoo!サッカー / SPAIA / Football LAB）を一括取得するCLIツール",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="対象シーズン年度 (デフォルト: 2026)",
    )
    parser.add_argument(
        "-mw",
        "--matchweek",
        type=str,
        default=None,
        help="対象節 (例: '12' または '1-12')",
    )
    parser.add_argument(
        "-t",
        "--team",
        type=str,
        default=None,
        help="対象チーム名または短縮ID (例: 'FC東京', 'FCT')",
    )
    parser.add_argument(
        "-g",
        "--game-id",
        type=str,
        default=None,
        help="特定試合IDの直接指定 (例: '2026102505')",
    )
    parser.add_argument(
        "-s",
        "--source",
        choices=["all", "yahoo", "spaia", "football_lab"],
        default="all",
        help="取得対象ソース (all / yahoo / spaia / football_lab, デフォルト: all)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="キャッシュ済みのファイルも強制再取得する",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="リクエスト間隔待機秒数 (デフォルト: 1.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際のスクレイピングは実行せず、対象試合一覧のみを表示する",
    )
    parser.add_argument(
        "--structure-ai",
        action="store_true",
        help="生データ取得後にGeminiによるテキスト速報の戦術構造化とMarkdown追記を実行する",
    )
    return parser


def main() -> None:
    """CLIメイン実行関数."""
    parser = build_arg_parser()
    args = parser.parse_args()

    start_mw, end_mw = parse_matchweek_range(args.matchweek)

    fetcher = RawMatchFetcher()
    fetcher.run_batch(
        season=args.season,
        start_mw=start_mw,
        end_mw=end_mw,
        team_query=args.team,
        game_id=args.game_id,
        source=args.source,
        force=args.force,
        delay=args.delay,
        dry_run=args.dry_run,
        structure_ai=args.structure_ai,
    )


if __name__ == "__main__":
    main()
