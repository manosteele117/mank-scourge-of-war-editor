from typing import List, Self
import traceback


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
    def __init__(self, archetype_id: str, strength: list[Self] | int):
        self.archetype = FormationArchetype.formations[archetype_id]
        self.strength = strength
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
                if int(seq) <= len(self.strength):
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
                if seq in ['1', '2']:
                    self.subunit_dimensions[seq] = 2.5, 1.8
                elif isinstance(self.strength, list) and int(seq) <= len(self.strength):
                    subunit = self.strength[int(seq) - 1]
                    if (subunit is None):
                        self.subunit_dimensions[seq] = 2.5, 1.8
                    self.subunit_dimensions[seq] = subunit.get_dimensions()
                else:
                    self.subunit_dimensions[seq] = float(self.archetype.col_dist), float(self.archetype.row_dist)
            except Exception:
                raise Exception(f"Error calculating dimensions for seq {seq}: {traceback.format_exc()}")

        for seq in sorted_seqs:
            grid_x, grid_y, pos_info = rebased_layout[seq]

            if seq == '1':
                length, depth = self.subunit_dimensions[seq]
                positions[seq] = (0, 0, length, depth)
            else:
                grow_col = str(pos_info['col_dist']).endswith('+')
                grow_row = str(pos_info['row_dist']).endswith('+')
                x_offset = grid_y * float(str(pos_info['col_dist']).rstrip('+'))
                y_offset = grid_x * float(str(pos_info['row_dist']).rstrip('+'))

                for prev_seq in sorted_seqs:
                    if prev_seq == seq:
                        break
                    prev_grid_x, prev_grid_y, _ = rebased_layout[prev_seq]
                    if prev_grid_y == grid_y and 0 <= prev_grid_x < grid_x and grow_row:
                        y_offset += (self.subunit_dimensions[prev_seq][1]/2 + self.subunit_dimensions[seq][1]/2) * (-1 if grid_x < 0 else 1)
                    if prev_grid_y == grid_y and grid_x < prev_grid_x <= 0 and grow_row:
                        y_offset += (self.subunit_dimensions[prev_seq][1]/2 + self.subunit_dimensions[seq][1]/2) * (-1 if grid_x < 0 else 1)
                    if prev_grid_x == grid_x and 0 <= prev_grid_y < grid_y and grow_col:
                        x_offset += (self.subunit_dimensions[prev_seq][0]/2 + self.subunit_dimensions[seq][0]/2) * (-1 if grid_y < 0 else 1)
                    if prev_grid_x == grid_x and grid_y < prev_grid_y <= 0 and grow_col:
                        x_offset += (self.subunit_dimensions[prev_seq][0]/2 + self.subunit_dimensions[seq][0]/2) * (-1 if grid_y < 0 else 1)

                length, depth = self.subunit_dimensions[seq]
                positions[seq] = (x_offset, y_offset, length, depth)

        return positions

    def get_dimensions(self) -> tuple:
        layout = self.get_positions()
        if not layout:
            return (10, 10)
        all_x = [pos[0] for pos in layout.values()]
        all_y = [pos[1] for pos in layout.values()]
        length = max(all_x) - min(all_x)
        depth = max(all_y) - min(all_y)
        self.length = length
        self.depth = depth
        return length, depth


def populate_formation_archetypes_from_csv(file_path):
    """Parse formation definitions from a CSV file, reading blocks of lines."""
    with open(file_path, 'r', encoding='utf-8') as f:
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

        block_lines = []
        while i < len(data_lines):
            block_line = data_lines[i].strip()
            if not block_line:
                break
            block_parts = block_line.split(',')
            col1 = block_parts[0].strip() if block_parts else ""
            col2 = block_parts[1].strip() if len(block_parts) > 1 else ""
            if col1.lower() == 'x' or col2.lower() == 'x' or not any(block_parts):
                break
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

    for block in lvl6_blocks:
        try:
            FormationArchetype(block)
        except Exception as e:
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    for block in lvl5_blocks:
        try:
            FormationArchetype(block)
        except Exception as e:
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    for block in lvl4_blocks:
        try:
            FormationArchetype(block)
        except Exception as e:
            traceback.print_exc()
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
