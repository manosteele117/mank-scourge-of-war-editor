"""Micro-benchmarks for the OOB editor hot paths.

Runs the three operations a user feels on big CSVs:

  1. ``OOBData.load_csv`` (parse + normalize + build adjacency index)
  2. ``OOBTreeWidget.populate`` (post-order aggregate tree build)
  3. ``OOBData.build_strength`` (ActualFormation build, cold + warm)

Usage::

    python bench/bench_oob.py                       # default CSVs
    python bench/bench_oob.py path/to/oob.csv ...  # custom CSVs
    python bench/bench_oob.py --repeats 5          # average over N runs
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path
from typing import List

# Force the offscreen Qt platform so the tree widget can construct without
# needing a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication

from core.formation import populate_formation_archetypes_from_csv
from core.oob_model import OOBData
from gui.oob_tree_view import OOBTreeWidget


DEFAULT_BASE = Path("C:/Steam/steamapps/common/Scourge Of War - Remastered/Base")
DEFAULT_CSVS: List[Path] = [
    DEFAULT_BASE / "OOBs" / "OOB_Waterloo_Battle_AM.csv",
    DEFAULT_BASE / "OOBs" / "OOB_SB_Waterloo_Campaign All Brigades.csv",
    DEFAULT_BASE / "OOBs" / "OOB_SB_test_4corps.csv",
]
DEFAULT_DRILLS = DEFAULT_BASE / "Logistics" / "drills.csv"


def time_op(op, repeats: int) -> List[float]:
    samples: List[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        op()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


def fmt(samples: List[float]) -> str:
    if len(samples) == 1:
        return f"{samples[0]:7.1f} ms"
    return f"{statistics.mean(samples):7.1f} ms (min {min(samples):.1f} / max {max(samples):.1f})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csvs", nargs="*", type=Path,
                    help="OOB CSV files to benchmark (defaults: known big files).")
    ap.add_argument("--drills", type=Path, default=DEFAULT_DRILLS,
                    help="Path to drills.csv (formation archetypes).")
    ap.add_argument("--repeats", type=int, default=3,
                    help="How many times to repeat each timed op (default: 3).")
    args = ap.parse_args()

    csvs = args.csvs or [c for c in DEFAULT_CSVS if c.exists()]
    if not csvs:
        print("No CSV files to benchmark. Pass paths explicitly or fix the default base dir.")
        return 1

    populate_formation_archetypes_from_csv(str(args.drills))
    app = QApplication.instance() or QApplication([])

    print(f"Benchmarking {len(csvs)} file(s), {args.repeats} repeat(s) each\n")
    header = f"{'CSV':<58} {'rows':>6} {'load':>14} {'tree':>14} {'build_strength':>28}"
    print(header)
    print("-" * len(header))

    for csv_path in csvs:
        if not csv_path.exists():
            print(f"  skipping (missing): {csv_path}")
            continue

        oob = OOBData()
        load_samples = time_op(lambda: oob.load_csv(str(csv_path)), args.repeats)
        row_count = len(oob.df)

        tree = OOBTreeWidget(oob)
        tree_samples = time_op(lambda: tree.populate(), args.repeats)

        # Cold = first call builds cache; warm = subsequent calls hit cache.
        def cold_warm():
            _ = oob.build_strength(0)
            _ = oob.build_strength(0)

        bs_samples = time_op(cold_warm, args.repeats)

        print(f"{csv_path.name:<58} {row_count:>6} "
              f"{fmt(load_samples):>14} {fmt(tree_samples):>14} {fmt(bs_samples):>28}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
