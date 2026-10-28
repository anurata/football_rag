"""
Batch Match Context Enrichment for All FC Tokyo 2026 Matches (scripts/enrich_fct_match_context_batch.py).

Calculates and synchronizes the 5 external tactical context elements:
1. 🏥 怪我・コンディション情報 (Injury & Condition Context)
2. 🟨 累積警告・出場停止情報 (Disciplinary Status)
3. 🗓️ 過密日程・中何日・移動負担 (Schedule & Fatigue Context)
4. 📄 契約上の出場制限 (Loan Restrictions)
5. 🌦️ 特殊なピッチ状態・気候条件 (Pitch & Weather Context)

Synchronizes directly into data/structured/{match_id}_tactical.json.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.fetch_fct_canonical import FCT_CANONICAL_MATCHES
from scripts.calculate_match_context import MatchContextCalculator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("enrich_context_batch")


def run_batch_context_enrichment() -> None:
    """Enrich all 12 canonical FCT matches with 5-element match context."""
    calc = MatchContextCalculator()
    structured_dir = ROOT_DIR / "data" / "structured"

    logger.info("Starting Batch Match Context Enrichment for FCT Canonical Matches...")

    for m in FCT_CANONICAL_MATCHES:
        mw = m["mw"]
        match_id = m["match_id"]
        game_id = m["game_id"]
        date_str = m["date"]
        home_team = m["home"]
        away_team = m["away"]
        is_home = (home_team == "FCT")
        opponent = away_team if is_home else home_team
        stadium = "味の素スタジアム" if is_home else "アウェイスタジアム"

        context = calc.get_full_match_context(
            team_id="FCT",
            opponent_team_id=opponent,
            match_id=match_id,
            date_str=date_str,
            stadium=stadium,
            is_home=is_home,
        )

        logger.info(
            "MW%02d (%s vs %s): Rest: %s | Disciplinary: %s | Weather: %s | Loan: %s",
            mw,
            home_team,
            away_team,
            context["schedule_fatigue"]["rest_days_display"],
            context["disciplinary"]["summary_text"],
            context["weather_pitch"]["weather_condition"],
            context["loan_restrictions"]["summary_text"],
        )

        # Sync to structured JSON files
        for target_stem in [match_id, game_id]:
            p = structured_dir / f"{target_stem}_tactical.json"
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    data["match_context"] = context
                    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info("Updated match_context in %s", p.name)
                except Exception as e:
                    logger.warning("Failed to update %s: %s", p.name, e)

    logger.info("Batch Match Context Enrichment completed successfully.")


if __name__ == "__main__":
    run_batch_context_enrichment()
