import sys
import argparse
from pathlib import Path

sys.path.insert(0, '.')
from core.formation import populate_formation_archetypes_from_csv
from core.oob_model import OOBData
from core.utilities import plot_rectangles

BASE = Path('C:/Steam/steamapps/common/Scourge Of War - Remastered/Base')

populate_formation_archetypes_from_csv(str(BASE / 'Logistics' / 'drills.csv'))
oob = OOBData()
oob.load_csv(str(BASE / 'OOBs' / 'OOB_SB_test_4corps.csv'))

parser = argparse.ArgumentParser()
parser.add_argument('--plot', action='store_true', help='Plot formation layout')
args = parser.parse_args()

ROW_INDEX = 3
FORMATION = 'DRIL_Lvl5_Inf_Column'

fmt = oob.build_strength(ROW_INDEX, archetype_id=FORMATION)
pos = fmt.get_positions()
name = str(oob.df.iloc[ROW_INDEX].get('Name', ''))

print(f'Unit: {name} (row {ROW_INDEX})')
print(f'Formation: {FORMATION}')
print(f'Row dist: {fmt.archetype.row_dist}')
print(f'Col dist: {fmt.archetype.col_dist}')
print(f'Children: {len([v for v in fmt.strength if v is not None])}')
print()

print('Bounding box:')
print(f'  length: {fmt.length:.1f}')
print(f'  depth:  {fmt.depth:.1f}')
print(f'  origin offset: ({fmt.origin_offset_x:.1f}, {fmt.origin_offset_y:.1f})')
print()

print('Child placements:')
children = oob.get_direct_children(ROW_INDEX, exclude_supply=True)
for seq_str in sorted(pos.keys(), key=lambda s: int(s) if s.isdigit() else 0):
    seq = int(seq_str)
    x, y, l, d = pos[seq_str]
    if seq <= 2:
        label = 'commander' if seq == 1 else 'standard'
    elif seq - 1 < len(fmt.child_row_indices) and fmt.child_row_indices[seq - 1] is not None:
        child_row = fmt.child_row_indices[seq - 1]
        child_name = str(oob.df.iloc[child_row].get('Name', ''))[:30]
        child_cls = str(oob.df.iloc[child_row].get('CLASS', ''))
        label = f'{child_name} ({child_cls})'
    else:
        label = '(empty slot)'
    print(f'  seq {seq:2d}: x={x:8.1f} y={y:8.1f}  len={l:5.1f} dep={d:5.1f}  {label}')

print()
print('Child row indices (seq -> oob_row):')
for i, row_idx in enumerate(fmt.child_row_indices):
    if row_idx is not None:
        print(f'  seq {i+1:2d}: row {row_idx}')

if args.plot:
    plot_rectangles(pos, title=f'{name} - {FORMATION}',
                    origin_offsets=(fmt.origin_offset_x, fmt.origin_offset_y))
