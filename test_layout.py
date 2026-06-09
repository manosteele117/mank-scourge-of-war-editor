import sys
from pathlib import Path

sys.path.insert(0, '.')
from core.formation import populate_formation_archetypes_from_csv, ActualFormation
from core.oob_model import OOBData
from core.utilities import plot_rectangles

BASE = Path('C:/Steam/steamapps/common/Scourge Of War - Remastered/Base')

# Formation overrides per level (None = use the OOB's default).
LEVEL_FORMATIONS: dict[int, str | None] = {
    6: None,
    5: None,
    4: "DRIL_Lvl4_Inf_Div_DoubleLine_FR",
    3: "DRIL_Lvl3_Inf_Line_Corps_FR",
    2: None,
}

# Standalone formation tests: (archetype_id, head_count, label)
# Uses build_strength so artillery scale (15) vs infantry scale (6) is applied correctly
STANDALONE_TESTS = [
    #("DRIL_Lvl6_Inf_Line_3L", 300, "Lvl6 Inf Line (300 men)"),
    ("DRIL_Lvl6_Art_Line", 30, "Lvl6 Art Line (30guys)"),
    ("DRIL_Lvl6_Art_March", 30, "Lvl6 Art March (30guys)"),
    #("DRIL_Lvl5_Art_Line", 30, "Lvl5 Art Line (8 gun children)"),
    #("DRIL_Lvl5_Art_Column", 30, "Lvl5 Art Column (8 gun children)"),
]

DETAILED = True
PLOT = True


def find_first_at_level(oob, level):
    for idx in range(len(oob.df)):
        if oob.get_level(idx) == level:
            info = oob.unit_info(idx)
            return idx, info.name
    return None, None


def find_first_with_class(oob, class_substr):
    for idx in range(len(oob.df)):
        cls = str(oob.df.iloc[idx].get("CLASS", ""))
        if class_substr in cls:
            info = oob.unit_info(idx)
            return idx, info.name
    return None, None


def rects_overlap(a, b):
    ax, ay, al, ad = a
    bx, by, bl, bd = b
    return ax < bx + bl and ax + al > bx and ay < by + bd and ay + ad > by


def rects_touching(a, b):
    ax, ay, al, ad = a
    bx, by, bl, bd = b
    touch_x = abs((ax + al / 2) - (bx + bl / 2)) < (al + bl) / 2 + 0.01
    touch_y = abs((ay + ad / 2) - (by + bd / 2)) < (ad + bd) / 2 + 0.01
    edges_close_x = (abs(ax - (bx + bl)) < 0.01 or abs((ax + al) - bx) < 0.01) and touch_y
    edges_close_y = (abs(ay - (by + bd)) < 0.01 or abs((ay + ad) - by) < 0.01) and touch_x
    return edges_close_x or edges_close_y


def check_formation(name, positions):
    all_pass = True
    seqs = sorted(positions.keys(), key=lambda s: int(s) if s.isdigit() else 0)
    for i in range(len(seqs)):
        for j in range(i + 1, len(seqs)):
            s1, s2 = seqs[i], seqs[j]
            r1, r2 = positions[s1], positions[s2]
            if rects_overlap(r1, r2):
                print(f"  OVERLAP: seq {s1} and seq {s2}")
                all_pass = False
            elif rects_touching(r1, r2):
                print(f"  TOUCHING: seq {s1} and seq {s2}")
                all_pass = False
    return all_pass


def run_single_test(label, fmt, overall_pass):
    pos = fmt.get_positions()
    print(f"\n{label} ({len(pos)} units, {fmt.length:.1f} x {fmt.depth:.1f})")
    if DETAILED:
        print(f"  Origin offset: ({fmt.origin_offset_x:.2f}, {fmt.origin_offset_y:.2f})")
        for seq in sorted(pos.keys(), key=lambda s: int(s) if s.isdigit() else 0):
            x, y, l, d = pos[seq]
            print(f"  seq {seq}: ({x:7.1f}, {y:7.1f}) [{l:.1f} x {d:.1f}]")
    passed = check_formation(label, pos)
    if passed:
        print(f"  PASS: no overlaps or touching")
    overall_pass &= passed
    if PLOT:
        plot_rectangles(pos, title=label,
                        origin_offsets=(fmt.origin_offset_x, fmt.origin_offset_y))
    return overall_pass


def compute_strength(archetype_id, head_count):
    """Mirror the head_count -> sprite-count logic from OOBData.build_strength."""
    from constants import SPRITE_SCALE
    art_scale = 15 if "Art" in archetype_id else SPRITE_SCALE
    return int(head_count / art_scale)


def main():
    populate_formation_archetypes_from_csv(str(BASE / 'Logistics' / 'drills.csv'))
    oob = OOBData()
    oob.load_csv(str(BASE / 'OOBs' / 'OOB_SB_test_4corps.csv'))
    overall_pass = True

    # # ── Standalone formation tests ──
    # for arch_id, head_count, label in STANDALONE_TESTS:
    #     strength = compute_strength(arch_id, head_count)
    #     fmt = ActualFormation(arch_id, strength)
    #     overall_pass = run_single_test(label, fmt, overall_pass)

    # ── Level 5 artillery battery from OOB (Boquero) ──
    # art_row, art_name = find_first_with_class(oob, "UGLB_FR_Art_Cdr_Bty")
    # if art_row is not None:
    #     fmt = oob.build_strength(art_row)
    #     overall_pass = run_single_test(f"OOB: {art_name} (Lvl5 battery)", fmt, overall_pass)

    # ── Level 4 division (Friant with mixed inf+art) ──
    for level in [3, 4, 5, 6]:
        row, name = find_first_at_level(oob, level)
        if row is None:
            print(f"Level {level}: NOT FOUND"); continue
        override = LEVEL_FORMATIONS.get(level)
        fmt = oob.build_strength(row, archetype_id=override)
        label = f"{override}" if override else name
        overall_pass = run_single_test(f"Level {level}: {label}", fmt, overall_pass)

    print()
    print("ALL PASSED" if overall_pass else "FAILURES DETECTED")


if __name__ == '__main__':
    main()
