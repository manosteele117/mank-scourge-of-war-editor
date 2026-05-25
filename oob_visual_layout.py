from typing import Dict, Tuple, List, Optional
from oob_model import OOBData
from oob_visual_shapes import get_shape_class_for_level


class HierarchicalLayout:
    """
    Layout engine for positioning units in a hierarchical formation view.
    
    Arranges child units in 2-row grids beneath their parents, creating a
    tree-like formation visualization.
    """
    
    # Layout constants (in logical units)
    HORIZONTAL_SPACING = 50    # Space between sibling units
    VERTICAL_SPACING = 50     # Space between parent and children
    ROW_VERTICAL_SPACING = 50  # Space between the two rows
    
    def __init__(self, data: OOBData):
        """
        Initialize the layout engine.
        
        Args:
            data: OOBData instance containing the unit hierarchy
        """
        self.data = data
        self.positions: Dict[int, Tuple[float, float]] = {}  # row_index -> (x, y)
        self.subtree_sizes: Dict[int, Tuple[float, float]] = {}  # row_index -> (width, height)
        self.parent_to_children: Dict[int, List[int]] = {}  # Pre-built index for efficiency
    
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
        
        # Build parent-to-children index for efficient lookup
        self._build_parent_child_index()
        
        # Find the highest-level units (those with no parents)
        root_units = []
        for idx in range(len(self.data.df)):
            if idx not in [child for children in self.parent_to_children.values() for child in children]:
                # This unit is not a child of any other unit, so it's a root
                root_units.append(idx)
        
        # Split roots by side so Side 2 is drawn from the top and Side 1 is drawn from below.
        side1_roots = []
        side2_roots = []
        for unit_idx in root_units:
            row = self.data.get_row(unit_idx)
            side = int(row.get("SIDE 1", 1))
            if side == 2:
                side2_roots.append(unit_idx)
            else:
                side1_roots.append(unit_idx)

        if side2_roots:
            subtree_widths = [self._compute_subtree_size(root)[0] for root in side2_roots]
            total_width = sum(subtree_widths) + self.HORIZONTAL_SPACING * (len(side2_roots) - 1)
            start_x = -total_width / 2
            y_pos = 0
            current_x = start_x
            for unit_idx, width in zip(side2_roots, subtree_widths):
                x_pos = current_x + width / 2
                self._layout_unit_recursive(unit_idx, x_pos, y_pos, direction=1)
                current_x += width + self.HORIZONTAL_SPACING

        if side1_roots:
            subtree_widths = [self._compute_subtree_size(root)[0] for root in side1_roots]
            total_width = sum(subtree_widths) + self.HORIZONTAL_SPACING * (len(side1_roots) - 1)
            start_x = -total_width / 2
            max_side2_height = max((self.subtree_sizes[root][1] for root in side2_roots), default=0.0)
            max_side1_height = max((self.subtree_sizes[root][1] for root in side1_roots), default=0.0)
            y_pos = max_side2_height + self.VERTICAL_SPACING * 3 + max_side1_height
            current_x = start_x
            for unit_idx, width in zip(side1_roots, subtree_widths):
                x_pos = current_x + width / 2
                self._layout_unit_recursive(unit_idx, x_pos, y_pos, direction=-1)
                current_x += width + self.HORIZONTAL_SPACING

        return self.positions
    
    def _build_parent_child_index(self):
        """Pre-build a mapping of parent units to their children for efficiency."""
        self.parent_to_children = {i: [] for i in range(len(self.data.df))}
        
        for idx in range(len(self.data.df)):
            child_row = self.data.get_row(idx)
            child_key = self.data.get_hierarchy_key(child_row, idx)
            
            # Find the parent by zeroing out the last non-zero position
            parent_key = list(child_key)
            parent_found = False
            
            # Try zeroing positions from right to left to find parent
            for i in range(5, -1, -1):
                if parent_key[i] != 0:
                    parent_key[i] = 0
                    parent_found = True
                    break
            
            if not parent_found:
                continue  # Root unit, no parent
            
            parent_key = tuple(parent_key)
            
            # Find parent unit with matching key
            for parent_idx in range(len(self.data.df)):
                if parent_idx == idx:
                    continue
                parent_row = self.data.get_row(parent_idx)
                parent_row_key = self.data.get_hierarchy_key(parent_row, parent_idx)
                
                if parent_row_key == parent_key:
                    self.parent_to_children[parent_idx].append(idx)
                    break

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
