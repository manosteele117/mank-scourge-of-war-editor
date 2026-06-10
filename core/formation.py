from typing import List, Self
import traceback
import re


class FormationArchetype:
    formations: dict[str, 'FormationArchetype'] = {}

    def __init__(self, drill: List[str]):
        self.definition = drill[0].split(',')
        self.layout = drill[1:]

        self.name = self.definition[0].strip()
        self.drill_id = self.definition[1].strip()
        self.rows = int(self.definition[2])
        self.columns = int(self.definition[3])
        self.row_dist = self.definition[4].strip()
        self.col_dist = self.definition[5].strip()
        self.sub_form = self.definition[6].strip()
        self.keep_form = self.definition[7].strip()
        self.can_wheel = self.definition[8].strip()
        self.can_fight = self.definition[9].strip()
        self.move_rate_mod = self.definition[10].strip()
        self.about_face = self.definition[11].strip()
        self.arty_form = self.definition[12].strip()
        self.min_enemy = self.definition[13].strip()
        self.fire_mod = self.definition[14].strip()
        self.melee_mod = self.definition[15].strip()
        self.cant_move = self.definition[16].strip()
        self.cant_counter_charge = self.definition[17].strip()
        self.cant_flank = self.definition[18].strip()
        self.cant_take_cover = self.definition[19].strip()
        self.notes = self.definition[20].strip()

        layout_2d = [x.split(',') for x in self.layout]

        self.full_strength_layout = {}
        for x, line in enumerate(layout_2d):
            for y, location in enumerate(line):
                pos_info = self.parse_layout_entry(location)
                if pos_info.get("seq"):
                    self.full_strength_layout[pos_info['seq']] = (x, y, pos_info)

        FormationArchetype.formations[self.drill_id] = self

    def parse_layout_entry(self, entry: str) -> dict:
        entry = entry.strip()
        if not entry:
            return {}

        if ')' in entry:
            inner_str, seq_str = entry.rsplit(')', 1)
            seq_str = seq_str.strip()
            if inner_str.startswith('('):
                inner_str = inner_str[1:]
        else:
            inner_str = ""
            seq_str = entry.strip()

        parts = inner_str.split('-') if inner_str else []

        return {
            'row_dist':       self.clean_up_row_or_col_dist(parts[0].strip() if len(parts) > 0 else "0", self.row_dist),
            'col_dist':       self.clean_up_row_or_col_dist(parts[1].strip() if len(parts) > 1 else "0", self.col_dist),
            'sprite':    parts[2].strip() if len(parts) > 2 else 0,
            'facing':    parts[3].strip() if len(parts) > 3 else 0,
            'subformation': parts[4].strip() if len(parts) > 4 else self.sub_form,
            'subtype': parts[5].strip() if len(parts) > 5 else None,
            'lock':      parts[6].strip() if len(parts) > 6 else None,
            'seq':       seq_str,
        }

    def clean_up_row_or_col_dist(self, dist_str: str, parent_dist: str) -> str:
        plus = "+" if dist_str.endswith('+') or parent_dist.endswith('+') else ""
        dist_float = float(dist_str.rstrip('+')) + float(parent_dist.rstrip('+'))
        return f"{dist_float}{plus}"

    def __str__(self):
        return f"Formation: {self.name}, ID: {self.drill_id}"


