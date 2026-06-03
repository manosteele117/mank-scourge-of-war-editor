import sys
sys.path.insert(0, '.')
from core.formation import populate_formation_archetypes_from_csv, ActualFormation
from core.oob_model import OOBData
from core.utilities import plot_rectangles

populate_formation_archetypes_from_csv('C:\\Steam\\steamapps\\common\\Scourge Of War - Remastered\\Base\\Logistics\\drills.csv')

oob = OOBData()
oob.load_csv('C:\\Steam\\steamapps\\common\\Scourge Of War - Remastered\\Base\\OOBs\\OOB_SB_test_4corps.csv')


def build_strength(row_index: int) -> ActualFormation:
    sub_row = oob.get_row(row_index)
    archetype_id = sub_row.get("Formation", "")
    level = oob.get_level_from_hierarchy(sub_row)
    if level is None:
        raise ValueError(f"Cannot determine level for row {row_index}")
    if level >= 6:
        head_count = sub_row.get("Head Count", 0)
        return ActualFormation(archetype_id=archetype_id, strength=int(float(head_count / 6)))
    else:
        all_sub_indices = oob.get_subordinate_row_indices(row_index)
        direct_children = [
            idx for idx in all_sub_indices
            if oob.get_level_from_hierarchy(oob.get_row(idx)) == level + 1
            and "SupplyWagon" not in oob.get_row(idx).get("Formation", "")
        ]
        sub_formations = [None, None] + [build_strength(idx) for idx in direct_children]
        return ActualFormation(archetype_id=archetype_id, strength=sub_formations)


def find_unit_row(oob, name_fragment):
    for idx, row in oob.df.iterrows():
        if name_fragment in str(row.get('NAME1', '')):
            return idx, str(row.get('NAME1', ''))
    return None, None


def has_overlap(positions):
    entries = [(seq, x, y, l, d) for seq, (x, y, l, d) in positions.items()]
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            s1, x1, y1, l1, d1 = entries[i]
            s2, x2, y2, l2, d2 = entries[j]
            cx1, cx2 = x1 + l1 / 2, x2 + l2 / 2
            overlap_x = abs(cx1 - cx2) < (l1 + l2) / 2
            overlap_y = y1 < y2 + d2 and y2 < y1 + d1
            if overlap_x and overlap_y:
                return True, s1, s2
    return False, None, None


def has_touching(positions):
    entries = [(seq, x, y, l, d) for seq, (x, y, l, d) in positions.items()]
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            s1, x1, y1, l1, d1 = entries[i]
            s2, x2, y2, l2, d2 = entries[j]
            cx1, cx2 = x1 + l1 / 2, x2 + l2 / 2
            overlap_x = abs(cx1 - cx2) < (l1 + l2) / 2
            touching_y = abs((y1 + d1) - y2) < 0.01 or abs((y2 + d2) - y1) < 0.01
            if overlap_x and touching_y:
                return True, s1, s2
    return False, None, None


def check_no_overlap(positions, label):
    result, s1, s2 = has_overlap(positions)
    if result:
        print(f"  FAIL: {label} overlap between seq {s1} and seq {s2}")
        return False
    print(f"  PASS: {label} no overlaps")
    return True


def check_no_touching(positions, label):
    result, s1, s2 = has_touching(positions)
    if result:
        print(f"  FAIL: {label} touching between seq {s1} and seq {s2}")
        return False
    print(f"  PASS: {label} no touching")
    return True


def check_centers_aligned_x(positions, label):
    combat = {s: (x, y, l, d) for s, (x, y, l, d) in positions.items() if s not in ('1', '2')}
    if not combat:
        print(f"  SKIP: {label} no combat units")
        return True
    centers_x = [x + l / 2 for x, y, l, d in combat.values()]
    if max(centers_x) - min(centers_x) > 0.01:
        print(f"  FAIL: {label} X centers not aligned: min={min(centers_x):.1f} max={max(centers_x):.1f}")
        return False
    print(f"  PASS: {label} all combat unit centers aligned at x={centers_x[0]:.1f}")
    return True


all_pass = True


print("=" * 60)
print("Case 1: Friant (Column of Battalions)")
print("=" * 60)
row_idx, name = find_unit_row(oob, 'Friant')
if row_idx is None:
    print("Unit not found")
    sys.exit(1)
print(f"Found '{name}' at row {row_idx}")
friant = build_strength(row_idx)
friant_pos = friant.get_positions()
print(f"Positions ({len(friant_pos)} units):")
for seq, (x, y, l, d) in sorted(friant_pos.items(), key=lambda s: int(s[0]) if s[0].isdigit() else 0):
    print(f"  seq {seq}: x={x:.1f} y={y:.1f} length={l:.1f} depth={d:.1f}")

print("\nTests:")
all_pass &= check_no_overlap(friant_pos, "Friant top-level")
all_pass &= check_centers_aligned_x(friant_pos, "Friant top-level")

plot_rectangles(friant_pos, title=f"Formation: {name}")

print("\n" + "=" * 60)
print("Case 2: JeanMartin Petit (Column)")
print("=" * 60)
row_idx2, name2 = find_unit_row(oob, 'Petit')
if row_idx2 is None:
    print("Unit not found")
    sys.exit(1)
name2 = 'JeanMartin Petit'
print(f"Found '{name2}' at row {row_idx2}")
jm = build_strength(row_idx2)
jm_pos = jm.get_positions()
print(f"Positions ({len(jm_pos)} units):")
for seq, (x, y, l, d) in sorted(jm_pos.items(), key=lambda s: int(s[0]) if s[0].isdigit() else 0):
    print(f"  seq {seq}: x={x:.1f} y={y:.1f} length={l:.1f} depth={d:.1f}")

print("\nTests:")
all_pass &= check_no_overlap(jm_pos, "JeanMartin top-level")
all_pass &= check_no_touching(jm_pos, "JeanMartin top-level")

combat_seqs = sorted([s for s in jm_pos if s not in ('1', '2')], key=lambda s: int(s))
if combat_seqs:
    min_top = min(jm_pos[s][1] for s in combat_seqs)
    expected_offset = 15.1
    actual_offset = min_top
    if abs(actual_offset - expected_offset) > 0.1:
        print(f"  FAIL: top row offset = {actual_offset:.1f}, expected {expected_offset}")
        all_pass = False
    else:
        print(f"  PASS: top row offset = {actual_offset:.1f} behind origin")

plot_rectangles(jm_pos, title=f"Formation: {name2}")

print("\n" + "=" * 60)
if all_pass:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED")
print("=" * 60)
