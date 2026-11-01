# -*- coding: utf-8 -*-
"""
Verification Script for Layer 1 (Ground Truth) & Layer 2 (Tactical Heuristics).
Generates tactical data into data/test_structured/ and compares against data/structured/
and data/football.db to verify accuracy, stability, and consistency.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.match_tactical_enricher import DeterministicTacticalEnricher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_layer1_layer2")

ROOT_DIR = Path(__file__).resolve().parent.parent
EXISTING_DIR = ROOT_DIR / "data" / "structured"
TEST_OUTPUT_DIR = ROOT_DIR / "data" / "test_structured"


def run_generation() -> int:
    """Generate tactical data into test_structured directory."""
    logger.info("Starting tactical data generation into %s", TEST_OUTPUT_DIR)
    enricher = DeterministicTacticalEnricher()
    count = enricher.enrich_all_matches(output_dir=TEST_OUTPUT_DIR)
    logger.info("Generated %d files in %s", count, TEST_OUTPUT_DIR)
    return count


def verify_layer1_ground_truth(test_dir: Path, db_path: Path) -> Dict[str, Any]:
    """Verify Layer 1 data accuracy against database and physical bounds."""
    conn = get_db_connection(str(db_path))
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cursor = conn.cursor()

    # Load match facts from DB
    cursor.execute(
        """
        SELECT m.match_id, m.home_score, m.away_score,
               fh.distance_m as h_dist, fh.sprints as h_spr, fh.m30_entries as h_m30, fh.pa_entries as h_pa,
               fa.distance_m as a_dist, fa.sprints as a_spr, fa.m30_entries as a_m30, fa.pa_entries as a_pa
        FROM matches m
        LEFT JOIN team_match_flab_stats fh ON m.match_id = fh.match_id AND m.home_team_id = fh.team_id
        LEFT JOIN team_match_flab_stats fa ON m.match_id = fa.match_id AND m.away_team_id = fa.team_id
        WHERE m.season = 2026 AND m.matchweek <= 12
        """
    )
    db_records = {row["match_id"]: row for row in cursor.fetchall()}

    total_files = 0
    score_matches = 0
    intensity_matches = 0
    conversion_valid_count = 0
    physical_bounds_valid = 0
    null_issues = []
    bounds_issues = []

    for file_path in sorted(test_dir.glob("*_tactical.json")):
        total_files += 1
        data = json.loads(file_path.read_text(encoding="utf-8"))
        match_id = data.get("match_id", "")
        db_row = db_records.get(match_id)

        deep_metrics = data.get("deep_metrics", {})
        conv = deep_metrics.get("conversion_rates", {})
        h_conv = conv.get("home", {})
        a_conv = conv.get("away", {})

        intensity = deep_metrics.get("intensity", {})
        h_dist = intensity.get("home_distance_km")
        a_dist = intensity.get("away_distance_km")
        h_spr = intensity.get("home_sprints")
        a_spr = intensity.get("away_sprints")

        # 1. Null check
        if any(v is None for v in [h_dist, a_dist, h_spr, a_spr]):
            null_issues.append(f"{match_id}: None intensity values")

        # 2. Physical bounds check (distance between 80 and 140km, sprints between 30 and 260)
        dist_ok = (80.0 <= h_dist <= 140.0) and (80.0 <= a_dist <= 140.0) if (h_dist and a_dist) else False
        spr_ok = (30 <= h_spr <= 260) and (30 <= a_spr <= 260) if (h_spr and a_spr) else False
        if dist_ok and spr_ok:
            physical_bounds_valid += 1
        else:
            bounds_issues.append(f"{match_id}: dist=({h_dist},{a_dist}), spr=({h_spr},{a_spr})")

        # 3. Logical containment: m30_entries >= pa_entries
        h_m30 = h_conv.get("m30_entries", 0)
        h_pa = h_conv.get("pa_entries", 0)
        a_m30 = a_conv.get("m30_entries", 0)
        a_pa = a_conv.get("pa_entries", 0)
        if h_m30 >= h_pa and a_m30 >= a_pa:
            conversion_valid_count += 1

        # 4. DB cross-validation
        if db_row and db_row["h_m30"] is not None:
            if h_m30 == db_row["h_m30"] and a_m30 == db_row["a_m30"]:
                conversion_matches = True
            else:
                conversion_matches = False

            if h_spr == db_row["h_spr"] and a_spr == db_row["a_spr"]:
                intensity_matches += 1

    return {
        "total_files": total_files,
        "physical_bounds_valid": physical_bounds_valid,
        "conversion_containment_valid": conversion_valid_count,
        "intensity_db_matches": intensity_matches,
        "null_issues": null_issues,
        "bounds_issues": bounds_issues[:5],
    }


def verify_layer2_stability(existing_dir: Path, test_dir: Path) -> Dict[str, Any]:
    """Verify Layer 2 heuristics stability, distribution, and exact reproducibility."""
    identical_files = 0
    total_comparisons = 0
    diff_files = []

    formation_dist = Counter()
    dominant_team_dist = Counter()
    team_formations = defaultdict(Counter)

    for test_file in sorted(test_dir.glob("*_tactical.json")):
        existing_file = existing_dir / test_file.name
        total_comparisons += 1

        test_data = json.loads(test_file.read_text(encoding="utf-8"))

        # Formation distributions
        h_form = test_data.get("home_formation", "UNKNOWN")
        a_form = test_data.get("away_formation", "UNKNOWN")
        formation_dist[h_form] += 1
        formation_dist[a_form] += 1

        # Phase dominant_team distributions
        phases = test_data.get("phases", [])
        for p in phases:
            dom = p.get("dominant_team", "UNKNOWN")
            dominant_team_dist[dom] += 1

        if existing_file.exists():
            existing_data = json.loads(existing_file.read_text(encoding="utf-8"))
            if test_data == existing_data:
                identical_files += 1
            else:
                diff_files.append(test_file.name)

    return {
        "total_comparisons": total_comparisons,
        "identical_files": identical_files,
        "identical_ratio_pct": round(identical_files / max(1, total_comparisons) * 100, 2),
        "diff_files": diff_files,
        "formation_dist": dict(formation_dist),
        "dominant_team_dist": dict(dominant_team_dist),
    }


def main() -> None:
    # 1. Run generation
    count = run_generation()

    # 2. Layer 1 Validation
    l1_report = verify_layer1_ground_truth(TEST_OUTPUT_DIR, DEFAULT_DB_PATH)

    # 3. Layer 2 Stability & Reproducibility
    l2_report = verify_layer2_stability(EXISTING_DIR, TEST_OUTPUT_DIR)

    report = {
        "generated_count": count,
        "layer1_validation": l1_report,
        "layer2_stability": l2_report,
    }

    report_path = ROOT_DIR / "exports" / "tactical_verification_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(" [VERIFICATION RESULT SUMMARY]")
    print("=" * 60)
    print(f"Generated Files: {count}")
    print("\n[Layer 1: Ground Truth Accuracy]")
    print(f"  Total Verified: {l1_report['total_files']}")
    print(f"  Physical Bounds Valid (Distance/Sprints): {l1_report['physical_bounds_valid']} / {l1_report['total_files']}")
    print(f"  Logical Containment (m30 >= PA): {l1_report['conversion_containment_valid']} / {l1_report['total_files']}")
    print(f"  DB Exact Intensity Matches: {l1_report['intensity_db_matches']} / {l1_report['total_files']}")
    print(f"  Null/NaN Anomalies: {len(l1_report['null_issues'])}")

    print("\n[Layer 2: Stability & Reproducibility]")
    print(f"  Exact Match with Existing Data: {l2_report['identical_files']} / {l2_report['total_comparisons']} ({l2_report['identical_ratio_pct']}%)")
    print(f"  Formation Distributions: {l2_report['formation_dist']}")
    print(f"  Phase Dominant Team Ratio: {l2_report['dominant_team_dist']}")
    print("=" * 60)
    print(f"Detailed report saved to: {report_path}")


if __name__ == "__main__":
    main()