class ActualFormation:
    def __init__(self, archetype_id: str, strength: list[Self] | int,
                 child_row_indices: list[int] | None = None):
        self.archetype = FormationArchetype.formations[archetype_id]
        self.strength = strength
        self.child_row_indices = child_row_indices
        self.full_strength_layout = FormationArchetype.formations[archetype_id].full_strength_layout
        self.length = None
        self.depth = None
        self.subunit_dimensions = {}
        self.get_dimensions()
    
    def __str__(self):
        return f"Formation: {self.archetype.name}, Subunits/Strength: {self.strength}."
    
    def __repr__(self):
        return f"Formation: {self.archetype.name}, Subunits/Strength: {self.strength}."

    def get_layout(self) -> dict:
        layout: dict[int, tuple[float, float]] = {}
        for seq, location in self.full_strength_layout.items():
            if isinstance(self.strength, list):
                idx = int(seq) - 1
                if 0 <= idx < len(self.strength):
                    if int(seq) <= 2 or self.strength[idx] is not None:
                        layout[seq] = location
            elif isinstance(self.strength, int):
                if int(seq) <= self.strength:
                    layout[seq] = location
        return layout

    def get_positions(self) -> dict:
        layout = self.get_layout()

        origin_data = layout.get('1')
        if origin_data is None:
            return {}
        origin_row, origin_col, loc_info = origin_data

        rebased_layout = {}
        for seq in layout:
            x, y, info = layout[seq]
            rebased_layout[seq] = (x - origin_row, y - origin_col, info)

        positions = {}
        sorted_seqs = sorted(rebased_layout.keys(), key=lambda s: int(s) if s.isdigit() else float('inf'))

        for seq in sorted_seqs:
            try:
                if seq in ['1', '2'] and isinstance(self.strength, list):
                    self.subunit_dimensions[seq] = 2.5, 1.8
                elif isinstance(self.strength, list) and int(seq) <= len(self.strength):
                    subunit = self.strength[int(seq) - 1]
                    if subunit is None:
                        self.subunit_dimensions[seq] = 2.5, 1.8
                    else:
                        self.subunit_dimensions[seq] = subunit.get_dimensions()
                else:
                    # 0,0 is hack because spacing is already taken into account, this should only effect level 6 units. 
                    # Certain formations are still off, like columns in particular for some reason. But much closer than before
                    self.subunit_dimensions[seq] = 0,0 # float(self.archetype.col_dist.rstrip('+')), float(self.archetype.row_dist.rstrip('+'))
            except Exception:
                raise Exception(f"Error calculating dimensions for seq {seq}: {traceback.format_exc()}")

        base_row_dist = float(str(self.archetype.row_dist).rstrip('+'))
        base_col_dist = float(str(self.archetype.col_dist).rstrip('+'))
        row_dist_plus = self.archetype.row_dist.rstrip(',').endswith('+')
        col_dist_plus = self.archetype.col_dist.rstrip(',').endswith('+')

        col_max_length = {}
        per_cell_dist = {}
        col_row_depth = {}  # col -> {row -> depth} for per-column depth tracking

        for seq in sorted_seqs:
            grid_x, grid_y, pos_info = rebased_layout[seq]
            length, depth = self.subunit_dimensions[seq]
            if grid_y not in col_max_length:
                col_max_length[grid_y] = length
            else:
                col_max_length[grid_y] = max(col_max_length[grid_y], length)
            if grid_y not in col_row_depth:
                col_row_depth[grid_y] = {}
            col_row_depth[grid_y][grid_x] = max(col_row_depth[grid_y].get(grid_x, 0), depth)

        for seq_str, (gx, gy, pos_info) in self.full_strength_layout.items():
            cell_row_dist = float(str(pos_info.get('row_dist', base_row_dist)).rstrip('+'))
            override = cell_row_dist - base_row_dist
            if override != 0:
                per_cell_dist[(gx - origin_row, gy - origin_col)] = override

        origin_row, origin_col, _ = origin_data
        all_grid_x = list(range(0 - origin_row, self.archetype.rows - origin_row))
        all_grid_y = list(range(0 - origin_col, self.archetype.columns - origin_col))

        propagated = {}
        for gx in all_grid_x:
            row_ov = 0
            for gy in all_grid_y:
                ov = per_cell_dist.get((gx, gy), 0)
                if ov != 0:
                    row_ov = ov
                    break
            for gy in all_grid_y:
                if (gx, gy) in per_cell_dist:
                    ov = per_cell_dist[(gx, gy)]
                else:
                    ov = row_ov
                if gx < 0:
                    propagated[(gx, gy)] = base_row_dist - ov
                else:
                    propagated[(gx, gy)] = ov if ov != 0 else base_row_dist

        col_row_offsets = {}
        for gy in all_grid_y:
            ov_at_origin = per_cell_dist.get((0, gy), 0)
            col_row_offsets[gy] = {0: ov_at_origin}
            for gx in [g for g in all_grid_x if g > 0]:
                prev_gx = max((g for g in all_grid_x if g < gx), default=0)
                gap = propagated.get((gx, gy), base_row_dist)
                if row_dist_plus:
                    prev_depth = col_row_depth.get(gy, {}).get(prev_gx, 0)
                    curr_depth = col_row_depth.get(gy, {}).get(gx, 0)
                    gap += (prev_depth + curr_depth) / 2
                col_row_offsets[gy][gx] = col_row_offsets[gy][prev_gx] + gap
            for gx in reversed([g for g in all_grid_x if g < 0]):
                next_gx = min((g for g in all_grid_x if g > gx), default=0)
                next_ov = per_cell_dist.get((next_gx, gy), 0)
                gap = next_ov if next_ov != 0 else base_row_dist
                if row_dist_plus:
                    next_depth = col_row_depth.get(gy, {}).get(next_gx, 0)
                    curr_depth = col_row_depth.get(gy, {}).get(gx, 0)
                    gap += (next_depth + curr_depth) / 2
                col_row_offsets[gy][gx] = col_row_offsets[gy][next_gx] - gap

        col_offsets = {0: 0}
        for gy in [g for g in all_grid_y if g > 0]:
            prev_gy = max((g for g in all_grid_y if g < gy), default=0)
            col_offsets[gy] = col_offsets[prev_gy] + (col_max_length.get(prev_gy, 0) + col_max_length.get(gy, 0)) / 2 + base_col_dist
        for gy in reversed([g for g in all_grid_y if g < 0]):
            next_gy = min((g for g in all_grid_y if g > gy), default=0)
            col_offsets[gy] = col_offsets[next_gy] - (col_max_length.get(next_gy, 0) + col_max_length.get(gy, 0)) / 2 - base_col_dist

        for seq in sorted_seqs:
            grid_x, grid_y, pos_info = rebased_layout[seq]

            if seq == '1':
                length, depth = self.subunit_dimensions[seq]
                positions[seq] = (-length / 2, 0, length, depth)
            else:
                x_offset = col_offsets.get(grid_y, 0)
                y_offset = col_row_offsets.get(grid_y, {}).get(grid_x, 0)
                length, depth = self.subunit_dimensions[seq]
                positions[seq] = (x_offset - length / 2, y_offset, length, depth)

        if '2' in positions and '1' in positions:
            shift_y = -positions['2'][1]
            if shift_y != 0:
                for seq in positions:
                    x, y, l, d = positions[seq]
                    positions[seq] = (x, y + shift_y, l, d)

        return positions

    def get_dimensions(self) -> tuple:
        layout = self.get_positions()
        if not layout:
            return (10, 10)
        all_left = [x for x, y, l, d in layout.values()]
        all_right = [x + l for x, y, l, d in layout.values()]
        all_top = [y for x, y, l, d in layout.values()]
        all_bottom = [y + d for x, y, l, d in layout.values()]
        length = max(all_right) - min(all_left)
        depth = max(all_bottom) - min(all_top)
        self.length = length
        self.depth = depth
        origin = layout.get('2') or layout.get('1')
        if origin:
            ox, oy = origin[0], origin[1]
            self.origin_offset_x = ox - min(all_left)
            self.origin_offset_y = oy - min(all_top)
        else:
            self.origin_offset_x = length / 2
            self.origin_offset_y = depth / 2
        return length, depth


