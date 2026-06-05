import json
import os
from typing import Dict, List, Tuple
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox, QHeaderView, QAbstractItemView,
    QFileDialog, QApplication,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QByteArray
from PySide6.QtGui import QBrush, QColor, QDrag
from core.oob_model import OOBData
from constants import TREE_SIDE_1_BG, TREE_SIDE_2_BG
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
    delete_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    insert_template_requested = Signal()
    zoom_to_unit_requested = Signal(int)
    formation_requested = Signal(int, dict)

    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)

        self.data = data
        self._drag_start_pos = None
        self._drag_item = None
        self._selection_from_tree = False

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
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._selection_from_tree = False

    def populate(self) -> None:
        self.clear()
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
        line_nums = [int(v) if v is not None and not pd.isna(v) else i + 2
                     for i, v in enumerate(df["line_number"].tolist())] if "line_number" in df.columns else list(range(2, n_rows + 2))
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
        items_by_key: Dict[Tuple, QTreeWidgetItem] = {}
        top_level_items: List[QTreeWidgetItem] = []
        self.blockSignals(True)
        try:
            for idx in range(n_rows):
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
                    item = QTreeWidgetItem([
                        info.name, level_info, strength_str,
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

        self.expandToDepth(2)
        for col in range(self.columnCount()):
            self.resizeColumnToContents(col)

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
                row_index = self._drag_item.data(0, Qt.UserRole)
                if row_index is not None:
                    info = self.data.unit_info(row_index)
                    unit_payload = info.to_drag_payload()

                    mime_data = QMimeData()
                    mime_data.setData("application/x-unit-drop",
                                      QByteArray(json.dumps(unit_payload).encode('utf-8')))

                    drag = QDrag(self)
                    drag.setMimeData(mime_data)
                    drag.exec(Qt.DropAction.CopyAction)

                self._drag_start_pos = None
                self._drag_item = None

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_item = None
        super().mouseReleaseEvent(event)

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

                # Add Single Unit submenu
                if level < 6:
                    unit_menu = menu.addMenu("Add Single Unit")
                    templates_dir = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)),
                        "templates", "units")
                    if os.path.exists(templates_dir):
                        for fname in sorted(os.listdir(templates_dir)):
                            if fname.endswith(".csv"):
                                template_name = fname[:-4]  # strip .csv
                                action = unit_menu.addAction(template_name)
                                action.setData(os.path.join(templates_dir, fname))

                # Add Formation submenu
                if level < 6:
                    formation_menu = menu.addMenu("Add Formation")
                    action_infantry = formation_menu.addAction("Infantry Formation")
                    action_infantry.setData("infantry")
                    action_cavalry = formation_menu.addAction("Cavalry Formation")
                    action_cavalry.setData("cavalry")
                    action_artillery = formation_menu.addAction("Artillery Formation")
                    action_artillery.setData("artillery")

        menu.addSeparator()
        menu.addAction("Insert Unit Template", self.action_insert_template)
        menu.addAction("Copy CSV Format to Clipboard", self.action_copy_csv_format)

        # Connect submenu actions
        result = menu.exec(self.mapToGlobal(position))
        if result is not None:
            data = result.data()
            if data and isinstance(data, str):
                if data.endswith(".csv"):
                    self.action_add_single_unit(data)
                elif data in ("infantry", "cavalry", "artillery"):
                    self.action_add_formation(data)

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

        # Snapshot each root's hierarchy key and subordinate indices *before* any
        # deletion.  Delete in reverse order so that earlier row indices stay valid
        # as the DataFrame shrinks from the tail.
        roots = []
        for item in items:
            row_index = item.data(0, Qt.UserRole)
            if row_index is None:
                continue
            try:
                hk = self.data.get_hierarchy_key_by_index(row_index)
                sub = self.data.get_subordinate_row_indices(row_index)
                roots.append((row_index, hk, sub))
            except ValueError:
                pass

        all_deleted_indices: list = []
        for row_index, hk, sub in reversed(roots):
            # Validate: the hierarchy key at this row must still match (it may have
            # shifted or disappeared after a prior deletion).
            try:
                if tuple(self.data._hierarchy_keys[row_index].tolist()) != tuple(hk):
                    continue
            except (IndexError, TypeError):
                continue
            all_deleted_indices.extend(sub)
            self.data.delete_unit(row_index)

        self.populate()
        self.unit_deleted.emit(len(all_deleted_indices), all_deleted_indices)

    def action_collapse_all(self) -> None:
        self.collapseAll()

    def action_expand_all(self) -> None:
        self.expandAll()

    def action_insert_template(self) -> None:
        items = self.selectedItems()
        if not items:
            QMessageBox.warning(self, "Insert Template", "No parent unit selected")
            return

        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        if row_index is None:
            QMessageBox.warning(self, "Insert Template", "Cannot insert under this item")
            return
        self.insert_template_requested.emit()

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
            QMessageBox.critical(self, "Copy CSV Error", f"Failed to copy: {str(e)}")

    def action_move_up(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            return
        if self.data.move_unit(row_index, -1):
            self.populate()
            self.select_unit(row_index)

    def action_move_down(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            return
        if self.data.move_unit(row_index, +1):
            self.populate()
            self.select_unit(row_index)

    def action_add_single_unit(self, template_path: str) -> None:
        items = self.selectedItems()
        if not items:
            QMessageBox.warning(self, "Add Unit", "No parent unit selected")
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            QMessageBox.warning(self, "Add Unit", "Cannot add under this item")
            return
        try:
            new_idx = self.data.insert_unit(row_index, template_path)
            self.populate()
            self.select_unit(new_idx)
        except Exception as e:
            QMessageBox.critical(self, "Add Unit Error", f"Failed to add unit:\n{str(e)}")

    def action_add_formation(self, formation_type: str) -> None:
        items = self.selectedItems()
        if not items:
            QMessageBox.warning(self, "Add Formation", "No parent unit selected")
            return
        row_index = items[0].data(0, Qt.UserRole)
        if row_index is None:
            QMessageBox.warning(self, "Add Formation", "Cannot add under this item")
            return
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates", "units")
        composition = {
            "commander_name": f"New {formation_type.title()} Commander",
            "commander_level": 5,
            "commander_formation": formation_type.title(),
            "sub_units": [
                {"template": f"lvl6_{formation_type}.csv", "count": 3},
            ]
        }
        try:
            inserted = self.data.insert_formation(row_index, composition)
            self.populate()
            if inserted:
                self.select_unit(inserted[0])
        except Exception as e:
            QMessageBox.critical(self, "Add Formation Error", f"Failed to add formation:\n{str(e)}")
