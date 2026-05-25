from typing import Dict, Tuple, List, Optional
from oob_model import OOBData


class HierarchicalLayout:
    """
    Layout engine for positioning units in a hierarchical formation view.
    
    Arranges child units in 2-row grids beneath their parents, creating a
    tree-like formation visualization.
    """
    
    # Layout constants (in logical units)
    HORIZONTAL_SPACING = 50    # Space between sibling units
    VERTICAL_SPACING = 75     # Space between parent and children
    ROW_VERTICAL_SPACING = 35  # Space between the two rows
    
    def __init__(self, data: OOBData):
        """
        Initialize the layout engine.
        
        Args:
            data: OOBData instance containing the unit hierarchy
        """
        self.data = data
        self.positions: Dict[int, Tuple[float, float]] = {}  # row_index -> (x, y)
        self.subtree_sizes: Dict[int, Tuple[float, float]] = {}  # row_index -> (width, height)
        self.parent_to_children: Dict[int, List[int]] = {}  # parent row index -> child row indices
        self.row_keys: List[Tuple[int, ...]] = []  # cached hierarchy keys for each row
        self.row_sides: List[int] = []  # cached side value for each row
        self.child_indices: set = set()  # all rows that are known children

    def calculate_layout(self, root_row_index: Optional[int] = None) -> Dict[int, Tuple[float, float]]:
        """
        Calculate positions for all units starting from root or specified unit.
        
        Args:
            root_row_index: Starting unit row index. If None, starts from highest-level units.
                          If specified, shows entire OOB (always shows from top level).
        
        Returns:
            Dict mapping row_index to (x, y) position
        """
        self.positions = {}
        self.subtree_sizes = {}

        # Build parent-to-children index and cache hierarchy data.
        self._build_parent_child_index()

        # Root units are those that are not children of any other row.
        all_indices = set(range(len(self.data.df)))
        root_units = sorted(all_indices - self.child_indices)

        # Split roots by side so Side 2 is drawn from the top and Side 1 is drawn from below.
        side1_roots = []
        side2_roots = []
        for unit_idx in root_units:
            if self.row_sides[unit_idx] == 2:
                side2_roots.append(unit_idx)
            else:
                side1_roots.append(unit_idx)

        if side2_roots:
            subtree_widths = [self._compute_subtree_size(root)[0] for root in side2_roots]
            total_width = sum(subtree_widths) + self.HORIZONTAL_SPACING * (len(side2_roots) - 1)
            start_x = -total_width / 2
            y_pos = 0 - self.VERTICAL_SPACING
            current_x = start_x
            for unit_idx, width in zip(side2_roots, subtree_widths):
                x_pos = current_x + width / 2
                self._layout_unit_recursive(unit_idx, x_pos, y_pos, direction=-1)
                current_x += width + self.HORIZONTAL_SPACING

        if side1_roots:
            subtree_widths = [self._compute_subtree_size(root)[0] for root in side1_roots]
            total_width = sum(subtree_widths) + self.HORIZONTAL_SPACING * (len(side1_roots) - 1)
            start_x = -total_width / 2
            y_pos = 0 + self.VERTICAL_SPACING
            current_x = start_x
            for unit_idx, width in zip(side1_roots, subtree_widths):
                x_pos = current_x + width / 2
                self._layout_unit_recursive(unit_idx, x_pos, y_pos, direction=1)
                current_x += width + self.HORIZONTAL_SPACING

        return self.positions
    
    def _build_parent_child_index(self):
        """Pre-build a mapping of parent units to their children for efficiency."""
        row_count = len(self.data.df)
        self.parent_to_children = {i: [] for i in range(row_count)}
        self.row_keys = []
        self.row_sides = []
        self.child_indices = set()

        key_to_index: Dict[Tuple[int, ...], int] = {}
        for idx in range(row_count):
            row = self.data.get_row(idx)
            hierarchy_key = self.data.get_hierarchy_key(row, idx)
            key_to_index[hierarchy_key] = idx
            self.row_keys.append(hierarchy_key)

            side_value = row.get("SIDE 1", 1)
            try:
                self.row_sides.append(int(side_value))
            except (TypeError, ValueError):
                self.row_sides.append(1)

        for idx, hierarchy_key in enumerate(self.row_keys):
            parent_key = self.data.get_parent_key(hierarchy_key)
            parent_idx = key_to_index.get(parent_key)
            if parent_idx is not None and parent_idx != idx:
                self.parent_to_children[parent_idx].append(idx)
                self.child_indices.add(idx)

    def _compute_subtree_size(self, row_index: int) -> Tuple[float, float]:
        """Compute the logical size of a unit's subtree."""
        if row_index in self.subtree_sizes:
            return self.subtree_sizes[row_index]

        children = self.parent_to_children.get(row_index, [])
        if not children:
            size = (self.HORIZONTAL_SPACING, self.HORIZONTAL_SPACING)
            self.subtree_sizes[row_index] = size
            return size

        num_children = len(children)
        if num_children <= 3:
            top_children = children
            bottom_children = []
        else:
            split = (num_children + 1) // 2
            top_children = children[:split]
            bottom_children = children[split:]

        top_sizes = [self._compute_subtree_size(child) for child in top_children]
        bottom_sizes = [self._compute_subtree_size(child) for child in bottom_children]

        top_width = sum(width for width, _ in top_sizes)
        if len(top_children) > 1:
            top_width += self.HORIZONTAL_SPACING * (len(top_children) - 1)

        bottom_width = sum(width for width, _ in bottom_sizes)
        if len(bottom_children) > 1:
            bottom_width += self.HORIZONTAL_SPACING * (len(bottom_children) - 1)

        width = max(top_width, bottom_width, self.HORIZONTAL_SPACING)

        top_height = max((height for _, height in top_sizes), default=0.0)
        bottom_height = max((height for _, height in bottom_sizes), default=0.0)

        height = self.VERTICAL_SPACING + top_height
        if bottom_children:
            height += self.ROW_VERTICAL_SPACING + bottom_height

        size = (width, height)
        self.subtree_sizes[row_index] = size
        return size

    def _layout_unit_recursive(self, row_index: int, x: float, y: float, direction: int = 1):
        """
        Recursively layout a unit and its children.
        
        Args:
            row_index: Index of the unit to layout
            x: X position for this unit
            y: Y position for this unit
            direction: +1 for downward growth, -1 for upward growth
        """
        # Store position for this unit
        self.positions[row_index] = (x, y)
        
        # Get children of this unit from pre-built index
        children = self.parent_to_children.get(row_index, [])
        
        if not children:
            # No children - this unit is a leaf
            self.subtree_sizes[row_index] = (self.HORIZONTAL_SPACING, self.HORIZONTAL_SPACING)
            return
        
        # Arrange children horizontally first. Use a second row only when there are more than 3 children.
        num_children = len(children)
        if num_children <= 3:
            top_children = children
            bottom_children = []
        else:
            split = (num_children + 1) // 2
            top_children = children[:split]
            bottom_children = children[split:]
        
        top_width = sum(self.subtree_sizes[child][0] for child in top_children)
        if len(top_children) > 1:
            top_width += self.HORIZONTAL_SPACING * (len(top_children) - 1)
        
        bottom_width = sum(self.subtree_sizes[child][0] for child in bottom_children)
        if len(bottom_children) > 1:
            bottom_width += self.HORIZONTAL_SPACING * (len(bottom_children) - 1)
        
        top_row_start_x = x - top_width / 2
        child_y_offset = y + self.VERTICAL_SPACING * direction

        current_x = top_row_start_x
        for child_row_idx in top_children:
            child_width = self.subtree_sizes[child_row_idx][0]
            child_x = current_x + child_width / 2
            self._layout_unit_recursive(child_row_idx, child_x, child_y_offset, direction=direction)
            current_x += child_width + self.HORIZONTAL_SPACING
        
        bottom_height = 0.0
        if bottom_children:
            bottom_row_start_x = x - bottom_width / 2
            top_row_height = max(self.subtree_sizes[child][1] for child in top_children) if top_children else 0.0
            bottom_y_offset = child_y_offset + (top_row_height + self.ROW_VERTICAL_SPACING) * direction
            current_x = bottom_row_start_x
            
            for child_row_idx in bottom_children:
                child_width = self.subtree_sizes[child_row_idx][0]
                child_x = current_x + child_width / 2
                self._layout_unit_recursive(child_row_idx, child_x, bottom_y_offset, direction=direction)
                current_x += child_width + self.HORIZONTAL_SPACING
            bottom_height = max(self.subtree_sizes[child][1] for child in bottom_children)

        top_height = max(self.subtree_sizes[child][1] for child in top_children) if top_children else 0.0
        subtree_height = self.VERTICAL_SPACING + top_height
        if bottom_children:
            subtree_height += self.ROW_VERTICAL_SPACING + bottom_height

        self.subtree_sizes[row_index] = (max(top_width, bottom_width, self.HORIZONTAL_SPACING), subtree_height)

    def get_level_for_position(self, row_index: int) -> int:
        """Get the hierarchy level of a unit."""
        row = self.data.get_row(row_index)
        return self.data.get_level_from_hierarchy(row)