def populate_formation_archetypes_from_csv(file_path):
    """Parse formation definitions from a CSV file, reading blocks of lines."""
    FormationArchetype.formations.clear()
    with open(file_path, 'r', encoding='cp1252') as f:
        lines = f.readlines()

    data_lines = lines[1:]

    lvl6_blocks = []
    lvl5_blocks = []
    lvl4_blocks = []
    lvl3_blocks = []
    lvl2_blocks = []
    misc_blocks = []

    i = 0
    while i < len(data_lines):
        line = data_lines[i].strip()
        if not line:
            i += 1
            continue

        parts = line.split(',')
        drill_id = parts[1].strip() if len(parts) > 1 else ""
        if not drill_id.startswith("DRIL_"):
            i += 1
            continue

        block_lines = [data_lines[i].strip()]
        i += 1
        valid_cell = re.compile(r"^(\d+|\(.+\)\d+)$")
        while i < len(data_lines):
            block_line = data_lines[i].strip()
            if not block_line:
                break
            block_parts = block_line.split(',')
            col1 = block_parts[0].strip() if block_parts else ""
            col2 = block_parts[1].strip() if len(block_parts) > 1 else ""
            if col1.lower() == 'x' or col2.lower() == 'x' or col2.startswith("DRIL_"):
                break
            if not all(valid_cell.match(cell.strip()) or not cell.strip()
                       for cell in block_parts):
                i += 1
                continue
            block_lines.append(block_line)
            i += 1

        if "DRIL_Lvl6" in block_lines[0].split(',')[1]:
            lvl6_blocks.append(block_lines)
        elif "DRIL_Lvl5" in block_lines[0].split(',')[1]:
            lvl5_blocks.append(block_lines)
        elif "DRIL_Lvl4" in block_lines[0].split(',')[1]:
            lvl4_blocks.append(block_lines)
        elif "DRIL_Lvl3" in block_lines[0].split(',')[1]:
            lvl3_blocks.append(block_lines)
        elif "DRIL_Lvl2" in block_lines[0].split(',')[1]:
            lvl2_blocks.append(block_lines)
        elif "DRIL_" in block_lines[0].split(',')[1]:
            misc_blocks.append(block_lines)
        else:
            print(f"Unrecognized formation type in block starting with: {block_lines[0]}")


    for block in lvl6_blocks + lvl5_blocks + lvl4_blocks + lvl3_blocks + lvl2_blocks + misc_blocks:
        try:
            FormationArchetype(block)
        except Exception as e:
            traceback.print_exc()
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
