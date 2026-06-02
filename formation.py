from typing import List, Self
import traceback
from pprint import pp


class FormationArchetype:
    formations: dict[str, 'FormationArchetype'] = {}
    def __init__(self, drill: List[str]):
        self.definition = drill[0].split(',')
        self.layout = drill[1:]

        self.name = self.definition[0].strip()
        self.drill_id = self.definition[1].strip()
        self.rows = int(self.definition[2])  # number of rows in the formation
        self.columns = int(self.definition[3])  # number of units in each row
        self.row_dist = self.definition[4].strip()  # distance in yards between rows. Can have "+" to indicate dependence on child unit size.
        self.col_dist = self.definition[5].strip()  # distance in yards between units in the same row.  Can have "+" to indicate dependence on child unit size.
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
        
        # Parse all locations from the layout
        self.full_strength_layout = {}  # All locations defined in the formation
        for x, line in enumerate(layout_2d):
            for y, location in enumerate(line):
                pos_info = self.parse_layout_entry(location)
                if pos_info.get("seq"):
                    self.full_strength_layout[pos_info['seq']] = (x, y, pos_info)
        
        # Add to list of all loaded formations.
        FormationArchetype.formations[self.drill_id] = self

    def parse_layout_entry(self, entry: str) -> dict:
        """Parses a single location within a layout within the drills.csv file."""
        entry = entry.strip()
        if not entry:
            return {}

        # 1. Separate the optional parentheses group from the sequence number
        if ')' in entry:
            inner_str, seq_str = entry.rsplit(')', 1)
            seq_str = seq_str.strip()
            # Remove the opening parenthesis if present
            if inner_str.startswith('('):
                inner_str = inner_str[1:]
        else:
            # No parentheses: the entire string is just the sequence number
            inner_str = ""
            seq_str = entry.strip()

        parts = inner_str.split('-') if inner_str else []

        return {
            'row_dist':       self.clean_up_row_or_col_dist(parts[0].strip() if len(parts) > 0 else "0", self.row_dist),
            'col_dist':       self.clean_up_row_or_col_dist(parts[1].strip() if len(parts) > 1 else "0", self.col_dist),
            'sprite':    parts[2].strip() if len(parts) > 2 else 0, #  indexes into the unitglobal.csv file as to what specific sprite to use, leave 0 for default, valid values are currently 1-6
            'facing':    parts[3].strip() if len(parts) > 3 else 0, # integer specifying the number of degrees that the unit should face off of the flag bearer
            'subformation': parts[4].strip() if len(parts) > 4 else self.sub_form, # id of the sub formation to use for this slot, if it's not set, it uses the default for the formation
            'subtype': parts[5].strip() if len(parts) > 5 else None, # 1-Inf,2-Cav,3-Art, leave blank or zero for any
            'lock':      parts[6].strip() if len(parts) > 6 else None, # lock the position to be the exact place, they will never trail behind
            'seq':       seq_str # 1 - flagbearer, 2-300 men"
        }

    def clean_up_row_or_col_dist(self, dist_str: str, parent_dist: str) -> str:
        """Cleans up the row_dist and col_dist strings, ensuring they are in a consistent format."""
        plus = "+" if dist_str.endswith('+') or parent_dist.endswith('+') else ""
        dist_float = float(dist_str.rstrip('+')) + float(parent_dist.rstrip('+'))
        return f"{dist_float}{plus}"

    def __str__(self):
        return (f"Formation: {self.name}, ID: {self.drill_id}")


