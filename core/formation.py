from typing import List, Self
import traceback
import re


def detect_unit_type(class_value: str) -> str:
    """Detect unit type from the CLASS column in the OOB.

    Returns a string code used for subtype matching:
      "1" = infantry, "2" = cavalry, "3" = artillery, "0" = unknown.
    """
    class_upper = class_value.upper()
    if "_INF_" in class_upper:
        return "1"
    if "_CAV_" in class_upper:
        return "2"
    if "_ART_" in class_upper:
        return "3"
    return "0"


class FormationArchetype:
    """A parsed formation template from drills.csv.

    Shared across all units that use the same formation. Holds the layout
    grid, spacing defaults, and per-cell overrides parsed from the CSV.
    """
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

        # Pre-compute spacing constants from the raw strings.
        # These never change after parsing, so compute once here
        # instead of re-parsing on every get_positions() call.
        self.base_row_distance = float(self.row_dist.rstrip('+'))
        self.base_column_distance = float(self.col_dist.rstrip('+'))
        self.row_distance_depends_on_size = self.row_dist.rstrip(',').endswith('+')
        self.column_distance_depends_on_size = self.col_dist.rstrip(',').endswith('+')
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

        # Parse the layout grid into a dictionary keyed by sequence number.
        # Each entry stores the raw (grid_row, grid_col) and parsed cell info.
        layout_2d = [x.split(',') for x in self.layout]
        self.full_strength_layout = {}
        for grid_row, line in enumerate(layout_2d):
            for grid_col, location in enumerate(line):
                cell_info = self.parse_layout_entry(location)
                if cell_info.get("seq"):
                    self.full_strength_layout[cell_info['seq']] = (grid_row, grid_col, cell_info)

        FormationArchetype.formations[self.drill_id] = self

    def parse_layout_entry(self, entry: str) -> dict:
        """Parse a single layout cell from the CSV.

        A cell can be:
          - Empty (spacing only)
          - A bare seq number: "5"
          - A parenthesized override with seq: "(500-0-0-0-DRIL_Lvl4_Inf_Reserves-1)6"

        The override format is: row_dist-col_dist-sprite-facing-subformation-subtype-lock
        """
        entry = entry.strip()
        if not entry:
            return {}

        # Split the override prefix from the sequence number
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
            'row_dist':      self._combine_row_or_col_distance(parts[0].strip() if len(parts) > 0 else "0", self.row_dist),
            'col_dist':      self._combine_row_or_col_distance(parts[1].strip() if len(parts) > 1 else "0", self.col_dist),
            'sprite':        parts[2].strip() if len(parts) > 2 else 0,
            'facing':        parts[3].strip() if len(parts) > 3 else 0,
            'subformation':  parts[4].strip() if len(parts) > 4 else self.sub_form,
            'subtype':       parts[5].strip() if len(parts) > 5 else None,
            'lock':          parts[6].strip() if len(parts) > 6 else None,
            'seq':           seq_str,
        }

    def _combine_row_or_col_distance(self, cell_distance: str, parent_distance: str) -> str:
        """Combine a cell-level distance with the formation's parent distance.

        If either has a '+' suffix, the result keeps it (meaning the distance
        depends on unit size). The numeric values are summed.
        """
        plus = "+" if cell_distance.endswith('+') or parent_distance.endswith('+') else ""
        combined_value = float(cell_distance.rstrip('+')) + float(parent_distance.rstrip('+'))
        return f"{combined_value}{plus}"

    def __str__(self):
        return f"Formation: {self.name}, ID: {self.drill_id}"


