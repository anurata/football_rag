"""
Master Runner for All 4 Verification Tracks
Runs Track 1, Track 2, Track 3, and Track 4 sequentially and produces an integrated execution summary.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiments.track1_stats_and_events import run_track1_verification
from experiments.track2_tactics_and_mining import run_track2_verification
from experiments.track3_backtest_and_qa import run_track3_verification
from experiments.track4_youtube_feasibility import run_track4_verification


def main():
    print("#" * 70)
    print("FC TOKYO 2026: 4-TRACK INTEGRATED VERIFICATION SUITE")
    print("#" * 70)

    # Track 1
    t1_res = run_track1_verification()

    # Track 2
    t2_res = run_track2_verification()

    # Track 3
    t3_res = run_track3_verification()

    # Track 4
    t4_res = run_track4_verification()

    print("\n" + "#" * 70)
    print("ALL 4 TRACKS EXECUTED SUCCESSFULLY WITHOUT ERRORS.")
    print("#" * 70)


if __name__ == "__main__":
    main()
