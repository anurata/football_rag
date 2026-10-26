"""TextLiveStructurer（AIテキスト速報構造化）の単体テスト (tests/test_text_live_structurer.py)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.gemini_client import GeminiTacticalClient
from pipeline.models import (
    MatchTacticalStructure,
    PhaseSummaryItem,
    TacticalEventItem,
)
from pipeline.text_live_structurer import (
    STRUCTURE_SYSTEM_PROMPT,
    TextLiveStructurer,
)


class TestTextLiveStructurer(unittest.TestCase):
    """TextLiveStructurerの機能検証テストケース."""

    def setUp(self) -> None:
        """テスト用の一時ディレクトリとダミーデータを準備する."""
        self.test_dir = tempfile.mkdtemp()
        self.raw_dir = os.path.join(self.test_dir, "raw")
        self.output_dir = os.path.join(self.test_dir, "structured")

        os.makedirs(os.path.join(self.raw_dir, "yahoo"), exist_ok=True)
        os.makedirs(os.path.join(self.raw_dir, "spaia"), exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        self.mock_client = MagicMock(spec=GeminiTacticalClient)
        self.structurer = TextLiveStructurer(
            raw_dir=self.raw_dir,
            output_dir=self.output_dir,
            gemini_client=self.mock_client,
        )

        self._create_dummy_raw_files()

    def tearDown(self) -> None:
        """一時ディレクトリをクリーンアップする."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _create_dummy_raw_files(self) -> None:
        """テスト用のYahoo/SPAIA生JSONファイルを作成する."""
        self.game_id = "2026102505"

        yahoo_data = {
            "game_id": self.game_id,
            "match_info": {
                "home_team": "FC東京",
                "away_team": "水戸",
                "score": "6 - 0",
            },
            "timeline": [
                {
                    "time": "前半0分",
                    "team": "FC東京",
                    "text": "予想フォーメーションは4-4-2。",
                },
                {
                    "time": "前半32分",
                    "team": "FC東京",
                    "text": "仲川が右ハーフスペースからシュートを決めてゴール！",
                },
            ],
        }
        yahoo_path = os.path.join(self.raw_dir, "yahoo", f"{self.game_id}_text.json")
        with open(yahoo_path, "w", encoding="utf-8") as f:
            json.dump(yahoo_data, f, ensure_ascii=False)

        spaia_data = {
            "game_id": self.game_id,
            "comments": [
                {
                    "state_name": "前半",
                    "time_label": "前半 (0)",
                    "team_name": "FC東京",
                    "text": "予想フォーメーションは4-4-2。",  # 重複テキスト
                },
                {
                    "state_name": "後半",
                    "time_label": "後半 (21)",
                    "team_name": "FC東京",
                    "text": "安斎が追加点を奪う！",
                },
            ],
        }
        spaia_path = os.path.join(self.raw_dir, "spaia", f"{self.game_id}_comments.json")
        with open(spaia_path, "w", encoding="utf-8") as f:
            json.dump(spaia_data, f, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # テストメソッド群
    # -------------------------------------------------------------------------

    def test_deduplicate_and_sort_comments(self) -> None:
        """重複コメントの除外ロジックを検証する."""
        comments, meta = self.structurer.load_raw_commentary(self.game_id)
        # 元4件中1件が重複なので、結果は3件になるはず
        self.assertEqual(len(comments), 3)
        texts = [c["text"] for c in comments]
        self.assertIn("仲川が右ハーフスペースからシュートを決めてゴール！", texts)
        self.assertIn("安斎が追加点を奪う！", texts)

    def test_build_user_prompt(self) -> None:
        """Gemini向けプロンプトの構成を検証する."""
        comments, meta = self.structurer.load_raw_commentary(self.game_id)
        prompt = self.structurer.build_user_prompt(self.game_id, meta, comments)

        self.assertIn(f"試合ID: {self.game_id}", prompt)
        self.assertIn("FC東京 vs 水戸", prompt)
        self.assertIn("時系列実況テキスト速報一覧", prompt)
        self.assertIn("MatchTacticalStructure", prompt)

    def test_generate_fallback_structure(self) -> None:
        """フォールバック構造データ生成の検証."""
        fallback = self.structurer.generate_fallback_structure(
            self.game_id,
            {"home_team": "FC東京", "away_team": "水戸"},
        )
        self.assertEqual(fallback.match_id, self.game_id)
        self.assertEqual(len(fallback.phases), 6)
        self.assertGreaterEqual(len(fallback.key_tactical_events), 3)

        phase_keys = [p.phase for p in fallback.phases]
        self.assertIn("0-15", phase_keys)
        self.assertIn("75-90+", phase_keys)

    def test_format_tactical_timeline_markdown(self) -> None:
        """Markdownシリアライズの書式検証."""
        fallback = self.structurer.generate_fallback_structure(
            self.game_id,
            {"home_team": "FC東京", "away_team": "水戸"},
        )
        md = self.structurer.format_tactical_timeline_markdown(fallback)

        self.assertIn(f"Match ID: {self.game_id}", md)
        self.assertIn("15分刻みフェーズ推移（6フェーズ分析）", md)
        self.assertIn("主要な戦術イベント・局面一覧", md)

    def test_structure_match_with_structured_output(self) -> None:
        """Gemini Structured Output が正常に応答した場合のフロー検証."""
        sample_structure = MatchTacticalStructure(
            match_id=self.game_id,
            home_formation="4-4-2",
            away_formation="4-4-2",
            tactical_highlights=["サイドの優位性を活かして大勝"],
            phases=[
                PhaseSummaryItem(
                    phase="0-15",
                    dominant_team="HOME",
                    momentum_summary="FC東京がハイプレスで圧倒",
                    pressing_battle="水戸のビルドアップを完全に封鎖",
                    tactical_adjustments="特になし",
                ),
            ],
            key_tactical_events=[
                TacticalEventItem(
                    minute=32,
                    period="1H",
                    team_side="HOME",
                    category="CHANCE_CREATION",
                    actors=["仲川 輝人"],
                    zone="右ハーフスペース",
                    description="右ポケットへ侵入して先制点。",
                ),
            ],
        )

        self.mock_client.generate_structured.return_value = sample_structure.model_dump_json()

        result = self.structurer.structure_match(self.game_id, force_refresh=True)

        self.assertEqual(result.match_id, self.game_id)
        self.assertEqual(result.tactical_highlights, ["サイドの優位性を活かして大勝"])
        self.assertEqual(result.key_tactical_events[0].actors, ["仲川 輝人"])

        # キャッシュファイルが保存されていることを確認
        cache_path = self.structurer.get_output_path(self.game_id)
        self.assertTrue(os.path.exists(cache_path))

        # キャッシュからの再読み込み（モック呼び出しなし）
        self.mock_client.generate_structured.reset_mock()
        cached_result = self.structurer.structure_match(self.game_id, force_refresh=False)
        self.mock_client.generate_structured.assert_not_called()
        self.assertEqual(cached_result.match_id, self.game_id)


if __name__ == "__main__":
    unittest.main()