class ActualFormation:
    """A concrete formation placement for one unit.

    Contains the child sub-formations and computes final x,y positions
    for every sequence slot in the formation layout.
    """
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

    # ── Layout filtering ────────────────────────────────────────────

    def get_layout(self) -> dict:
        """Return the filtered layout containing only occupied slots.

        Seq 1 and 2 are always included. Seq 3+ is included only if the
        corresponding child is non-None (or if strength is a plain count).
        """
        layout: dict[str, tuple] = {}
        for seq, location in self.full_strength_layout.items():
            if isinstance(self.strength, list):
                idx = int(seq) - 1
                if 0 <= idx < len(self.strength):
                    # Seq 1 and 2 are always present; seq 3+ requires a child
                    if int(seq) <= 2 or self.strength[idx] is not None:
                        layout[seq] = location
            elif isinstance(self.strength, int):
                if int(seq) <= self.strength:
                    layout[seq] = location
        return layout

    # ── Position computation ─────────────────────────────────────────

    def get_positions(self) -> dict:
        """Compute x, y positions for every slot in the formation.

        Returns a dict of {seq_str: (x, y, length, depth)} where x,y is the
        top-left corner of the unit's bounding box.

        The algorithm works in passes:
          1. Rebase all coordinates so seq 1 (commander) is at origin (0, 0)
          2. Compute per-slot subunit dimensions (length, depth)
          3. Build per-cell override and depth lookup tables
          4. Compute forward row offsets (gx > 0, behind commander)
          5. Compute backward row offsets (gx < 0, ahead of commander)
          6. Compute lateral column offsets (gy direction)
          7. Assemble final positions from row + column offsets
          8. Shift everything so the standard bearer (seq 2) sits at y=0
        """
        layout = self.get_layout()

        # Seq 1 defines the origin — if it's missing, we can't place anything
        origin_data = layout.get('1')
        if origin_data is None:
            return {}
        origin_row, origin_col, _loc_info = origin_data

        rebased_layout = self._rebase_layout_to_origin(layout, origin_row, origin_col)
        sorted_sequence_numbers = self._sorted_sequence_numbers(rebased_layout)

        # Compute subunit dimensions for every slot
        self._compute_subunit_dimensions(sorted_sequence_numbers)

        # Use pre-computed spacing constants from the archetype
        base_row_distance = self.archetype.base_row_distance
        base_column_distance = self.archetype.base_column_distance
        row_distance_depends_on_size = self.archetype.row_distance_depends_on_size
        column_distance_depends_on_size = self.archetype.column_distance_depends_on_size

        # Build lookup tables from the layout and full_strength_layout
        column_max_length, column_row_depth = self._compute_column_metrics(sorted_sequence_numbers, rebased_layout)
        per_cell_overrides = self._compute_per_cell_overrides(base_row_distance, origin_row, origin_col)

        # Compute the grid ranges (rebased to origin)
        all_grid_x = list(range(0 - origin_row, self.archetype.rows - origin_row))
        all_grid_y = list(range(0 - origin_col, self.archetype.columns - origin_col))

        # Build propagated gap values (handles row-level override inheritance)
        propagated_gaps = self._compute_propagated_gaps(per_cell_overrides, base_row_distance, all_grid_x, all_grid_y)

        # Compute y-axis row offsets per column
        column_row_offsets = self._compute_column_row_offsets(
            per_cell_overrides, propagated_gaps, column_row_depth,
            base_row_distance, row_distance_depends_on_size,
            all_grid_x, all_grid_y)

        # Compute x-axis column offsets
        column_offsets = self._compute_column_offsets(column_max_length, base_column_distance, all_grid_y)

        # Assemble final (x, y, length, depth) positions
        positions = self._assemble_final_positions(
            sorted_sequence_numbers, rebased_layout, column_offsets, column_row_offsets)

        # Shift so the standard bearer sits at y=0 (the formation front line)
        self._apply_standard_bearer_shift(positions)

        return positions

    # ── Helper: rebase layout coordinates ────────────────────────────

    @staticmethod
    def _rebase_layout_to_origin(layout: dict, origin_row: int, origin_col: int) -> dict:
        """Shift all grid coordinates so seq 1 sits at (0, 0)."""
        rebased = {}
        for seq, (grid_row, grid_col, cell_info) in layout.items():
            rebased[seq] = (grid_row - origin_row, grid_col - origin_col, cell_info)
        return rebased

    @staticmethod
    def _sorted_sequence_numbers(rebased_layout: dict) -> list:
        """Return sequence numbers sorted numerically (seq 1 first)."""
        return sorted(rebased_layout.keys(),
                      key=lambda s: int(s) if s.isdigit() else float('inf'))

    # ── Helper: compute subunit dimensions ───────────────────────────

    def _compute_subunit_dimensions(self, sorted_sequence_numbers: list) -> None:
        """Fill self.subunit_dimensions with (length, depth) for every slot.

        - Seq 1 and 2: fixed small size (commander/standard bearer)
        - Seq 3+: the child formation's own dimensions
        - Empty slots or level-6 units: (0, 0) since spacing is already handled
        """
        for seq in sorted_sequence_numbers:
            try:
                if seq in ['1', '2'] and isinstance(self.strength, list):
                    # Commander and standard bearer have fixed small dimensions
                    self.subunit_dimensions[seq] = 2.5, 1.8
                elif isinstance(self.strength, list) and int(seq) <= len(self.strength):
                    subunit = self.strength[int(seq) - 1]
                    if subunit is None:
                        # Empty slot — use default small size
                        self.subunit_dimensions[seq] = 2.5, 1.8
                    else:
                        self.subunit_dimensions[seq] = subunit.get_dimensions()
                else:
                    # Level-6 units or beyond the strength list — zero dimensions
                    # because spacing is already accounted for in the grid layout
                    self.subunit_dimensions[seq] = 0, 0
            except Exception:
                raise Exception(f"Error calculating dimensions for seq {seq}: {traceback.format_exc()}")

    # ── Helper: column metrics (max length and per-depth) ────────────

    def _compute_column_metrics(self, sorted_sequence_numbers: list, rebased_layout: dict) -> tuple:
        """Compute the maximum unit length per column and per-cell depths.

        Returns:
            column_max_length: dict mapping column index -> max unit length
            column_row_depth: dict mapping column index -> {row index -> depth}
        """
        column_max_length = {}
        column_row_depth = {}

        for seq in sorted_sequence_numbers:
            grid_x, grid_y, _cell_info = rebased_layout[seq]
            unit_length, unit_depth = self.subunit_dimensions[seq]

            # Track the longest unit in each column (for lateral spacing)
            if grid_y not in column_max_length:
                column_max_length[grid_y] = unit_length
            else:
                column_max_length[grid_y] = max(column_max_length[grid_y], unit_length)

            # Track the deepest unit at each (column, row) position
            if grid_y not in column_row_depth:
                column_row_depth[grid_y] = {}
            column_row_depth[grid_y][grid_x] = max(
                column_row_depth[grid_y].get(grid_x, 0), unit_depth)

        return column_max_length, column_row_depth

    # ── Helper: per-cell overrides ───────────────────────────────────

    def _compute_per_cell_overrides(self, base_row_distance: float,
                                    origin_row: int, origin_col: int) -> dict:
        """Extract per-cell row distance overrides from the full layout.

        Returns a dict mapping rebased (grid_x, grid_y) -> override value.
        Only non-zero overrides are stored. The override is the amount by
        which a cell's row_dist exceeds the formation's base row_dist.
        """
        per_cell_overrides = {}
        for _seq_str, (grid_x, grid_y, cell_info) in self.full_strength_layout.items():
            cell_row_distance = float(str(cell_info.get('row_dist', base_row_distance)).rstrip('+'))
            override = cell_row_distance - base_row_distance
            if override != 0:
                per_cell_overrides[(grid_x - origin_row, grid_y - origin_col)] = override
        return per_cell_overrides

    # ── Helper: propagated gap values ────────────────────────────────

    def _compute_propagated_gaps(self, per_cell_overrides: dict, base_row_distance: float,
                                 all_grid_x: list, all_grid_y: list) -> dict:
        """Compute the effective gap for each (grid_x, grid_y) position.

        For gx >= 0 (behind commander): the gap is the cell's override if
        non-zero, otherwise the base row distance. If one cell in a row has
        an override, other cells in the same row inherit it via row_override.

        For gx < 0 (ahead of commander): the gap is base_row_dist minus the
        cell's override (the override pulls the unit closer to the origin).
        """
        propagated_gaps = {}
        for grid_x in all_grid_x:
            # Find the first non-zero override in this row (for inheritance)
            row_override = 0
            for grid_y in all_grid_y:
                override = per_cell_overrides.get((grid_x, grid_y), 0)
                if override != 0:
                    row_override = override
                    break
            # Assign the gap value for each cell in this row
            for grid_y in all_grid_y:
                if (grid_x, grid_y) in per_cell_overrides:
                    override = per_cell_overrides[(grid_x, grid_y)]
                else:
                    override = row_override
                if grid_x < 0:
                    # Ahead of commander: override pulls unit toward origin
                    propagated_gaps[(grid_x, grid_y)] = base_row_distance - override
                else:
                    # Behind commander: override or default gap
                    propagated_gaps[(grid_x, grid_y)] = override if override != 0 else base_row_distance
        return propagated_gaps

    # ── Helper: column row offsets (y-axis) ──────────────────────────

    def _compute_column_row_offsets(self, per_cell_overrides: dict, propagated_gaps: dict,
                                    column_row_depth: dict, base_row_distance: float,
                                    row_distance_depends_on_size: bool,
                                    all_grid_x: list, all_grid_y: list) -> dict:
        """Compute y-axis offsets for each column and row position.

        Returns a dict mapping column_index -> {grid_x -> y_offset}.

        Special cases:
          - gx=0: offset is the override at that column's origin cell (if any)
          - gx > 0: forward accumulation from origin, with optional depth comp
          - gx < 0: computed directly from origin (not chained through intermediates)
        """
        column_row_offsets = {}
        for grid_y in all_grid_y:
            # The origin row (gx=0) starts at the override for this column.
            # This defines the gap from gx=-1 to gx=0.
            override_at_origin = per_cell_overrides.get((0, grid_y), 0)
            column_row_offsets[grid_y] = {0: override_at_origin}

            # Forward: accumulate offsets for rows behind the commander (gx > 0)
            for grid_x in [gx for gx in all_grid_x if gx > 0]:
                previous_grid_x = max((gx for gx in all_grid_x if gx < grid_x), default=0)
                gap = propagated_gaps.get((grid_x, grid_y), base_row_distance)

                # When row distance depends on unit size and there's no override,
                # add edge-to-edge depth compensation to prevent overlapping.
                # Overrides define top-to-top distances and replace the default gap.
                if row_distance_depends_on_size and (grid_x, grid_y) not in per_cell_overrides:
                    previous_depth = column_row_depth.get(grid_y, {}).get(previous_grid_x, 0)
                    current_depth = column_row_depth.get(grid_y, {}).get(grid_x, 0)
                    gap += (previous_depth + current_depth) / 2

                # Move the unit gap units behind the previous row
                column_row_offsets[grid_y][grid_x] = column_row_offsets[grid_y][previous_grid_x] + gap

            # Backward: compute offsets for rows ahead of the commander (gx < 0).
            # Each position is computed directly from origin (gx=0) to avoid
            # chaining errors through intermediate rows. The override at the
            # current cell reduces the gap, pulling the unit closer to origin.
            for grid_x in reversed([gx for gx in all_grid_x if gx < 0]):
                current_override = per_cell_overrides.get((grid_x, grid_y), 0)
                gap = base_row_distance - current_override
                # Distance grows linearly with abs(gx) from origin
                column_row_offsets[grid_y][grid_x] = -gap * abs(grid_x)

        return column_row_offsets

    # ── Helper: column offsets (x-axis) ──────────────────────────────

    def _compute_column_offsets(self, column_max_length: dict, base_column_distance: float,
                                all_grid_y: list) -> dict:
        """Compute x-axis lateral offsets for each column.

        Uses edge-to-edge spacing: the gap between two columns is
        (max_length_of_left + max_length_of_right) / 2 + column_distance.

        Special case: gy=0 is always at offset 0 (the center column).
        """
        column_offsets = {0: 0}
        # Forward: columns to the right (positive gy)
        for grid_y in [gy for gy in all_grid_y if gy > 0]:
            previous_grid_y = max((gy for gy in all_grid_y if gy < grid_y), default=0)
            left_length = column_max_length.get(previous_grid_y, 0)
            right_length = column_max_length.get(grid_y, 0)
            # Center-to-center = half the left unit + gap + half the right unit
            column_offsets[grid_y] = (column_offsets[previous_grid_y]
                                      + (left_length + right_length) / 2
                                      + base_column_distance)
        # Backward: columns to the left (negative gy)
        for grid_y in reversed([gy for gy in all_grid_y if gy < 0]):
            next_grid_y = min((gy for gy in all_grid_y if gy > grid_y), default=0)
            left_length = column_max_length.get(grid_y, 0)
            right_length = column_max_length.get(next_grid_y, 0)
            column_offsets[grid_y] = (column_offsets[next_grid_y]
                                      - (left_length + right_length) / 2
                                      - base_column_distance)
        return column_offsets

    # ── Helper: assemble final positions ─────────────────────────────

    def _assemble_final_positions(self, sorted_sequence_numbers: list,
                                  rebased_layout: dict, column_offsets: dict,
                                  column_row_offsets: dict) -> dict:
        """Build the final {seq: (x, y, length, depth)} dict from offsets.

        Each unit's x position is its column offset minus half its length
        (so the unit is centered on the column axis).
        """
        positions = {}
        for seq in sorted_sequence_numbers:
            grid_x, grid_y, _cell_info = rebased_layout[seq]
            unit_length, unit_depth = self.subunit_dimensions[seq]

            if seq == '1':
                # Commander is always centered at the origin
                positions[seq] = (-unit_length / 2, 0, unit_length, unit_depth)
            else:
                x_offset = column_offsets.get(grid_y, 0)
                y_offset = column_row_offsets.get(grid_y, {}).get(grid_x, 0)
                # Center the unit on the column axis
                positions[seq] = (x_offset - unit_length / 2, y_offset, unit_length, unit_depth)

        return positions

    # ── Helper: standard bearer shift ────────────────────────────────

    @staticmethod
    def _apply_standard_bearer_shift(positions: dict) -> None:
        """Shift all positions so the standard bearer (seq 2) sits at y=0.

        The standard bearer defines the formation's front line. This shift
        ensures that regardless of column overrides, the front rank is
        always at the origin y-coordinate.
        """
        if '2' in positions and '1' in positions:
            shift_amount = -positions['2'][1]
            if shift_amount != 0:
                for seq in positions:
                    x_pos, y_pos, length, depth = positions[seq]
                    positions[seq] = (x_pos, y_pos + shift_amount, length, depth)

    # ── Bounding box computation ─────────────────────────────────────

    def get_dimensions(self) -> tuple:
        """Compute the overall bounding box (length, depth) and origin offset.

        Sets self.length, self.depth, self.origin_offset_x, self.origin_offset_y.
        """
        layout = self.get_positions()
        if not layout:
            return (10, 10)

        all_left_edges = [x for x, y, l, d in layout.values()]
        all_right_edges = [x + l for x, y, l, d in layout.values()]
        all_top_edges = [y for x, y, l, d in layout.values()]
        all_bottom_edges = [y + d for x, y, l, d in layout.values()]

        length = max(all_right_edges) - min(all_left_edges)
        depth = max(all_bottom_edges) - min(all_top_edges)
        self.length = length
        self.depth = depth

        # Origin is seq 2 (standard bearer) if present, else seq 1 (commander)
        origin = layout.get('2') or layout.get('1')
        if origin:
            origin_x, origin_y = origin[0], origin[1]
            self.origin_offset_x = origin_x - min(all_left_edges)
            self.origin_offset_y = origin_y - min(all_top_edges)
        else:
            self.origin_offset_x = length / 2
            self.origin_offset_y = depth / 2

        return length, depth


