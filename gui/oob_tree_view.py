import json
import os
import random
from typing import Dict, List, Tuple
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox, QHeaderView, QAbstractItemView,
    QFileDialog, QApplication, QDialog,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QByteArray
from PySide6.QtGui import QBrush, QColor, QDrag, QFont, QDragEnterEvent, QDragMoveEvent, QDropEvent
from core.oob_model import OOBData
from gui.oob_generate_dialog import GenerateSubtreeDialog, GenerateSubtreeConfirmDialog
from constants import TREE_SIDE_1_BG, TREE_SIDE_2_BG, TREE_INDICATOR_PLACED, TREE_INDICATOR_UNPLACED
import pandas as pd
import traceback


class OOBTreeWidget(QTreeWidget):
    """
    Tree widget for displaying Order of Battle hierarchy.

    Signals:
        unit_deleted: Emitted when a unit is deleted; carries number of units deleted
        unit_selected: Emitted when a unit is selected; carries row index
        unit_double_clicked: Emitted when a unit is double-clicked; carries row index
    """

    unit_deleted = Signal(int, list)
    unit_selected = Signal(int)
    unit_double_clicked = Signal(int)
    unit_added = Signal()
    delete_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    zoom_to_unit_requested = Signal(int)
    filter_count_changed = Signal(int, int)  # visible_count, total_count
    unit_moved = Signal(list)  # list of source row indices that were moved

    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)

        self.data = data
        self._drag_start_pos = None
        self._drag_item = None
        self._selection_from_tree = False
        self._placed_row_indices: set = set()
        self._placement_filter: str = "all"
        self._total_unit_count: int = 0
        self._cut_row_indices: set = set()
        self._cut_top_level_rows: set = set()
        self._templates: list = []
        self._enabled_template_files: set = set()  # empty = all enabled
        self._templates_dir: str = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates", "units")
        self._drop_target_item = None
        self._drop_target_valid = False
        self._drop_target_original_bg = None

        self.setColumnCount(5)
        self.setHeaderLabels(["Unit", "Level", "Strength", "Experience", "Line"])

        self.itemSelectionChanged.connect(self.on_selection_changed)
        self.setStyleSheet("""QTreeView::item {
            border: 0;
            color: #ffffff;
            }
            QTreeView::item:hover {
            background: #252525;
            }
            QTreeView::item:selected {
            background: #2979ff;
            color: #ffffff;
            }

            QTreeView::branch:has-siblings:!adjoins-item {
                border-image: url(icons/vline.png) 0;
            }

            QTreeView::branch:has-siblings:adjoins-item {
                border-image: url(icons/branch-more.png) 0;
            }

            QTreeView::branch:!has-children:!has-siblings:adjoins-item {
                border-image: url(icons/branch-end.png) 0;
            }

            QTreeView::branch:has-children:!has-siblings:closed,
            QTreeView::branch:closed:has-children:has-siblings {
                    border-image: none;
                    image: url(icons/branch-closed.png);
            }

            QTreeView::branch:open:has-children:!has-siblings,
            QTreeView::branch:open:has-children:has-siblings  {
                    border-image: none;
                    image: url(icons/branch-open.png);
            }""")

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._selection_from_tree = False
        self._expanded_keys: set = set()
        self.itemExpanded.connect(self._on_item_expanded)
        self.itemCollapsed.connect(self._on_item_collapsed)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        row_index = item.data(0, Qt.UserRole)
        if row_index is not None:
            try:
                hk = self.data.get_hierarchy_key_by_index(row_index)
                self._expanded_keys.add(hk)
            except (IndexError, TypeError):
                pass

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        row_index = item.data(0, Qt.UserRole)
        if row_index is not None:
            try:
                hk = self.data.get_hierarchy_key_by_index(row_index)
                self._expanded_keys.discard(hk)
            except (IndexError, TypeError):
                pass

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        row_index = item.data(0, Qt.UserRole)
        if row_index is not None:
            self.zoom_to_unit_requested.emit(row_index)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.action_delete()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.action_zoom_to_unit()
        elif event.key() == Qt.Key.Key_X and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.action_cut()
        elif event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._cut_top_level_rows:
                self.action_paste()
        elif event.key() == Qt.Key.Key_Escape:
            self.action_cancel_cut()
        else:
            super().keyPressEvent(event)

    def populate(self) -> None:
        self.clear()
        self._expanded_keys.clear()
        if self.data.df is None:
            return

        self.data._ensure_built()
        df = self.data.df
        n_rows = len(df)

        # Precompute per-row scalars as plain Python lists (avoid per-node iloc).
        head_counts = [float(v) if v is not None and not pd.isna(v) else 0.0
                       for v in df["Head Count"].tolist()] if "Head Count" in df.columns else [0.0] * n_rows
        experiences = [float(v) if v is not None and not pd.isna(v) else 0.0
                       for v in df["Experience"].tolist()] if "Experience" in df.columns else [0.0] * n_rows
        formations = [str(v) if v is not None and not pd.isna(v) else ""
                       for v in df["Formation"].tolist()] if "Formation" in df.columns else [""] * n_rows
        line_nums = [str(int(v)) if v is not None and not pd.isna(v) and str(v).strip() != "" else ""
                     for v in df["line_number"].tolist()] if "line_number" in df.columns else [""] * n_rows
        is_supply = ["SupplyWagon" in f for f in formations]

        # Per-row subtree aggregates via post-order DFS over the adjacency index.
        subtree_strength: Dict[int, float] = {}
        subtree_experience: Dict[int, float] = {}

        def compute_aggregates(idx: int) -> None:
            own_strength = head_counts[idx]
            own_exp = experiences[idx] if not is_supply[idx] else None
            children = self.data._parent_to_children.get(idx, [])
            for child in children:
                compute_aggregates(child)
            total_strength = own_strength + sum(subtree_strength[c] for c in children)
            subtree_strength[idx] = total_strength
            if not children:
                # Leaf: own experience, or 0 fallback.
                subtree_experience[idx] = own_exp if own_exp is not None else experiences[idx]
            else:
                # Internal: average of non-supply children's subtree averages.
                # If every child is a supply wagon, fall back to own.
                child_exps = [subtree_experience[c] for c in children if not is_supply[c]]
                if child_exps:
                    subtree_experience[idx] = sum(child_exps) / len(child_exps)
                else:
                    subtree_experience[idx] = own_exp if own_exp is not None else experiences[idx]

        for top in range(n_rows):
            if self.data.get_level(top) is None:
                continue
            # Top-level = no parent in _parent_to_children
            if top not in self.data._children_set:
                compute_aggregates(top)

        # Build the items. Block all signals during the bulk insert.
        # Sort by hierarchy key so children appear in correct order after swaps.
        valid_indices = [idx for idx in range(n_rows)
                         if self.data.get_level(idx) is not None]
        sorted_indices = sorted(valid_indices,
                                key=lambda i: tuple(self.data._hierarchy_keys[i].tolist()))

        items_by_key: Dict[Tuple, QTreeWidgetItem] = {}
        top_level_items: List[QTreeWidgetItem] = []
        self.blockSignals(True)
        try:
            for idx in sorted_indices:
                try:
                    level = self.data.get_level(idx)
                    if level is None:
                        continue
                    hierarchy_key = self.data.get_hierarchy_key_by_index(idx)
                    info = self.data.unit_info(idx)
                    level_info = self.data.get_hierarchy_level_name_and_index(hierarchy_key)
                    subtree_s = subtree_strength[idx]
                    subtree_e = subtree_experience[idx]
                    strength_str = (str(int(subtree_s)) if subtree_s == int(subtree_s)
                                    else str(subtree_s))
                    initial_indicator = "\u25a3" if idx in self._placed_row_indices else "\u25a2"
                    item = QTreeWidgetItem([
                        f"{initial_indicator} {info.name}", level_info, strength_str,
                        f"{subtree_e:.2f}", str(line_nums[idx]),
                    ])
                    item.setData(0, Qt.UserRole, idx)
                    item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                    self.apply_side_colors(item, info.side)

                    parent_key = self.data.get_parent_key(hierarchy_key)
                    if parent_key in items_by_key:
                        items_by_key[parent_key].addChild(item)
                    else:
                        top_level_items.append(item)
                    items_by_key[hierarchy_key] = item
                except ValueError as e:
                    raise ValueError(f"Invalid data in CSV: {str(e)}\n{traceback.format_exc()}")

            # Bulk-insert top-level items; children are already attached above.
            if top_level_items:
                self.addTopLevelItems(top_level_items)
        finally:
            self.blockSignals(False)

        for col in range(self.columnCount()):
            self.resizeColumnToContents(col)
        self.setColumnWidth(1, self.columnWidth(1) + 24) # Hardcode expand the 'Level' column.

        self._expand_initial_levels()
        self._total_unit_count = len(self.data.df)
        self.refresh_indicators_and_visibility()
        if self._cut_row_indices:
            self._apply_cut_visual()

    def _expand_initial_levels(self) -> None:
        """Expand Side and Army level units in the tree.

        If a group has no side commander, level 1 is Army — in that case only
        level 1 is expanded (level 2 would be Corps, which should stay collapsed).
        """
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            self.expandItem(top)
            if top.data(0, Qt.UserRole) is not None:
                try:
                    level = self.data.get_level(top.data(0, Qt.UserRole))
                    if level == 1:
                        for j in range(top.childCount()):
                            self.expandItem(top.child(j))
                except (IndexError, TypeError):
                    pass

    def get_expanded_keys(self):
        """Return a set of hierarchy keys for all currently expanded items."""
        return set(self._expanded_keys)

    def restore_expanded_keys(self, keys):
        """Expand items whose hierarchy key is in *keys*."""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            self._restore_expanded(item, keys)

    def _restore_expanded(self, item, keys):
        row_index = item.data(0, Qt.UserRole)
        if row_index is not None:
            try:
                hk = self.data.get_hierarchy_key_by_index(row_index)
                if hk in keys:
                    self.expandItem(item)
            except (IndexError, TypeError):
                pass
        for i in range(item.childCount()):
            self._restore_expanded(item.child(i), keys)

    def populate_with_expansion(self):
        """Populate the tree while preserving the current expansion state."""
        expanded = self.get_expanded_keys()
        self.populate()
        self.restore_expanded_keys(expanded)

    # ── Placement indicator and filter ──────────────────────────────

    def _collect_all_items(self) -> List[QTreeWidgetItem]:
        result = []
        def _walk(item):
            result.append(item)
            for i in range(item.childCount()):
                _walk(item.child(i))
        for i in range(self.topLevelItemCount()):
            _walk(self.topLevelItem(i))
        return result

    def _set_indicator(self, item, indicator, color):
        full_text = item.text(0)
        if full_text and full_text[0] in ("\u25a3", "\u25a2", "\u25eb"):
            base_name = full_text[2:]
        else:
            base_name = full_text
        item.setText(0, f"{indicator} {base_name}")
        item.setData(0, Qt.UserRole + 2, indicator)
        item.setForeground(0, QBrush(color))

    def refresh_indicators_and_visibility(self):
        all_items = self._collect_all_items()
        matching = set()
        for item in all_items:
            row_index = item.data(0, Qt.UserRole)
            is_placed = row_index in self._placed_row_indices
            if self._placement_filter == "all":
                matches = True
            elif self._placement_filter == "placed":
                matches = is_placed
            else:
                matches = not is_placed
            if matches:
                matching.add(item)
        visible = set(matching)
        for item in matching:
            parent = item.parent()
            while parent is not None:
                visible.add(parent)
                parent = parent.parent()
        visible_count = 0
        for item in all_items:
            row_index = item.data(0, Qt.UserRole)
            is_placed = row_index in self._placed_row_indices
            item.setHidden(item not in visible)
            if item in visible:
                visible_count += 1
            if is_placed:
                indicator = "\u25a3"
                color = TREE_INDICATOR_PLACED
            elif item in matching:
                indicator = "\u25a2"
                color = TREE_INDICATOR_UNPLACED
            else:
                indicator = "\u25eb"
                color = TREE_INDICATOR_UNPLACED
            self._set_indicator(item, indicator, color)
        self.filter_count_changed.emit(visible_count, self._total_unit_count)

    def set_placed_row_indices(self, row_indices: set) -> None:
        self._placed_row_indices = set(row_indices)
        self.refresh_indicators_and_visibility()

    def set_placement_filter(self, mode: str) -> None:
        if mode not in ("all", "placed", "unplaced"):
            return
        self._placement_filter = mode
        self.refresh_indicators_and_visibility()

    def load_templates(self, enabled_files: set = None) -> None:
        """Load or reload all template units from the templates directory.

        Args:
            enabled_files: Set of file paths to include. If None or empty,
                           all templates are included.
        """
        all_templates = self.data.load_templates(self._templates_dir)
        if enabled_files:
            self._templates = [t for t in all_templates
                               if t["file"] in enabled_files]
        else:
            self._templates = all_templates

    def load_pools(self) -> None:
        """Load name pools from the pools directory."""
        pools_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates", "pools")
        self.data.load_pools(pools_dir)

    def drawRow(self, painter, option, index):
        item = self.itemFromIndex(index)
        if item is not None:
            side_color = item.data(0, Qt.UserRole + 1)
            if isinstance(side_color, QColor):
                painter.save()
                row_rect = option.rect
                row_rect.setWidth(self.viewport().width() - row_rect.left())
                painter.fillRect(row_rect, side_color)
                painter.restore()
        super().drawRow(painter, option, index)

    def apply_side_colors(self, item: QTreeWidgetItem, side: int) -> None:
        if side == 1:
            background = QColor(TREE_SIDE_1_BG)
            foreground = QColor("#ffffff")
        elif side == 2:
            background = QColor(TREE_SIDE_2_BG)
            foreground = QColor("#ffffff")
        else:
            return

        for col in range(self.columnCount()):
            item.setBackground(col, QBrush(background))
            item.setForeground(col, QBrush(foreground))
            item.setData(col, Qt.UserRole + 1, background)

    def find_item_by_row_index(self, row_index: int) -> QTreeWidgetItem | None:
        def _search(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, Qt.UserRole) == row_index:
                return item
            for i in range(item.childCount()):
                found = _search(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.topLevelItemCount()):
            found = _search(self.topLevelItem(i))
            if found is not None:
                return found
        return None

    def select_unit(self, row_index: int) -> None:
        current = self.currentItem()
        if current is not None and current.data(0, Qt.UserRole) == row_index:
            return

        item = self.find_item_by_row_index(row_index)
        if item is None:
            return

        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

        self.blockSignals(True)
        try:
            self.clearSelection()
            item.setSelected(True)
            self.setCurrentItem(item)
        finally:
            self.blockSignals(False)

        self.scrollToItem(item, QAbstractItemView.PositionAtCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                self._drag_start_pos = event.position().toPoint()
                self._drag_item = item
            else:
                self._drag_start_pos = None
                self._drag_item = None

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None and self._drag_item is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                top_level_items = self._get_top_level_selected_items()
                if not top_level_items:
                    top_level_items = [self._drag_item]
                items_payload = []
                for it in top_level_items:
                    row_index = it.data(0, Qt.UserRole)
                    if row_index is None:
                        continue
                    info = self.data.unit_info(row_index)
                    items_payload.append(info.to_drag_payload())

                if not items_payload:
                    self._drag_start_pos = None
                    self._drag_item = None
                    super().mouseMoveEvent(event)
                    return

                mime_data = QMimeData()
                mime_data.setData("application/x-unit-drop",
                                  QByteArray(json.dumps({"items": items_payload}).encode('utf-8')))

                drag = QDrag(self)
                drag.setMimeData(mime_data)
                drag.exec(Qt.DropAction.MoveAction)

                self._drag_start_pos = None
                self._drag_item = None

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_item = None
        super().mouseReleaseEvent(event)

    def _get_top_level_selected_items(self) -> List[QTreeWidgetItem]:
        """Get selected items that are not descendants of other selected items."""
        selected = set(self.selectedItems())
        top_level: List[QTreeWidgetItem] = []
        for item in selected:
            is_descendant_of_selected = False
            parent = item.parent()
            while parent is not None:
                if parent in selected:
                    is_descendant_of_selected = True
                    break
                parent = parent.parent()
            if not is_descendant_of_selected:
                top_level.append(item)
        return top_level

    def _is_valid_drop_target(self, source_row_indices: List[int],
                              target_row_index: int) -> bool:
        """Check if target is a valid drop point for any of the source items."""
        if target_row_index is None:
            return False
        target_level = self.data.get_level(target_row_index)
        if target_level is None:
            return False
        for src in source_row_indices:
            src_level = self.data.get_level(src)
            if src_level is None:
                return False
            if src == target_row_index:
                return False
            if self.data.is_descendant_of(target_row_index, src):
                return False
            if target_level != src_level and target_level != src_level - 1:
                return False
        return True

    def _clear_drop_target_highlight(self):
        if self._drop_target_item is not None and self._drop_target_original_bg is not None:
            self._drop_target_item.setBackground(0, self._drop_target_original_bg)
        self._drop_target_item = None
        self._drop_target_valid = False
        self._drop_target_original_bg = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-unit-drop"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if not event.mimeData().hasFormat("application/x-unit-drop"):
            return
        raw = event.mimeData().data("application/x-unit-drop")
        try:
            payload = json.loads(bytes(raw).decode('utf-8'))
            items = payload.get("items", [])
            source_row_indices = [it["row_index"] for it in items if "row_index" in it]
        except (json.JSONDecodeError, KeyError, TypeError):
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        target_row_index = target_item.data(0, Qt.UserRole) if target_item else None
        valid = self._is_valid_drop_target(source_row_indices, target_row_index)

        if target_item is not self._drop_target_item:
            self._clear_drop_target_highlight()
            self._drop_target_item = target_item
            if valid and target_item is not None:
                self._drop_target_original_bg = target_item.background(0)
                target_item.setBackground(0, QBrush(QColor("#3a5f3a")))
                self._drop_target_valid = True
            else:
                self._drop_target_valid = False
        else:
            if valid and not self._drop_target_valid and target_item is not None:
                self._drop_target_original_bg = target_item.background(0)
                target_item.setBackground(0, QBrush(QColor("#3a5f3a")))
                self._drop_target_valid = True
            elif not valid and self._drop_target_valid:
                if self._drop_target_original_bg is not None:
                    target_item.setBackground(0, self._drop_target_original_bg)
                self._drop_target_valid = False

        if valid:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._clear_drop_target_highlight()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self._clear_drop_target_highlight()
        if not event.mimeData().hasFormat("application/x-unit-drop"):
            event.ignore()
            return
        raw = event.mimeData().data("application/x-unit-drop")
        try:
            payload = json.loads(bytes(raw).decode('utf-8'))
            items = payload.get("items", [])
            source_row_indices = [it["row_index"] for it in items if "row_index" in it]
        except (json.JSONDecodeError, KeyError, TypeError):
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        if target_item is None:
            event.ignore()
            return
        target_row_index = target_item.data(0, Qt.UserRole)
        if target_row_index is None:
            event.ignore()
            return

        if not self._is_valid_drop_target(source_row_indices, target_row_index):
            event.ignore()
            return

        target_level = self.data.get_level(target_row_index)
        moved_any = False
        for src in source_row_indices:
            src_level = self.data.get_level(src)
            if src_level is None:
                continue
            peer_drop = (target_level == src_level)
            if self.data.reparent_unit(src, target_row_index, peer_drop):
                moved_any = True

        if moved_any:
            self.populate_with_expansion()
            self.unit_moved.emit(source_row_indices)
            event.acceptProposedAction()
        else:
            event.ignore()

    def on_selection_changed(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        if row_index is not None:
            self._selection_from_tree = True
            self.unit_selected.emit(row_index)

    def show_context_menu(self, position) -> None:
        item = self.itemAt(position)
        if not item:
            return

        menu = QMenu()
        menu.addAction("Cut", self.action_cut)
        menu.addAction("Paste", self.action_paste)
        if self._cut_row_indices:
            menu.addAction("Cancel Cut", self.action_cancel_cut)
        menu.addSeparator()
        menu.addAction("Delete", self.action_delete)
        menu.addSeparator()
        menu.addAction("Zoom to Unit", self.action_zoom_to_unit)
        menu.addAction("Collapse All", self.action_collapse_all)
        menu.addAction("Expand All", self.action_expand_all)
        menu.addSeparator()

        # Move Up / Down
        row_index = item.data(0, Qt.UserRole)
        if row_index is not None:
            level = self.data.get_level(row_index)
            if level is not None:
                parent_key = self.data.get_parent_key(
                    self.data.get_hierarchy_key_by_index(row_index))
                parent_row = next((i for i, k in enumerate(self.data._hierarchy_keys)
                                   if tuple(k) == parent_key), -1)
                if parent_row >= 0:
                    siblings = self.data._parent_to_children.get(parent_row, [])
                    if len(siblings) > 1:
                        current_pos = None
                        for pos, sib_idx in enumerate(siblings):
                            if sib_idx == row_index:
                                current_pos = pos
                                break
                        if current_pos is not None:
                            if current_pos > 0:
                                menu.addAction("Move Up", self.action_move_up)
                            if current_pos < len(siblings) - 1:
                                menu.addAction("Move Down", self.action_move_down)

            # Insert Template submenu
            if self._templates and level is not None:
                peer_level = level       # same level = peer
                child_level = level + 1  # one deeper = child
                parent_level = level - 1  # one shallower = parent

                peer_templates = [t for t in self._templates if t["level"] == peer_level]
                child_templates = [t for t in self._templates if t["level"] == child_level]
                # Parent only available for orphaned units with level > 1
                is_orphaned = self.data.is_orphaned(row_index)
                parent_templates = [t for t in self._templates if t["level"] == parent_level] if is_orphaned and level > 1 else []
                # Level 6 can only have peers, no children
                if level == 6:
                    child_templates = []

                has_peer = len(peer_templates) > 0
                has_child = len(child_templates) > 0
                has_parent = len(parent_templates) > 0

                insert_menu = menu.addMenu("Insert Template")
                if not has_peer and not has_child and not has_parent:
                    insert_menu.setEnabled(False)
                else:
                    if has_parent:
                        parent_menu = insert_menu.addMenu(f"Lvl {parent_level} (parent)")
                        for t in sorted(parent_templates, key=lambda x: x["name"]):
                            action = parent_menu.addAction(t["name"])
                            action.setData(json.dumps({
                                "file": t["file"], "id": t["id"],
                                "level": t["level"], "parent": True
                            }))
                    if has_peer:
                        peer_menu = insert_menu.addMenu(f"Lvl {peer_level} (peer)")
                        for t in sorted(peer_templates, key=lambda x: x["name"]):
                            action = peer_menu.addAction(t["name"])
                            action.setData(json.dumps({
                                "file": t["file"], "id": t["id"],
                                "level": t["level"], "peer": True
                            }))
                    if has_child:
                        child_menu = insert_menu.addMenu(f"Lvl {child_level} (child)")
                        for t in sorted(child_templates, key=lambda x: x["name"]):
                            action = child_menu.addAction(t["name"])
                            action.setData(json.dumps({
                                "file": t["file"], "id": t["id"],
                                "level": t["level"], "peer": False
                            }))

            # Save as Template
            menu.addAction("Save as Template", self.action_save_as_template)

            # Generate Subtree (not for level 6)
            if level is not None and level < 6:
                menu.addAction("Generate Subtree", self.action_generate_subtree)

        menu.addSeparator()
        menu.addAction("Copy CSV Format to Clipboard", self.action_copy_csv_format)

        # Dispatch submenu actions
        result = menu.exec(self.mapToGlobal(position))
        if result is not None:
            data = result.data()
            if data and isinstance(data, str):
                if data == "save_template":
                    self.action_save_as_template()
                else:
                    try:
                        info = json.loads(data)
                        self.action_insert_template(info)
                    except (json.JSONDecodeError, KeyError):
                        pass

    def action_zoom_to_unit(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        if row_index is None:
            return
        self.zoom_to_unit_requested.emit(row_index)

    def action_delete(self) -> None:
        items = self.selectedItems()
        if not items:
            QMessageBox.warning(self, "Delete Unit", "No unit selected")
            return

        # Collect all row indices to delete, expanding each to its full subtree.
        # Use a set to deduplicate (selecting both a parent and child is common).
        to_delete: set = set()
        for item in items:
            row_index = item.data(0, Qt.UserRole)
            if row_index is None:
                continue
            try:
                to_delete.update(self.data.get_subordinate_row_indices(row_index))
            except ValueError:
                to_delete.add(row_index)

        if not to_delete:
            return

        count = len(to_delete)
        unit_word = "unit" if count == 1 else "units"
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {count} {unit_word}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted_indices = sorted(to_delete)
        self.data.delete_rows(to_delete)

        self.populate_with_expansion()
        self.unit_deleted.emit(len(deleted_indices), deleted_indices)

    def action_cut(self) -> None:
        top_level_items = self._get_top_level_selected_items()
        if not top_level_items:
            QMessageBox.warning(self, "Cut", "No unit selected")
            return
        new_cut_rows: set = set()
        self._cut_top_level_rows: set = set()
        for item in top_level_items:
            row_index = item.data(0, Qt.UserRole)
            if row_index is None:
                continue
            self._cut_top_level_rows.add(row_index)
            try:
                new_cut_rows.update(self.data.get_subordinate_row_indices(row_index))
            except ValueError:
                new_cut_rows.add(row_index)
        self._cut_row_indices = new_cut_rows
        self._apply_cut_visual()

    def action_paste(self) -> None:
        if not self._cut_top_level_rows:
            return
        selected = self.selectedItems()
        target_item = None
        for item in selected:
            if item.data(0, Qt.UserRole) not in self._cut_row_indices:
                target_item = item
                break
        if target_item is None:
            target_item = self.currentItem()
        if target_item is None:
            QMessageBox.warning(self, "Paste", "No target unit selected")
            return
        target_row_index = target_item.data(0, Qt.UserRole)
        if target_row_index is None:
            QMessageBox.warning(self, "Paste", "Invalid target")
            return

        sources = list(self._cut_top_level_rows)
        valid_sources = [s for s in sources if self.data.get_level(s) is not None]
        if not self._is_valid_drop_target(valid_sources, target_row_index):
            QMessageBox.warning(
                self, "Paste",
                "Cannot paste here: target level is not compatible with the cut units.")
            return

        target_level = self.data.get_level(target_row_index)
        moved_any = False
        for src in valid_sources:
            src_level = self.data.get_level(src)
            if src_level is None:
                continue
            peer_drop = (target_level == src_level)
            if self.data.reparent_unit(src, target_row_index, peer_drop):
                moved_any = True
        if moved_any:
            self.populate_with_expansion()
            self.unit_moved.emit(valid_sources)
            self.action_cancel_cut()

    def action_cancel_cut(self) -> None:
        if not self._cut_row_indices:
            return
        self._cut_row_indices = set()
        self._cut_top_level_rows = set()
        self._clear_cut_visual()

    def _apply_cut_visual(self) -> None:
        strike_font = QFont()
        strike_font.setStrikeOut(True)
        for item in self._collect_all_items():
            row_index = item.data(0, Qt.UserRole)
            if row_index in self._cut_row_indices:
                for col in range(self.columnCount()):
                    f = item.font(col)
                    f.setStrikeOut(True)
                    item.setFont(col, f)

    def _clear_cut_visual(self) -> None:
        for item in self._collect_all_items():
            for col in range(self.columnCount()):
                f = item.font(col)
                f.setStrikeOut(False)
                item.setFont(col, f)

    def action_collapse_all(self) -> None:
        self.collapseAll()

    def action_expand_all(self) -> None:
        self.expandAll()

    def action_insert_template(self, info: dict) -> None:
        """Insert a template unit at the selected location."""
        items = self.selectedItems()
        if not items:
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            return

        template = next((t for t in self._templates
                         if t["file"] == info["file"] and t["id"] == info["id"]),
                        None)
        if template is None:
            QMessageBox.warning(self, "Insert Template", "Template not found")
            return

        try:
            is_peer = info.get("peer", False)
            is_parent = info.get("parent", False)
            new_idx = self.data.reparent_unit(
                None, row_index, peer_drop=is_peer and not is_parent,
                new_row_data=template["row"],
                source_level=template["level"],
                parent_drop=is_parent)
            if isinstance(new_idx, int):
                self.populate()
                self.select_unit(new_idx)
                self.unit_added.emit()
            else:
                QMessageBox.warning(self, "Insert Template",
                                    "Failed to insert template at this location")
        except Exception as e:
            QMessageBox.critical(self, "Insert Template Error",
                                 f"Failed to insert template:\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def action_generate_subtree(self) -> None:
        """Generate a subtree of units under the selected unit."""
        from gui.oob_generate_dialog import (
            GenerateSubtreeConfirmDialog, RESULT_BACK, RESULT_CONFIRM, RESULT_REGENERATE,
        )

        items = self.selectedItems()
        if not items:
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            return

        from constants import LEVEL_NAMES
        level = self.data.get_level(row_index)

        # Parent node info (constant throughout the flow)
        info = self.data.unit_info(row_index)
        hierarchy_key = self.data.get_hierarchy_key_by_index(row_index)
        level_info_str = self.data.get_hierarchy_level_name_and_index(hierarchy_key)
        row = self.data.df.iloc[row_index]
        exp_raw = row.get("Experience", 0)
        parent_exp = float(exp_raw) if exp_raw is not None and not pd.isna(exp_raw) else 0.0
        parent_node = {
            "name": info.name,
            "level": level,
            "level_info": level_info_str,
            "head_count": info.head_count,
            "experience": parent_exp,
            "side": info.side,
        }

        config = None

        while True:
            # Phase 1: Settings dialog (only on first entry or after Back)
            if config is None:
                dialog = GenerateSubtreeDialog(level, self._templates, self)
                if dialog.exec() != QDialog.Accepted:
                    return
                config = dialog.get_config()

            # Phase 2: Build preview with resolved modifiers
            try:
                preview_nodes, counts_by_level, total_head = self._build_preview_tree(config)
            except Exception as e:
                QMessageBox.critical(self, "Preview Error",
                                     f"Failed to build preview:\n\n"
                                     f"Error: {type(e).__name__}: {str(e)}\n\n"
                                     f"Stack trace:\n{traceback.format_exc()}")
                return

            if not preview_nodes:
                QMessageBox.information(self, "Generate Subtree", "Nothing to generate.")
                return

            # Build settings summary text
            settings_lines = [f"Selected Parent: {items[0].text(0)}", "", "Settings:"]
            for cfg in config:
                if cfg["min"] == 0 and cfg["max"] == 0:
                    continue
                lvl = cfg["level"]
                lname = LEVEL_NAMES[lvl - 1] if lvl <= len(LEVEL_NAMES) else f"Lvl {lvl}"
                tname = cfg["template"]["name"] if cfg["template"] else "(none)"
                if cfg["min"] == cfg["max"]:
                    settings_lines.append(f"  Lvl {lvl} {lname}s: {cfg['min']} x {tname}")
                else:
                    settings_lines.append(f"  Lvl {lvl} {lname}s: {cfg['min']}-{cfg['max']} x {tname}")
            settings_text = "\n".join(settings_lines)

            # Build unit count summary
            count_parts = []
            for lvl in sorted(counts_by_level.keys()):
                lname = LEVEL_NAMES[lvl - 1] if lvl <= len(LEVEL_NAMES) else f"Lvl {lvl}"
                count_parts.append(f"{counts_by_level[lvl]} {lname}{'s' if counts_by_level[lvl] != 1 else ''}")
            summary_text = f"Created {', '.join(count_parts)}. Total of {total_head:,} men."

            # Phase 3: Confirmation dialog with preview tree
            confirm = GenerateSubtreeConfirmDialog(
                settings_text, summary_text, preview_nodes, parent_node, self)
            result = confirm.exec()

            if result == RESULT_CONFIRM:
                # Phase 4: Actually generate using the exact preview rows
                try:
                    parent_key = self.data.get_hierarchy_key_by_index(row_index)
                    self._insert_preview_tree(row_index, parent_key, preview_nodes)
                    self.data._invalidate_caches()
                    self.data._build_adjacency_index()
                    self._expanded_keys.add(parent_key)
                    self.populate_with_expansion()
                    self.select_unit(row_index)
                    self.unit_added.emit()
                except Exception as e:
                    QMessageBox.critical(self, "Generate Subtree Error",
                                         f"Failed to generate subtree:\n\n"
                                         f"Error: {type(e).__name__}: {str(e)}\n\n"
                                         f"Stack trace:\n{traceback.format_exc()}")
                return

            elif result == RESULT_REGENERATE:
                # Re-run preview with same config (re-roll random counts)
                continue

            elif result == RESULT_BACK:
                # Return to settings dialog
                config = None
                continue

            else:
                # Dialog was closed (X button) — exit
                return

    def _build_preview_tree(self, config: list[dict]) -> tuple:
        """Build preview nodes with resolved modifiers using synthetic parent indices.

        Each node stores its fully resolved row_dict so that the exact same
        data is inserted on confirm (no re-resolution of modifiers).

        Returns (top_level_nodes, counts_by_level, total_head_count).
        """
        from constants import HIERARCHY_COLS, LEVEL_NAMES, INT_COLUMNS
        synthetic_parent = -1
        counts_by_level: dict[int, int] = {}
        total_head = 0

        def build_level(parent_idx: int, cfg_idx: int) -> tuple[list[dict], int]:
            nonlocal synthetic_parent
            if cfg_idx >= len(config):
                return [], 0
            cfg = config[cfg_idx]
            if cfg["min"] == 0 and cfg["max"] == 0:
                return [], 0
            template = cfg["template"]
            if template is None:
                return [], 0

            lvl = cfg["level"]
            count = random.randint(cfg["min"], cfg["max"])
            counts_by_level[lvl] = counts_by_level.get(lvl, 0) + count
            nodes = []
            level_head = 0

            for _ in range(count):
                # Copy template row
                columns = list(self.data.df.columns) if self.data.df is not None else []
                row_dict = {col: template["row"].get(col, "") for col in columns}

                # Set hierarchy columns for the preview row
                source_level = template["level"]
                for i, hcol in enumerate(HIERARCHY_COLS):
                    if i == source_level - 1:
                        row_dict[hcol] = 1
                    else:
                        row_dict[hcol] = 0

                # Resolve modifiers using synthetic parent index
                self.data._resolve_modifiers(row_dict, parent_idx)

                # Convert INT_COLUMNS
                for col in INT_COLUMNS:
                    if col in row_dict:
                        try:
                            row_dict[col] = int(float(str(row_dict[col]))) if str(row_dict[col]).strip() else 0
                        except (ValueError, TypeError):
                            row_dict[col] = 0

                # Extract display values
                name = str(row_dict.get("NAME1", "") or row_dict.get("Name", "") or "?")
                hc = row_dict.get("Head Count", 0)
                exp = row_dict.get("Experience", 0)
                side_raw = row_dict.get("SIDE 1", 0)
                try:
                    side = int(side_raw)
                except (ValueError, TypeError):
                    side = 0

                level_info_str = f"{LEVEL_NAMES[lvl - 1] if lvl <= len(LEVEL_NAMES) else '?'} (1)"

                node = {
                    "name": name,
                    "level": lvl,
                    "level_info": level_info_str,
                    "head_count": hc,
                    "experience": exp,
                    "side": side,
                    "resolved_row": row_dict,
                    "children": [],
                }

                # Recurse for next level
                synthetic_parent -= 1
                child_nodes, child_head = build_level(synthetic_parent, cfg_idx + 1)
                node["children"] = child_nodes

                level_head += hc + child_head
                nodes.append(node)

            return nodes, level_head

        top_nodes, total_head = build_level(synthetic_parent, 0)
        self._compute_preview_aggregates(top_nodes)
        return top_nodes, counts_by_level, total_head

    def _compute_preview_aggregates(self, nodes: list[dict]) -> None:
        """Compute subtree_strength and subtree_experience for each preview node."""
        for node in nodes:
            self._compute_preview_aggregates(node.get("children", []))
            hc = node.get("head_count", 0)
            child_strength = sum(c.get("subtree_strength", c.get("head_count", 0))
                                for c in node.get("children", []))
            node["subtree_strength"] = hc + child_strength

            children = node.get("children", [])
            if not children:
                node["subtree_experience"] = node.get("experience", 0.0)
            else:
                child_exps = [c.get("subtree_experience", c.get("experience", 0.0))
                              for c in children]
                if child_exps:
                    node["subtree_experience"] = sum(child_exps) / len(child_exps)
                else:
                    node["subtree_experience"] = node.get("experience", 0.0)

    def _insert_preview_tree(self, parent_row_index: int, parent_key: tuple,
                              nodes: list[dict]) -> None:
        """Insert the exact resolved rows from the preview into the DataFrame.

        Walks the preview tree top-down, setting hierarchy keys based on
        the real parent key and child index. Each node's 'resolved_row'
        is the exact dict that was shown in the preview.
        Offsets l_value past any existing children at the same level.
        """
        from constants import HIERARCHY_COLS

        def _max_existing_l_value(parent_idx: int, level: int) -> int:
            """Find the max hierarchy value at *level* among existing children."""
            max_val = 0
            for child_idx in self.data._parent_to_children.get(parent_idx, []):
                child_level = self.data.get_level(child_idx)
                if child_level == level:
                    hk = self.data.get_hierarchy_key_by_index(child_idx)
                    val = hk[level - 1]
                    if val > max_val:
                        max_val = val
            return max_val

        if not nodes:
            return

        # Find the level of these nodes and offset past existing children
        first_level = nodes[0]["level"]
        existing_max = _max_existing_l_value(parent_row_index, first_level)
        l_value = existing_max

        for node in nodes:
            l_value += 1
            resolved_row = dict(node["resolved_row"])

            source_level = node["level"]
            for i, hcol in enumerate(HIERARCHY_COLS):
                if i < source_level - 1:
                    resolved_row[hcol] = parent_key[i] if i < len(parent_key) else 0
                elif i == source_level - 1:
                    resolved_row[hcol] = l_value
                else:
                    resolved_row[hcol] = 0

            resolved_row["line_number"] = ""

            # Assign unique ID
            template_id = str(resolved_row.get("ID", "")).strip()
            if template_id and "ID" in self.data.df.columns:
                used_indices = set()
                for val in self.data.df["ID"].dropna():
                    val_str = str(val).strip()
                    if val_str.startswith(template_id) and val_str != template_id:
                        suffix = val_str[len(template_id):]
                        try:
                            used_indices.add(int(suffix))
                        except ValueError:
                            pass
                idx = 1
                while idx in used_indices:
                    idx += 1
                resolved_row["ID"] = f"{template_id}{idx}"

            # Append to DataFrame
            new_df = pd.DataFrame([resolved_row])
            for col in list(new_df.columns):
                if col in HIERARCHY_COLS:
                    new_df[col] = pd.to_numeric(new_df[col], errors="coerce").astype("Int64")
            self.data.df = pd.concat([self.data.df, new_df], ignore_index=True)
            new_row_idx = len(self.data.df) - 1

            # Build this node's key for its children
            child_key = list(parent_key[:source_level - 1]) + [l_value] + [0] * (6 - source_level)
            child_key_tuple = tuple(child_key)

            # Recurse into children
            if node.get("children"):
                self._insert_preview_tree(new_row_idx, child_key_tuple, node["children"])

    def action_save_as_template(self) -> None:
        """Save the selected unit as a user template."""
        items = self.selectedItems()
        if not items:
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            return

        try:
            new_id = self.data.save_as_template(row_index, self._templates_dir)
            self.load_templates()
            QMessageBox.information(self, "Save as Template",
                                    f"Saved as template '{new_id}'")
            self.unit_added.emit()
        except Exception as e:
            QMessageBox.critical(self, "Save as Template Error",
                                 f"Failed to save template:\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def action_copy_csv_format(self) -> None:
        items = self.selectedItems()
        if not items:
            QMessageBox.warning(self, "Copy CSV", "No unit selected")
            return

        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        if row_index is None:
            QMessageBox.warning(self, "Copy CSV", "Cannot copy this item")
            return

        try:
            row = self.data.df.iloc[row_index]
            csv_line = ",".join(str(val) if pd.notna(val) else "" for val in row.values)
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(csv_line)
            QMessageBox.information(self, "Copy CSV", "Unit data copied to clipboard in CSV format")
        except Exception as e:
            QMessageBox.critical(self, "Copy CSV Error", f"Failed to copy to clipboard:\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def action_move_up(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            return
        if self.data.move_unit(row_index, -1):
            self.populate_with_expansion()
            self.select_unit(row_index)

    def action_move_down(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            return
        if self.data.move_unit(row_index, +1):
            self.populate_with_expansion()
            self.select_unit(row_index)
