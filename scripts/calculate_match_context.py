"""Match Context & Tactical Support Information Calculator (scripts/calculate_match_context.py).

全20クラブ対応の決定論的プレマッチ外部制約・コンテキスト算出モジュール。
内部実装は pipeline.match_context_service.MatchContextService に委任し、
既存のテストおよび呼び出し元との100%完全後方互換性を提供する。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.match_context_service import MatchContextService

logger = logging.getLogger("match_context_calculator")

ROOT_DIR = Path(__file__).resolve().parent.parent


class MatchContextCalculator:
    """Calculates objective pre-match external context and constraints."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        stadium_config_path: Optional[Path] = None,
        loan_config_path: Optional[Path] = None,
        injury_config_path: Optional[Path] = None,
        raw_spaia_dir: Optional[Path] = None,
        markdown_dir: Optional[Path] = None,
    ) -> None:
        self.db_path = db_path or (ROOT_DIR / "data" / "football.db")
        self.stadium_config_path = stadium_config_path or (
            ROOT_DIR / "config" / "stadium_master.json"
        )
        self.loan_config_path = loan_config_path or (
            ROOT_DIR / "config" / "loan_restrictions.json"
        )
        self.injury_config_path = injury_config_path or (
            ROOT_DIR / "config" / "injury_tracker.json"
        )
        self.raw_spaia_dir = raw_spaia_dir or (
            ROOT_DIR / "data" / "raw" / "spaia"
        )
        self.markdown_dir = markdown_dir or (
            ROOT_DIR / "data" / "markdown" / "2026"
        )

        self._service = MatchContextService(
            db_path=self.db_path,
            stadium_config_path=self.stadium_config_path,
            loan_config_path=self.loan_config_path,
            injury_config_path=self.injury_config_path,
            markdown_dir=self.markdown_dir,
        )

        # 既存テスト・スクリプト互換プロパティ
        self.stadium_master = self._service.stadium_master
        self.loan_master = self._service.loan_master
        self.injury_master = self._service.injury_master

    # ==========================================
    # 1. 過密日程・中何日・移動負担 (Schedule & Fatigue)
    # ==========================================
    def calculate_schedule_fatigue(
        self,
        team_id: str,
        current_date_str: str,
        current_stadium: str = "",
        is_home: bool = True,
    ) -> Dict[str, Any]:
        """Calculate rest days (中何日), consecutive away fixtures, and travel distance."""
        return self._service.calculate_schedule_fatigue(
            team_id=team_id,
            current_date_str=current_date_str,
            current_stadium=current_stadium,
            is_home=is_home,
        )

    # ==========================================
    # 2. 選手累積出場負荷 (Player Load)
    # ==========================================
    def calculate_player_load(
        self,
        team_id: str,
        current_date_str: str,
    ) -> Dict[str, Any]:
        """Calculate recent appearance minutes and physical load per player."""
        return self._service.calculate_player_load(
            team_id=team_id,
            current_date_str=current_date_str,
        )

    # ==========================================
    # 3. 累積警告・出場停止情報 (Disciplinary Status)
    # ==========================================
    def calculate_disciplinary_status(
        self,
        team_id: str,
        current_date_str: str,
        spaia_team_id: int = 270,
    ) -> Dict[str, Any]:
        """Calculate cumulative yellow cards, suspensions (reds / 4 yellows), and reaches."""
        _ = spaia_team_id
        return self._service.calculate_disciplinary_status(
            team_id=team_id,
            current_date_str=current_date_str,
        )

    # ==========================================
    # 4. 特殊なピッチ状態・気候条件 (Weather & Pitch)
    # ==========================================
    def calculate_weather_pitch_context(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """Parse weather, temperature, humidity, and extract tactical implications."""
        return self._service.calculate_weather_pitch_context(
            match_id=match_id,
        )

    # ==========================================
    # 5. 契約上の出場制限 (Loan Restrictions)
    # ==========================================
    def check_loan_restrictions(
        self,
        current_team_id: str,
        opponent_team_id: str,
    ) -> Dict[str, Any]:
        """Check if any loaned players are restricted from playing against parent club."""
        return self._service.check_loan_restrictions(
            current_team_id=current_team_id,
            opponent_team_id=opponent_team_id,
        )

    # ==========================================
    # 6. 怪我・コンディション情報 (Injury & Condition Context)
    # ==========================================
    def get_injury_condition_context(
        self,
        team_id: str,
        current_date_str: str,
        match_id: str = "",
    ) -> Dict[str, Any]:
        """Extract active injuries and coach remarks from match reports."""
        return self._service.get_injury_condition_context(
            team_id=team_id,
            current_date_str=current_date_str,
            match_id=match_id,
        )

    # ==========================================
    # 7. 総合コンテキスト統合 (Full Match Context)
    # ==========================================
    def get_full_match_context(
        self,
        team_id: str,
        opponent_team_id: str,
        match_id: str,
        date_str: str,
        stadium: str,
        is_home: bool,
    ) -> Dict[str, Any]:
        """Aggregate external tactical context elements."""
        fatigue = self.calculate_schedule_fatigue(
            team_id=team_id,
            current_date_str=date_str,
            current_stadium=stadium,
            is_home=is_home,
        )
        player_load = self.calculate_player_load(
            team_id=team_id,
            current_date_str=date_str,
        )
        disciplinary = self.calculate_disciplinary_status(
            team_id=team_id,
            current_date_str=date_str,
        )
        weather = self.calculate_weather_pitch_context(
            match_id=match_id,
        )
        loan = self.check_loan_restrictions(
            current_team_id=team_id,
            opponent_team_id=opponent_team_id,
        )
        injury = self.get_injury_condition_context(
            team_id=team_id,
            current_date_str=date_str,
            match_id=match_id,
        )

        return {
            "match_id": match_id,
            "team_id": team_id,
            "opponent_team_id": opponent_team_id,
            "schedule_fatigue": fatigue,
            "player_load": player_load,
            "disciplinary": disciplinary,
            "weather_pitch": weather,
            "loan_restrictions": loan,
            "injury_condition": injury,
        }

    def calculate_context(
        self,
        match_id: str,
        team_id: str = "FCT",
    ) -> Dict[str, Any]:
        """Convenience method: auto-resolve match metadata and calculate context."""
        ctx = self._service.get_club_prematch_context(
            team_id=team_id,
            match_id=match_id,
        )
        return {
            "match_id": match_id,
            "team_id": team_id,
            "opponent_team_id": ctx["opponent_team_id"],
            "schedule_fatigue": ctx["schedule_fatigue"],
            "player_load": ctx["player_load"],
            "disciplinary": ctx["disciplinary"],
            "weather_pitch": ctx["weather_pitch"],
            "loan_restrictions": ctx["loan_restrictions"],
            "injury_condition": ctx["injury_condition"],
        }