class ActualFormation:
    def __init__(self, archetype_id: str, strength: list[Self] | int):
        self.archetype = FormationArchetype.formations[archetype_id]
        self.strength = strength
        self.full_strength_layout = FormationArchetype.formations[archetype_id].full_strength_layout  # Layout at full strength.
        self.length = None
        self.depth = None
        self.subunit_dimensions = {}
        self.get_dimensions()
    
    def get_layout(self) -> dict:
        """
        Get the relative layout for a given strength (number of sub-units).
        Returns only the filtered layout for seq 1 through strength.
        """
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
        """
        Get the actual positions for this formation at a given strength.
        Returns a dict of seq to (x, y) coordinates in yards relative to seq 1 (flag bearer).
        
        Units are laid out sequentially, with each unit's position determined by:
        - Its grid position multiplied by row/column distances
        - Cumulative dimensions of previously placed units in the same row/column
        """
        layout = self.get_layout()
        
        # Rebase all positions relative to seq 1 (flag bearer)
        origin_data = layout.get('1')
        if origin_data is None:
            print("Seq 1 (flag bearer) not found in layout, cannot rebase positions.")
            return {}
        origin_row, origin_col, loc_info = origin_data

        rebased_layout = {}
        for seq in layout:
            x, y, info = layout[seq]
            rebased_layout[seq] = (x - origin_row, y - origin_col, info)

        positions = {}
        sorted_seqs = sorted(rebased_layout.keys(), key=lambda s: int(s) if s.isdigit() else float('inf'))
        # Determine sizes of all subunits in tree.
        for seq in sorted_seqs:
            try:
                if seq in ['1','2']:
                    self.subunit_dimensions[seq] = 2.5, 1.8  # Officer units, using man spacing from French regiments.
                elif isinstance(self.strength, list) and int(seq) <= len(self.strength):
                    subunit = self.strength[int(seq) - 3] # index accounts for officer units pre-placed.
                    self.subunit_dimensions[seq] = subunit.get_dimensions()
                else:
                    self.subunit_dimensions[seq] = float(self.archetype.col_dist), float(self.archetype.row_dist)
            except Exception:
                raise Exception(f"Error calculating dimensions for seq {seq}: {traceback.format_exc()}")
        # Process units in sequence order
        for seq in sorted_seqs:
            grid_x, grid_y, pos_info = rebased_layout[seq]
            
            if seq == '1':
                # First unit (flag bearer) at origin, centered on origin
                length, depth = self.subunit_dimensions[seq]
                positions[seq] = (0,0, length, depth)
            else:
                grow_col = str(pos_info['col_dist']).endswith('+')
                grow_row = str(pos_info['row_dist']).endswith('+')
                x_offset = grid_y * float(str(pos_info['col_dist']).rstrip('+'))
                y_offset = grid_x * float(str(pos_info['row_dist']).rstrip('+'))
                #x_offset = self._walk_spacing(grid_y, "col", rebased_layout)
                #y_offset = self._walk_spacing(grid_x, "row", rebased_layout)

                for prev_seq in sorted_seqs:
                    if prev_seq == seq:
                        break
                    prev_grid_x, prev_grid_y, _ = rebased_layout[prev_seq]
                    # if seq == '5':
                    #     print(f"Debug for seq 5: prev_seq={prev_seq}, prev_grid_x={prev_grid_x}, prev_grid_y={prev_grid_y}, grid_x={grid_x}, grid_y={grid_y}, grow_row={grow_row}, grow_col={grow_col}")
                    if prev_grid_y == grid_y and 0 <= prev_grid_x < grid_x and grow_row:
                        y_offset += (self.subunit_dimensions[prev_seq][1]/2 + self.subunit_dimensions[seq][1]/2) * (-1 if grid_x < 0 else 1)
                    if prev_grid_y == grid_y and grid_x < prev_grid_x <= 0 and grow_row:
                        y_offset += (self.subunit_dimensions[prev_seq][1]/2 + self.subunit_dimensions[seq][1]/2) * (-1 if grid_x < 0 else 1)
                    if prev_grid_x == grid_x and 0 <= prev_grid_y < grid_y and grow_col:
                        x_offset += (self.subunit_dimensions[prev_seq][0]/2 + self.subunit_dimensions[seq][0]/2) * (-1 if grid_y < 0 else 1)
                    if prev_grid_x == grid_x and grid_y < prev_grid_y <= 0 and grow_col:
                        x_offset += (self.subunit_dimensions[prev_seq][0]/2 + self.subunit_dimensions[seq][0]/2) * (-1 if grid_y < 0 else 1)
                # if seq == '5':
                #     print(f"Debug for seq 5: grid_x={grid_x}, grid_y={grid_y}, pos_info={pos_info}, x_offset={x_offset}, y_offset={y_offset}\n")

                length, depth = self.subunit_dimensions[seq]
                positions[seq] = (x_offset, y_offset, length, depth)

        return positions

    # def _get_spacing_for_coord(self, coord: int, axis: str, layout: dict) -> float:
    #     key = f"{axis}_dist"
    #     for seq, (grid_x, grid_y, info) in layout.items():
    #         if (axis == "row" and grid_x == coord) or (axis == "col" and grid_y == coord):
    #             print(coord, seq, info, self.subunit_dimensions[seq])
    #             # if '+' in str(info[key]):
    #             #     # This position has a dependent distance, calculate it based on the child unit's dimensions
    #             #     base_dist = float(str(info[key]).rstrip('+'))
    #             #     child_length = self.subunit_dimensions[seq][0]
    #             #     child_depth = self.subunit_dimensions[seq][1]
    #             #     if axis == "row":
    #             #         return base_dist + float(str(child_depth).rstrip('+')) # Silly conversions, but works, revisit for speed later.
    #             #     else:
    #             #         return base_dist + float(str(child_length).rstrip('+'))
    #             return float(str(info[key]).rstrip('+'))
    #     default = self.archetype.row_dist if axis == "row" else self.archetype.col_dist
    #     return float(str(default).rstrip('+'))

    # def _walk_spacing(self, index: int, axis: str, layout: dict) -> float:
    #     if index == 0:
    #         return 0.0
    #     step = 1 if index > 0 else -1
    #     total = 0.0
    #     for coord in range(0, index, step):
    #         total += step * self._get_spacing_for_coord(coord, axis, layout)
    #     return total

    # def dependent_dimension(self, parent_padding: tuple[str,str], child_dimensions: tuple[float, float]) -> tuple[float, float]:
    #     """Calculates the actual dimension based on the padding from parent, which may have a '+' indicating dependence on child size."""
    #     row_dist_str, col_dist_str = parent_padding
    #     child_length, child_depth = child_dimensions
    #     if row_dist_str.endswith('+'):
    #         base_dist = float(row_dist_str[:-1])
    #         actual_row_dist = base_dist + child_depth
    #     else:
    #         actual_row_dist = float(row_dist_str)

    #     if col_dist_str.endswith('+'):
    #         base_dist = float(col_dist_str[:-1])
    #         actual_col_dist = base_dist + child_length
    #     else:
    #         actual_col_dist = float(col_dist_str)

    #     return (actual_row_dist, actual_col_dist)

    def get_dimensions(self) -> tuple:
        """
        Get the actual dimensions (length, depth) of this formation at a given strength.
        
        For fighting formations: strength is an integer, returns bounding box of first N positions.
        For command formations: strength is an integer (number of sub-units), returns bounding box accordingly.
        
        Args:
            strength (int): The strength/number of positions to include
            
        Returns:
            tuple: (length_yards, depth_yards) - the actual dimensions at this strength
        """
        layout = self.get_positions()
        
        if not layout:
            print("WARNING: No positions found for this formation at the given strength, returning default dimensions (10, 10).")
            return (10, 10)
        
        all_x = [pos[0] for pos in layout.values()]
        all_y = [pos[1] for pos in layout.values()]
        
        length = max(all_x) - min(all_x)# if all_x else 10
        depth = max(all_y) - min(all_y)# if all_y else 10
        self.length = length
        self.depth = depth
        
        return length, depth

