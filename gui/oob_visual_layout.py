from typing import Dict, Tuple, List, Optional
from core.oob_model import OOBData


class HierarchicalLayout:
    """Layout engine for positioning units in a hierarchical formation view."""

    HORIZONTAL_SPACING = 104
    HORIZONTAL_SPACING_INCREMENT = 20
    VERTICAL_SPACING = 75
    ROW_VERTICAL_SPACING = 25

    def __init__(self, data: OOBData):
        self.data = data
        self.positions: Dict[int, Tuple[float, float]] = {}
        self.subtree_sizes: Dict[int, Tuple[float, float]] = {}
        self.parent_to_children: Dict[int, List[int]] = {}
        self.row_keys: List[Tuple[int, ...]] = []
        self.row_sides: List[int] = []
        self.child_indices: set = set()

    def calculate_layout(self, root_row_index: Optional[int] = None) -> Dict[int, Tuple[float, float]]:
        self.positions = {}
        self.subtree_sizes = {}
        self._build_parent_child_index()

        all_indices = set(range(len(self.data.df)))
        root_units = sorted(all_indices - self.child_indices)

        side1_roots = []
        side2_roots = []
        for unit_idx in root_units:
            if self.row_sides[unit_idx] == 2:
                side2_roots.append(unit_idx)
            else:
                side1_roots.append(unit_idx)

        if side2_roots:
            subtree_widths = [self._compute_subtree_size(root)[0] for root in side2_roots]
            root_level = self.get_level_for_position(side2_roots[0]) if side2_roots else 1
            root_spacing = self._get_horizontal_spacing_for_level(root_level)
            total_width = sum(subtree_widths) + root_spacing * (len(side2_roots) - 1)
            start_x = -total_width / 2
            y_pos = 0 - self.VERTICAL_SPACING
            current_x = start_x
            for unit_idx, width in zip(side2_roots, subtree_widths):
                x_pos = current_x + width / 2
                self._layout_unit_recursive(unit_idx, x_pos, y_pos, direction=-1)
                current_x += width + root_spacing

        if side1_roots:
            subtree_widths = [self._compute_subtree_size(root)[0] for root in side1_roots]
            root_level = self.get_level_for_position(side1_roots[0]) if side1_roots else 1
            root_spacing = self._get_horizontal_spacing_for_level(root_level)
            total_width = sum(subtree_widths) + root_spacing * (len(side1_roots) - 1)
            start_x = -total_width / 2
            y_pos = 0 + self.VERTICAL_SPACING
            current_x = start_x
            for unit_idx, width in zip(side1_roots, subtree_widths):
                x_pos = current_x + width / 2
                self._layout_unit_recursive(unit_idx, x_pos, y_pos, direction=1)
                current_x += width + root_spacing

        return self.positions

    def _build_parent_child_index(self):
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
        if row_index in self.subtree_sizes:
            return self.subtree_sizes[row_index]

        children = self.parent_to_children.get(row_index, [])
        if not children:
            size = (self.HORIZONTAL_SPACING, self.HORIZONTAL_SPACING)
            self.subtree_sizes[row_index] = size
            return size

        parent_level = self.get_level_for_position(row_index)
        child_level = parent_level + 1
        child_spacing = self._get_horizontal_spacing_for_level(child_level)

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
            top_width += child_spacing * (len(top_children) - 1)

        bottom_width = sum(width for width, _ in bottom_sizes)
        if len(bottom_children) > 1:
            bottom_width += child_spacing * (len(bottom_children) - 1)

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
        self.positions[row_index] = (x, y)

        children = self.parent_to_children.get(row_index, [])
        if not children:
            self.subtree_sizes[row_index] = (self.HORIZONTAL_SPACING, self.HORIZONTAL_SPACING)
            return

        parent_level = self.get_level_for_position(row_index)
        child_level = parent_level + 1
        child_spacing = self._get_horizontal_spacing_for_level(child_level)

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
            top_width += child_spacing * (len(top_children) - 1)

        bottom_width = sum(self.subtree_sizes[child][0] for child in bottom_children)
        if len(bottom_children) > 1:
            bottom_width += child_spacing * (len(bottom_children) - 1)

        top_row_start_x = x - top_width / 2
        child_y_offset = y + self.VERTICAL_SPACING * direction

        current_x = top_row_start_x
        for child_row_idx in top_children:
            child_width = self.subtree_sizes[child_row_idx][0]
            child_x = current_x + child_width / 2
            self._layout_unit_recursive(child_row_idx, child_x, child_y_offset, direction=direction)
            current_x += child_width + child_spacing

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
                current_x += child_width + child_spacing
            bottom_height = max(self.subtree_sizes[child][1] for child in bottom_children)

        top_height = max(self.subtree_sizes[child][1] for child in top_children) if top_children else 0.0
        subtree_height = self.VERTICAL_SPACING + top_height
        if bottom_children:
            subtree_height += self.ROW_VERTICAL_SPACING + bottom_height

        self.subtree_sizes[row_index] = (max(top_width, bottom_width, self.HORIZONTAL_SPACING), subtree_height)

    def get_level_for_position(self, row_index: int) -> int:
        row = self.data.get_row(row_index)
        return self.data.get_level_from_hierarchy(row)

    def _get_horizontal_spacing_for_level(self, level: int) -> float:
        if level >= 6:
            return self.HORIZONTAL_SPACING
        spacing_multiplier = 6 - level
        return self.HORIZONTAL_SPACING + (spacing_multiplier * self.HORIZONTAL_SPACING_INCREMENT)