def populate_formation_archetypes_from_csv(file_path):
    """Parse formation definitions from drills.csv.

    The CSV has a header line, then blocks of lines per formation. Each block:
      - Line 1: Definition row (name, ID, rows, cols, row_dist, col_dist, ...)
      - Lines 2+: Layout grid cells (one row of the formation grid per line)

    Blocks are sorted by level for deterministic parsing order.
    """
    FormationArchetype.formations.clear()
    with open(file_path, 'r', encoding='cp1252') as f:
        lines = f.readlines()

    data_lines = lines[1:]

    # Bucket blocks by formation level for deterministic parse order
    level_buckets = {
        "DRIL_Lvl6": [],
        "DRIL_Lvl5": [],
        "DRIL_Lvl4": [],
        "DRIL_Lvl3": [],
        "DRIL_Lvl2": [],
    }
    misc_blocks = []

    valid_cell_pattern = re.compile(r"^(\d+|\(.+\)\d+)$")

    line_index = 0
    while line_index < len(data_lines):
        line = data_lines[line_index].strip()
        if not line:
            line_index += 1
            continue

        parts = line.split(',')
        drill_id = parts[1].strip() if len(parts) > 1 else ""
        if not drill_id.startswith("DRIL_"):
            line_index += 1
            continue

        # Collect all lines belonging to this formation block
        block_lines = [data_lines[line_index].strip()]
        line_index += 1
        while line_index < len(data_lines):
            block_line = data_lines[line_index].strip()
            if not block_line:
                break
            block_parts = block_line.split(',')
            first_col = block_parts[0].strip() if block_parts else ""
            second_col = block_parts[1].strip() if len(block_parts) > 1 else ""
            # Stop if we hit a marker row or a new formation definition
            if first_col.lower() == 'x' or second_col.lower() == 'x' or second_col.startswith("DRIL_"):
                break
            # Only accept valid cell patterns (bare numbers or parenthesized overrides)
            if not all(valid_cell_pattern.match(cell.strip()) or not cell.strip()
                       for cell in block_parts):
                line_index += 1
                continue
            block_lines.append(block_line)
            line_index += 1

        # Sort the block into the appropriate level bucket
        drill_id_from_block = block_lines[0].split(',')[1].strip()
        matched_bucket = False
        for level_prefix, bucket in level_buckets.items():
            if level_prefix in drill_id_from_block:
                bucket.append(block_lines)
                matched_bucket = True
                break
        if not matched_bucket:
            misc_blocks.append(block_lines)

    # Parse all blocks in level order (highest level first)
    all_blocks = (level_buckets["DRIL_Lvl6"] + level_buckets["DRIL_Lvl5"]
                  + level_buckets["DRIL_Lvl4"] + level_buckets["DRIL_Lvl3"]
                  + level_buckets["DRIL_Lvl2"] + misc_blocks)
    for block in all_blocks:
        try:
            FormationArchetype(block)
        except Exception as exception:
            traceback.print_exc()
            print(f"Skipping block due to parsing error: {exception}")
            print(f"Block lines: {block}")
