# -*- coding: utf-8 -*-
"""
FC Tokyo Cross-Analytics & Opponent Clustering Engine.
(pipeline/fctokyo_cross_analytics.py)
Backwards-compatibility wrapper around pipeline.team_cross_analytics.
"""

from __future__ import annotations

from pathlib import Path
from pipeline.team_cross_analytics import (
    FCTokyoCrossAnalyticsEngine,
    TeamCrossAnalyticsEngine,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_SYNTHESIS_PATH = ROOT_DIR / "data" / "structured" / "fctokyo_season_tactical_synthesis.json"

__all__ = [
    "FCTokyoCrossAnalyticsEngine",
    "TeamCrossAnalyticsEngine",
    "OUTPUT_SYNTHESIS_PATH",
]

if __name__ == "__main__":
    engine = FCTokyoCrossAnalyticsEngine()
    data = engine.run_and_persist_synthesis()
    print("\n[Time Segment Summary]")
    for seg, st in data["time_segment_dynamics"].items():
        print(f"  {seg}: Goals {st['fct_goals']}-{st['opp_goals']}, Shots Missed {st['fct_shots_missed']}")
    print("\n[Opponent Archetype Summary]")
    for arch, val in data["opponent_archetype_resistance"].items():
        print(f"  {arch} ({val['match_count']} games): WinRate {val['win_rate_pct']}%, Conv30toPA {val['avg_conv_30_to_pa_pct']}%, CrossReliance {val['avg_cross_reliance_pct']}%")
