from typing import List
import traceback

formations = {}

class Formation:
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
        self.move_rate_mod = self.definition[10]
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

    def parse_position_entry(self, entry: str) -> dict:
        """Parses a single position within a layout."""
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
            'row_dist':       parts[0].strip() if len(parts) > 0 else "0", # Place a '+' after row or column distance to have the distance dependent on reg size, the distance that you add will be between reg's
            'col_dist':       parts[1].strip() if len(parts) > 1 else "0", # Place a '+' after row or column distance to have the distance dependent on reg size, the distance that you add will be between reg's
            'sprite':    parts[2].strip() if len(parts) > 2 else None, #  indexes into the unitglobal.csv file as to what specific sprite to use, leave 0 for default, valid values are currently 1-6
            'facing':    parts[3].strip() if len(parts) > 3 else None, # integer specifying the number of degrees that the unit should face off of the flag bearer
            'subformation': parts[4].strip() if len(parts) > 4 else None, # id of the sub formation to use for this slot, if it's not set, it uses the default for the formation
            'subtype': parts[5].strip() if len(parts) > 5 else None, # 1-Inf,2-Cav,3-Art, leave blank or zero for any
            'lock':      parts[6].strip() if len(parts) > 6 else None, # lock the position to be the exact place, they will never trail behind
            'seq':       seq_str # 1 - flagbearer, 2-300 men"
        }

    def dependent_distance(self, dist_str: str, subformation: str) -> float:
        """Calculates the actual distance based on the distance string, which may have a '+' indicating dependence on subformation size."""
        if dist_str.endswith('+'):
            base_dist = float(dist_str[:-1])
            if self.sub_form and self.sub_form in formations:
                sub_formation = formations[self.sub_form]
                return base_dist + max(sub_formation.length_yards, sub_formation.depth_yards)
            else:
                return base_dist
        else:
            return float(dist_str)
    
    def __str__(self):
        return f"Formation: {self.name}, ID: {self.drill_id}"

class FightingFormation(Formation):
    """Fighting formations are the lowest echelon formations that directly engage in combat. Lvl6 Units: Regiments, Batteries, and Squadrons are all fighting formations.
        Relies only on the definition line, the layout is mostly irrelevant as we are not interested in sprite positions, just the bounding box."""
    def __init__(self, drill):
        super().__init__(drill)
        # Minimum of 10 yards to prevent single column formations having zero length.
        self.length_yards = max(10, self.columns * float(self.col_dist))
        self.depth_yards = max(10, self.rows * float(self.row_dist))
        formations[self.drill_id] = self

    def __str__(self):
        return (f"Fighting Formation: {self.name}, ID: {self.drill_id}, "
                f"Length: {self.length_yards} yards, Depth: {self.depth_yards} yards")

class CommandFormation(Formation):
    """Command formations are higher echelon formations that may command other formations. Lvl5 and above Units: Brigades, Divisions, and Corps are all command formations."""
    def __init__(self, drill):
        super().__init__(drill)
        layout_2d = [x.split(',') for x in self.layout]
        
        # Create a 2D array to hold the calculated width and height for each position in the layout
        size_2d = [[(0.0,0.0)]*len(layout_2d[0]) for _ in range(len(layout_2d))]
        
        total_width = 0.0
        total_height = 0.0
        for x, line in enumerate(layout_2d):
            for y, position in enumerate(line):
                calculated_width = 0
                calculated_height = 0
                pos_info = self.parse_position_entry(position)
                if pos_info.get("seq"):
                    calculated_width = self.dependent_distance(pos_info['col_dist'], pos_info['subformation']) + self.dependent_distance(self.col_dist, self.sub_form)
                    calculated_height = self.dependent_distance(pos_info['row_dist'], pos_info['subformation']) + self.dependent_distance(self.row_dist, self.sub_form)

                size_2d[x][y] = (calculated_width, calculated_height)

        for line in size_2d:
            row_width = sum([pos[0] for pos in line])
            row_height = max([pos[1] for pos in line])
            total_width = max(total_width, row_width)
            total_height += row_height
        
        # Add to list of all loaded formations.
        self.length_yards = max(10, total_width)
        self.depth_yards = max(10, total_height)
        formations[self.drill_id] = self
        print(f"ID: {self.drill_id}: Length = {self.length_yards} yards, Depth = {self.depth_yards} yards\n   Subformation Size: {formations[self.sub_form].length_yards if self.sub_form else 'N/A'} yards by {formations[self.sub_form].depth_yards if self.sub_form else 'N/A'} yards")




                




    def __str__(self):
        return (f"Command Formation: {self.name}, ID: {self.drill_id}")

def populate_formations_from_csv(file_path):
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
            formation = FightingFormation(block)
        except Exception as e:
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    for block in lvl5_blocks:
        try:
            formation = CommandFormation(block)
        except Exception as e:
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    for block in lvl4_blocks:
        try:
            formation = CommandFormation(block)
        except Exception as e:
            traceback.print_exc()
            print(f"Skipping block due to parsing error: {e}")
            print(f"Block lines: {block}")
    # for block in lvl3_blocks:
    #     try:
    #         formation = CommandFormation(block)
    #     except Exception as e:
    #         print(f"Skipping block due to parsing error: {e}")
    #         print(f"Block lines: {block}")
    # for block in lvl2_blocks:
    #     try:
    #         formation = CommandFormation(block)
    #     except Exception as e:
    #         print(f"Skipping block due to parsing error: {e}")
    #         print(f"Block lines: {block}")
    #print(formations)