# def get_actual_layout(unit: dict) -> dict:
#     """
#     Given a unit (regiment, brigade, division, etc.) with a formation and strength, 
#     return the layout of positions with their coordinates in yards relative to seq 1 (flag bearer).
    
#     For fighting formations (Lvl6): strength is an integer (number of units)
#     For command formations (Lvl5-2): strength is a list of sub-unit strengths OR list of sub-units dicts
    
#     Args:
#         unit (dict): {'formation': formation_id, 'strength': strength_value}
        
#     Returns:
#         dict: Positioned units with their coordinates in yards
#         - For Lvl6: {seq: (x_yards, y_yards)} 
#         - For Lvl5+: {seq: {'position': (x, y), 'unit': sub_unit_dict}} or similar structure
#     """
#     formation_id = unit['formation']
#     strength = unit['strength']
    
#     if formation_id not in formations:
#         raise ValueError(f"Formation ID {formation_id} not found.")
    
#     formation = formations[formation_id]
#     print(formation)
    
#     # Handle integer strength (fighting formation or simplified layout)
#     if isinstance(strength, int):
#         layout = {}
#         for seq, pos in formation.positions.items():
#             try:
#                 if int(seq) <= strength:
#                     layout[seq] = pos
#             except ValueError:
#                 # Non-numeric sequence, skip
#                 pass
#         return layout
    
