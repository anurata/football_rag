# -*- coding: utf-8 -*-
"""
FC Tokyo 55 Tactical Metrics Calculator (pipeline/fctokyo_55_metrics_calculator.py).
Backwards-compatibility wrapper around pipeline.team_55_metrics_calculator.
"""

from __future__ import annotations

from pipeline.team_55_metrics_calculator import (
    FCTokyo55MetricsCalculator,
    Team55MetricsCalculator,
    compute_convex_hull_area,
    compute_gini_coefficient,
    compute_pagerank,
    compute_poisson_probability,
    compute_shannon_entropy,
    run_and_save_55_metrics,
    simulate_poisson_match,
)

__all__ = [
    "FCTokyo55MetricsCalculator",
    "Team55MetricsCalculator",
    "compute_convex_hull_area",
    "compute_gini_coefficient",
    "compute_pagerank",
    "compute_poisson_probability",
    "compute_shannon_entropy",
    "run_and_save_55_metrics",
    "simulate_poisson_match",
]

if __name__ == "__main__":
    df = run_and_save_55_metrics(team_id="FCT")
    print("\nCalculation Preview for FCT (first 2 matches):")
    print(df[["試合ID", "節", "チーム", "対戦相手", "実スコア", "31_チーム凸包面積(㎡)", "35_タッチ関与シャノンエントロピー", "43_ポアソン期待勝点(xPTS)", "48_BPI(ボール前進総合指数)"]].head(2))
