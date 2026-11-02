"""
Unit tests for specification conformance and data model validation (tests/test_spec_conformance.py).
Ensures 100% compatibility between data_analysis_specification.md, pipeline/models.py,
and real structured tactical JSON outputs.
"""

import json
import os
import unittest
from pathlib import Path

from pipeline.models import (
    CoachRatingItem,
    DisciplinaryModel,
    EventDetail,
    InjuryConditionModel,
    Layer1Metrics,
    Layer2EventCounts,
    LoanRestrictionModel,
    MatchAnalysisOutput,
    MatchContextModel,
    MatchTacticalStructure,
    PerspectiveItem,
    PlayerRatingItem,
    ScheduleFatigueModel,
    WeatherPitchModel,
)
from scripts.calculate_match_context import MatchContextCalculator

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestSpecConformance(unittest.TestCase):
    """Test suite ensuring complete conformance between specification and implementation."""

    def setUp(self) -> None:
        self.calculator = MatchContextCalculator()
        self.structured_dir = ROOT_DIR / "data" / "structured"

    def test_match_context_models_instantiation(self) -> None:
        """Test that all 5 sub-models of MatchContextModel can be instantiated with defaults."""
        sched = ScheduleFatigueModel()
        self.assertEqual(sched.rest_days_display, "-")
        self.assertFalse(sched.is_congested)

        disc = DisciplinaryModel()
        self.assertEqual(len(disc.suspended_players), 0)

        weather = WeatherPitchModel()
        self.assertEqual(weather.weather_condition, "不明")

        loan = LoanRestrictionModel()
        self.assertFalse(loan.has_loan_restriction)

        injury = InjuryConditionModel()
        self.assertEqual(len(injury.active_injuries), 0)

        ctx = MatchContextModel(
            match_id="20261025_FCT_MIT",
            team_id="FCT",
            opponent_team_id="MIT",
            schedule_fatigue=sched,
            disciplinary=disc,
            weather_pitch=weather,
            loan_restrictions=loan,
            injury_condition=injury,
        )
        self.assertEqual(ctx.match_id, "20261025_FCT_MIT")

    def test_calculate_context_convenience_method(self) -> None:
        """Test that calculate_context successfully auto-resolves and validates against MatchContextModel."""
        raw_ctx = self.calculator.calculate_context(
            match_id="20261025_FCT_MIT",
            team_id="FCT",
        )
        self.assertIn("schedule_fatigue", raw_ctx)
        self.assertIn("disciplinary", raw_ctx)
        self.assertIn("weather_pitch", raw_ctx)
        self.assertIn("loan_restrictions", raw_ctx)
        self.assertIn("injury_condition", raw_ctx)

        # Validate with Pydantic
        model = MatchContextModel(**raw_ctx)
        self.assertEqual(model.team_id, "FCT")
        self.assertEqual(model.opponent_team_id, "MIT")
        self.assertEqual(model.schedule_fatigue.rest_days_display, "中3日")

    def test_fct_canonical_matches_tactical_json_conformance(self) -> None:
        """Test that all 12 FC Tokyo canonical structured JSON files conform to MatchTacticalStructure."""
        fct_files = [
            f for f in os.listdir(self.structured_dir)
            if "FCT" in f and f.endswith("_tactical.json")
        ]
        self.assertGreaterEqual(
            len(fct_files),
            12,
            f"Expected at least 12 FCT canonical matches, got {len(fct_files)}: {fct_files}",
        )

        for fname in fct_files:
            file_path = self.structured_dir / fname
            with open(file_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            model = MatchTacticalStructure(**data)
            self.assertIsNotNone(
                model.match_context,
                f"Match context must be present in {fname}",
            )
            self.assertEqual(
                model.match_context.team_id,
                "FCT",
                f"Team ID should be FCT in {fname}",
            )

    def test_match_analysis_output_schema_conformance(self) -> None:
        """Test that full MatchAnalysisOutput schema from Chapter 7 can be constructed and validated."""
        l1 = Layer1Metrics(
            raw_keys_used=["Shoot", "PassCount"],
            metrics={"shots": 16.0, "passes": 450.0},
            formatted_display={"shots": "16本", "passes": "450本"},
        )
        ev = EventDetail(
            minute=32,
            half="1H",
            team="FCT",
            player_name="仲川 輝人",
            event_category="GOAL",
            description="右ハーフスペース突破から先制弾",
        )
        l2 = Layer2EventCounts(
            home_counts={"GOAL": 6, "SHOT": 16},
            away_counts={"GOAL": 0, "SHOT": 5},
            key_incidents=[ev],
        )
        persp = PerspectiveItem(
            perspective_id=1,
            title="ゲームフローと時間帯別力学",
            layer1_data=l1,
            layer2_events=l2,
            layer3_theory_tags=["#Game_State", "#Positional_Play"],
            narrative_home="前半立ち上がりから相手のハイプレスを冷静に回避し、アタッキングサード進入から主導権を掌握した。" * 3,
            narrative_away="アウェイの地で立ち上がり果敢にプレスを仕掛けたものの、スペース管理の歪みから先制を許し後退を余儀なくされた。" * 3,
        )
        player_r = PlayerRatingItem(
            name="仲川 輝人",
            uniform_number=39,
            position="FW",
            team_side="HOME",
            starting=True,
            minutes_played=63,
            rating="7.5",
            is_mom=True,
            cbp_attack=4.2,
            cbp_defense=0.8,
            cbp_steal=0.5,
            review_comment="先制ゴールと右サイド牽引で大勝の口火を切った。",
        )
        coach_r = CoachRatingItem(
            coach_name="ピーター クラモフスキー",
            team_name="FC東京",
            rating="7.5",
            game_plan_review="相手のハイプレスを逆手に取ったスペース活用と前線プレスの連動が完璧に機能。",
            substitutions_review="後半投入した若手・控え組がさらにギアを上げ追加点を量産。",
        )

        ctx_dict = self.calculator.calculate_context(
            match_id="20261025_FCT_MIT",
            team_id="FCT",
        )
        ctx_model = MatchContextModel(**ctx_dict)

        report = MatchAnalysisOutput(
            match_id="20261025_FCT_MIT",
            match_title="FC東京 vs 水戸ホーリーホック",
            overall_summary="ピッチ上の力学推移と勝敗の分岐点に関するプロフェッショナル戦術レポート本文。" * 10,
            tactical_highlights=["仲川の先制弾", "5レーン支配", "途中組の躍動"],
            three_phase_chronology={
                "0-45分": "立ち上がりのプレス合戦から先制",
                "46-60分": "後半開始直後の畳み掛け",
                "61-90分": "交代選手の決定力爆発",
            },
            perspectives=[persp],
            reasons_win_loss={
                "win_reasons": ["相手プレスの逆用", "圧倒的進入変換効率"],
                "loss_reasons": ["守備ライン間の決壊", "中盤のセカンドボール回収劣勢"],
            },
            player_ratings=[player_r],
            coach_ratings=[coach_r],
            match_context=ctx_model,
        )

        self.assertEqual(report.match_id, "20261025_FCT_MIT")
        self.assertIsNotNone(report.match_context)
        self.assertEqual(report.match_context.schedule_fatigue.rest_days_display, "中3日")


if __name__ == "__main__":
    unittest.main()
