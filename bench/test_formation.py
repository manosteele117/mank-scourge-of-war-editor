"""Unified formation layout test runner.

Usage:
    python bench/test_formation.py                          # run all tests
    python bench/test_formation.py --test corps             # run a single test by name
    python bench/test_formation.py --test corps --plot      # run and show plot window
    python bench/test_formation.py --all --plot             # run all and show each plot

Each test builds a formation for a specific OOB row, prints child placements,
and runs any formation-specific checks (overlap, alignment, etc.).
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, '..')
from core.formation import populate_formation_archetypes_from_csv
from core.oob_model import OOBData
from core.utilities import plot_rectangles

BASE = Path('C:/Steam/steamapps/common/Scourge Of War - Remastered/Base')

# ── Test configurations ────────────────────────────────────────────
# Each tuple: (test_name, row_index, formation_id, description)
TEST_CASES = [
    ("corps",             1,  "DRIL_Lvl3_Inf_Line_Corps_FR",        "Multi-row corps with overrides at gx=0"),
    ("brigade",           3,  "DRIL_Lvl5_Inf_Column",               "Single-column brigade growth with overrides"),
    ("brigade_line",      3,  "DRIL_Lvl5_Inf_Brig_DoubleLine_Fr",   "Two-row brigade line formation"),
    ("division",         59,  "DRIL_Lvl4_Inf_Reserves",             "Reserve column with artillery at rear"),
    ("division_column",  59,  "DRIL_Lvl4_Inf_Column",               "Division column with all children in front"),
    ("division_line",    59,  "DRIL_Lvl4_Inf_Div_Line_FR",          "Division line variant"),
    ("art_line",         70,  "DRIL_Lvl5_Art_Line",                 "Artillery line — all units ahead of commander"),
]


def format_child_label(formation, oob, sequence_number):
    """Return a human-readable label for a child slot."""
    if sequence_number <= 2:
        return 'commander' if sequence_number == 1 else 'standard'
    child_index = sequence_number - 1
    if child_index < len(formation.child_row_indices) and formation.child_row_indices[child_index] is not None:
        child_row = formation.child_row_indices[child_index]
        child_name = str(oob.df.iloc[child_row].get('Name', ''))[:30]
        child_class = str(oob.df.iloc[child_row].get('CLASS', ''))
        return f'{child_name} ({child_class})'
    return '(empty slot)'


def run_test(test_name, row_index, formation_id, description, oob, plot=False):
    """Build a formation, print its layout, and run formation-specific checks."""
    formation = oob.build_strength(row_index, archetype_id=formation_id)
    positions = formation.get_positions()
    unit_name = str(oob.df.iloc[row_index].get('Name', ''))

    print(f'=== {test_name}: {unit_name} (row {row_index}) ===')
    print(f'Formation: {formation_id}')
    print(f'Description: {description}')
    print(f'Children: {len([v for v in formation.strength if v is not None])}')
    print()

    # Always show spacing parameters if available
    print(f'Row dist: {formation.archetype.row_dist}')
    print(f'Col dist: {formation.archetype.col_dist}')
    print()

    print('Bounding box:')
    print(f'  length: {formation.length:.1f}')
    print(f'  depth:  {formation.depth:.1f}')
    print(f'  origin offset: ({formation.origin_offset_x:.1f}, {formation.origin_offset_y:.1f})')
    print()

    print('Child placements:')
    for seq_str in sorted(positions.keys(), key=lambda s: int(s) if s.isdigit() else 0):
        seq = int(seq_str)
        x_pos, y_pos, length, depth = positions[seq_str]
        label = format_child_label(formation, oob, seq)
        print(f'  seq {seq:2d}: x={x_pos:8.1f} y={y_pos:8.1f}  len={length:5.1f} dep={depth:5.1f}  {label}')

    print()
    print('Child row indices (seq -> oob_row):')
    for index, row_idx in enumerate(formation.child_row_indices):
        if row_idx is not None:
            print(f'  seq {index+1:2d}: row {row_idx}')

    # ── Formation-specific checks ───────────────────────────────────

    if test_name == "division":
        check_overlap(positions, seq_a='3', seq_b='12',
                      label_a='seq 3 (brigade)', label_b='seq 12 (artillery)')

    if test_name == "art_line":
        check_y_alignment(positions)

    print()

    if plot:
        plot_rectangles(positions,
                        title=f'{unit_name} - {formation_id}',
                        origin_offsets=(formation.origin_offset_x, formation.origin_offset_y))


def check_overlap(positions, seq_a, seq_b, label_a, label_b):
    """Verify that two units do not overlap in the y direction."""
    print(f'Overlap check ({label_a} vs {label_b}):')
    if seq_a not in positions or seq_b not in positions:
        print(f'  {seq_a} or {seq_b} not in layout')
        return

    _, y_a, _, depth_a = positions[seq_a]
    _, y_b, _, depth_b = positions[seq_b]

    front_a = y_a - depth_a / 2
    back_a = y_a + depth_a / 2
    front_b = y_b - depth_b / 2
    back_b = y_b + depth_b / 2

    print(f'  {seq_a}: y={y_a:8.1f}  front={front_a:8.1f}  back={back_a:8.1f}  depth={depth_a:.1f}')
    print(f'  {seq_b}: y={y_b:8.1f}  front={front_b:8.1f}  back={back_b:8.1f}  depth={depth_b:.1f}')

    gap = front_b - back_a
    print(f'  gap (front_{seq_b} - back_{seq_a}): {gap:.1f}')
    if gap >= 0:
        print(f'  PASS: {seq_b} is fully behind {seq_a}')
    else:
        print(f'  FAIL: {seq_b} overlaps {seq_a} by {-gap:.1f}')


def check_y_alignment(positions):
    """Verify that all non-commander units share the same y position."""
    print('Y-alignment check (gx=0 row):')
    gx0_entries = []
    for seq_str in sorted(positions.keys(), key=lambda s: int(s) if s.isdigit() else 0):
        seq = int(seq_str)
        if seq > 2:
            _, y_pos, _, _ = positions[seq_str]
            gx0_entries.append((seq, y_pos))

    if gx0_entries:
        y_values = [y for _, y in gx0_entries]
        print(f'  min y: {min(y_values):.1f}, max y: {max(y_values):.1f}')
        for seq, y_pos in gx0_entries:
            print(f'  seq {seq:2d}: y={y_pos:8.1f}')


# ── Main ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run formation layout tests')
    parser.add_argument('--test', type=str, help='Run a single test by name')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--plot', action='store_true', help='Show plot window for each test')
    args = parser.parse_args()

    populate_formation_archetypes_from_csv(str(BASE / 'Logistics' / 'drills.csv'))
    oob = OOBData()
    oob.load_csv(str(BASE / 'OOBs' / 'OOB_SB_test_4corps.csv'))

    if args.test:
        # Run a single named test
        matched = [tc for tc in TEST_CASES if tc[0] == args.test]
        if not matched:
            print(f"Unknown test: {args.test}")
            print(f"Available tests: {', '.join(tc[0] for tc in TEST_CASES)}")
            sys.exit(1)
        run_test(*matched[0], oob=oob, plot=args.plot)
    else:
        # Run all tests
        for test_config in TEST_CASES:
            run_test(*test_config, oob=oob, plot=args.plot)