#     # Handle list strength (command formation with multiple sub-units)
#     elif isinstance(strength, list):
#         layout = {}
        
#         # Check if items are dicts (nested units) or ints (strengths)
#         sub_unit_dicts = []
#         for idx, item in enumerate(strength):
#             seq = str(idx + 1)
            
#             if isinstance(item, dict):
#                 # It's a sub-unit dict like {'formation': 'DRIL_Lvl5_...', 'strength': [...]}
#                 sub_unit_dicts.append((seq, item))
#             else:
#                 # TODO: remove this case, this should not be used, pass in sub unit dicts for all command formations.
#                 print("SHOULD NOT BE USING INTEGER STRENGTHS IN A LIST.")
#                 # It's a strength value (int), create a basic sub-unit dict
#                 if seq in formation.positions:
#                     sub_unit_dicts.append((seq, {'strength': item}))
#         print(sub_unit_dicts)
#         # Calculate positions with actual sub-unit dimensions
#         layout = _calculate_positioned_subunits(formation, sub_unit_dicts)
#         return layout
    
#     else:
#         raise ValueError(f"Strength must be int or list, got {type(strength)}")



def populate_formation_archetypes_from_csv(file_path):
    """Parse formation definitions from a CSV file, reading blocks of lines.

    A block starts when column 2 (spec) starts with 'DRIL_'.
    A block ends when a line has 'x' in column 1 or 2, or has no data in any column.
    Each block is passed to FightingFormation to create a formation.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Skip the CSV header row
    data_lines = lines[1:]

    lvl6_blocks = []
    lvl5_blocks = []
    lvl4_blocks = []
    lvl3_blocks = []
    lvl2_blocks = []
    misc_blocks = []  # Likely supply wagons, or anything else not in an echelon.

    i = 0
    while i < len(data_lines):
        line = data_lines[i].strip()

        # Skip blank lines
        if not line:
            i += 1
            continue

        parts = line.split(',')

        # Check if this line starts a new formation block:
        # column 2 (index 1) starts with "DRIL_"
        drill_id = parts[1].strip() if len(parts) > 1 else ""
        if not drill_id.startswith("DRIL_"):
            i += 1
            continue

        # Found start of a block — collect lines until termination condition
        block_lines = []
        while i < len(data_lines):
            block_line = data_lines[i].strip()

            # End of block: no data in any column
            if not block_line:
                break

            block_parts = block_line.split(',')
            col1 = block_parts[0].strip() if block_parts else ""
            col2 = block_parts[1].strip() if len(block_parts) > 1 else ""

            # End of block: 'x' in column 1 or 2
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
    
    # makes sure all lower level formations are parsed before higher level ones that may depend on them.
    for block in lvl6_blocks:
        try:
            #formation = CommandFormation(block)
            formation = FormationArchetype(block)
        except Exception as e:
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    for block in lvl5_blocks:
        try:
            formation = FormationArchetype(block)
        except Exception as e:
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    for block in lvl4_blocks:
        try:
            formation = FormationArchetype(block)
        except Exception as e:
            traceback.print_exc()
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    # for block in lvl3_blocks:
    #     try:
    #         formation = FormationArchetype(block)
    #     except Exception as e:
    #         print(f"Skipping block due to parsing error: {e}")
    #         print(f"Block lines: {block}")
    # for block in lvl2_blocks:
    #     try:
    #         formation = FormationArchetype(block)
    #     except Exception as e:
    #         print(f"Skipping block due to parsing error: {e}")
    #         print(f"Block lines: {block}")
    #print(formations)