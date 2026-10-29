"""
tests/test_official_discourse_ingester.py

Unit tests for official coach press conference & player interview parsing,
7-layer ingestion, and per-club dossier export.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.club_entity_registry import ClubEntityRegistry
from pipeline.discourse_layer_decomposer import TacticalDiscourseRepository
from pipeline.official_discourse_ingester import (
    export_all_clubs_primary_dossiers,
    ingest_official_markdowns_into_layers,
    parse_official_markdown,
)


class TestOfficialDiscourseIngester(unittest.TestCase):
    """Test suite for official markdown parsing and 7-layer club dossier generation."""

    def test_parse_and_ingest_official_markdown(self) -> None:
        sample_md = """# 鹿島アントラーズ vs ヴィッセル神戸 (Match ID: 20260808_KAS_VOB)

## 【1. 試合概要・基本データ】
- **対象URL**: https://www.jleague.jp/match/j1/2026/080801/
- **節数**: 第1節
- **試合結果**: 2 - 1

## 【2. 公式マッチレポート】
鹿島がハイプレスから主導権を握り、2対1で勝利を収めた。

## 【3. 監督・選手コメント（定性の核）】
### 【監督コメント】
#### 【鹿島アントラーズ】鬼木 達
－－後半の修正について？
ボランチの距離感を修正したことでセカンドボールを回収できるようになり前進できた。サポーターとともに今年こそタイトルを獲ってほしいという想いに応えたい。

#### 【ヴィッセル神戸】ミヒャエル スキッベ
前半35分の失点まではプラン通りだったのではないか。次節はホームで必ず勝点3を奪うだろう。

### 【選手コメント】
#### 【鹿島アントラーズ】鈴木 優磨
－－決勝ゴールの場面は？
監督の狙い通り背後を突くことができた。昨年の悔しさを帳消しにする最高のスタートになった。

## 【4. 分析・観察メモ（AI / ユーザー追記用）】
- メモ
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            md_dir = tmp_dir / "md"
            md_dir.mkdir()
            md_file = md_dir / "20260808_KAS_VOB.md"
            md_file.write_text(sample_md, encoding="utf-8")

            parsed = parse_official_markdown(md_file)
            self.assertEqual(parsed["matchweek"], "第1節")
            self.assertEqual(len(parsed["coach_comments"]), 2)
            self.assertEqual(parsed["coach_comments"][0]["speaker_name"], "鬼木 達")
            self.assertEqual(len(parsed["player_comments"]), 1)
            self.assertNotIn("－－後半の修正", parsed["coach_comments"][0]["answers_only"])

            db_path = tmp_dir / "test.db"
            repo = TacticalDiscourseRepository(db_path=db_path)
            registry = ClubEntityRegistry(md_2026_dir=md_dir)

            stats = ingest_official_markdowns_into_layers(
                registry=registry,
                repo=repo,
                md_dir=md_dir,
            )
            self.assertEqual(stats["markdown_files"], 1)
            self.assertGreaterEqual(stats["official_claims_upserted"], 3)

            kas_claims = repo.query_claims(team_id="KAS")
            self.assertTrue(
                any(c["source_reliability"] == "OFFICIAL_PRESS_CONFERENCE" for c in kas_claims),
            )
            self.assertTrue(
                any(c["source_reliability"] == "OFFICIAL_PLAYER_INTERVIEW" for c in kas_claims),
            )

            export_dir = tmp_dir / "exports"
            files = export_all_clubs_primary_dossiers(
                registry=registry,
                repo=repo,
                output_dir=export_dir,
            )
            self.assertEqual(len(files), len(registry.list_target_clubs()))
            kas_md = (export_dir / "KAS_primary_sources.md").read_text(encoding="utf-8")
            self.assertIn("鬼木 達", kas_md)
            self.assertIn("OFFICIAL_PRESS_CONFERENCE", kas_md)


if __name__ == "__main__":
    unittest.main()

