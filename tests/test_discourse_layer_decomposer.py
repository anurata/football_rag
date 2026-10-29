"""
tests/test_discourse_layer_decomposer.py

Unit tests for 7-Layer Discourse Decomposition (Gemini structured + Deterministic fallback)
and SQLite persistence in TacticalDiscourseRepository.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

from pipeline.discourse_layer_decomposer import (
    DiscourseLayerDecomposer,
    TacticalDiscourseRepository,
    classify_unit_layer_deterministic,
)


class _StubGeminiClient:
    """Stub Gemini client returning structured 7-layer JSON without network calls."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.mock_mode = False

    def is_available(self) -> bool:
        return True

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Any,
        temperature: float = 0.1,
    ) -> Optional[str]:
        return json.dumps(self._payload, ensure_ascii=False)


class TestDiscourseLayerDecomposer(unittest.TestCase):
    """Test suite for 7-layer classification, decomposition, and SQLite storage."""

    def test_deterministic_7_layer_classification(self) -> None:
        self.assertEqual(
            classify_unit_layer_deterministic("パス本数638本で保持率60%、後半27分に交代した。"),
            1,
        )
        self.assertEqual(
            classify_unit_layer_deterministic(
                "最終ラインにゲームメーカーがいるとビルドアップの仕組みを1人で解決できる。"
            ),
            2,
        )
        self.assertEqual(
            classify_unit_layer_deterministic(
                "後半4-2-3-1に修正したことで相手ボランチを引き出し前進できた。"
            ),
            3,
        )
        self.assertEqual(
            classify_unit_layer_deterministic(
                "松橋監督は90分間敵陣で制圧し続ける意図があったのではないか。"
            ),
            4,
        )
        self.assertEqual(
            classify_unit_layer_deterministic(
                "神戸戦と清水戦のミスは完全に帳消しとなり伝説になる試合だった。"
            ),
            5,
        )
        self.assertEqual(
            classify_unit_layer_deterministic(
                "次節は相手がブロックを敷くので予想スコアは2-0で先制するだろう。",
                video_title="次節プレビュー",
            ),
            6,
        )
        self.assertEqual(
            classify_unit_layer_deterministic(
                "今年こそ言い訳なしで優勝してほしいしヨーロッパへ行ってほしい。"
            ),
            7,
        )

    def test_gemini_structured_decomposition_and_sqlite_repo(self) -> None:
        stub_payload = {
            "claims": [
                {
                    "truth_layer": 1,
                    "team_id": "FCT",
                    "manager_mentioned": "松橋 力蔵",
                    "players_mentioned": ["稲村 隼翔"],
                    "statement_text": "前半のボール保持率は60%を記録した。",
                    "original_quote": "ただ保持率60%東京です。",
                },
                {
                    "truth_layer": 4,
                    "team_id": "REY",
                    "manager_mentioned": "リカルド ロドリゲス",
                    "players_mentioned": ["小泉 佳穂"],
                    "statement_text": "柏は前半を抑えて後半45分に3枚替えで勝負をかけるプランだったと推論される。",
                    "original_quote": "前半は抑え目で最後の45分に全てをかけるプランだったのではないか。",
                },
                {
                    "truth_layer": 7,
                    "team_id": "FCT",
                    "manager_mentioned": "",
                    "players_mentioned": ["マルセロ ヒアン"],
                    "statement_text": "ヒアンにゴールを決めて笑顔を見せてほしいというサポーターの願い。",
                    "original_quote": "みんなが思うことはヒアンにゴールを取らせたい、今は笑う時だ。",
                },
            ],
        }

        club_profiles = {
            "FCT": {"canonical_name": "FC東京", "current_manager": "松橋 力蔵"},
            "REY": {"canonical_name": "柏レイソル", "current_manager": "リカルド ロドリゲス"},
        }
        decomposer = DiscourseLayerDecomposer(
            gemini_client=_StubGeminiClient(stub_payload),  # type: ignore[arg-type]
            club_profiles=club_profiles,
            use_gemini=True,
        )

        sample_seg = {
            "segment_id": "SEG_test_0",
            "video_id": "test_vid",
            "channel_name": "トーキョウ二元論",
            "video_title": "FC東京 vs 柏レイソル レビュー",
            "video_url": "https://www.youtube.com/watch?v=test_vid&t=0s",
            "time_range": "00:00 - 03:00",
            "verbatim_text": (
                "ただ保持率60%東京です。"
                "前半は抑え目で最後の45分に全てをかけるプランだったのではないか。"
                "みんなが思うことはヒアンにゴールを取らせたい、今は笑う時だ。"
            ),
        }

        claims = decomposer.decompose_segment(sample_seg, ["FCT", "REY"])
        self.assertEqual(len(claims), 3)
        self.assertEqual(claims[0]["source_reliability"], "YOUTUBE_REPORTED_FACT")
        self.assertEqual(claims[1]["team_id"], "REY")
        self.assertEqual(claims[1]["truth_layer"], 4)
        self.assertEqual(claims[2]["truth_layer"], 7)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            repo = TacticalDiscourseRepository(db_path=db_path)
            inserted = repo.upsert_claims(claims)
            self.assertEqual(inserted, 3)

            # Re-upserting same claims must be idempotent
            repo.upsert_claims(claims)
            fct_l1 = repo.query_claims(team_id="FCT", layers=[1])
            self.assertEqual(len(fct_l1), 1)
            self.assertEqual(fct_l1[0]["statement_text"], "前半のボール保持率は60%を記録した。")

            rey_l4 = repo.query_claims(team_id="REY", layers=[4])
            self.assertEqual(len(rey_l4), 1)
            self.assertEqual(rey_l4[0]["manager_mentioned"], "リカルド ロドリゲス")

            matrix = repo.count_by_team_and_layer()
            self.assertEqual(matrix["FCT"][1], 1)
            self.assertEqual(matrix["FCT"][7], 1)
            self.assertEqual(matrix["REY"][4], 1)


if __name__ == "__main__":
    unittest.main()

