import json
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox, QHeaderView, QAbstractItemView,
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

    unit_deleted = Signal(int)
    unit_selected = Signal(int)
    unit_double_clicked = Signal(int)
    delete_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    insert_template_requested = Signal()
    zoom_to_unit_requested = Signal(int)

    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)

        self.data = data

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

        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setDragEnabled(True)

    def populate(self) -> None:
        self.clear()
        if self.data.df is None:
            return

        items_by_key = {}
        items_data = []
        for idx, row in self.data.df.iterrows():
            try:
                level = self.data.get_level_from_hierarchy(row)
                if level is None:
                    continue

                hierarchy_key = self.data.get_hierarchy_key(row, idx)
                name = str(row.get("NAME1", "Unknown"))
                strength = row.get("Head Count", "")
                avg_experience = row.get("Experience", "")
                level_info = self.data.get_hierarchy_level_name_and_index(hierarchy_key)
                line_num = int(row.get("line_number", idx + 2))
                side = int(row.get("SIDE 1", 0) or 0)

                items_data.append({
                    'idx': idx, 'level': level, 'hierarchy_key': hierarchy_key,
                    'name': name, 'strength': strength, 'avg_experience': avg_experience,
                    'level_info': level_info, 'line_num': line_num, 'side': side,
                })
            except ValueError as e:
                raise ValueError(f"Invalid data in CSV: {str(e)}\n{traceback.format_exc()}")

        items_data.sort(key=lambda x: x['level'])

        for data in items_data:
            item = QTreeWidgetItem([
                data['name'], data['level_info'], str(data['strength']),
                str(data['avg_experience']), str(data['line_num']),
            ])
            item.setData(0, Qt.UserRole, data['idx'])
            self.apply_side_colors(item, data['side'])

            parent_key = self.data.get_parent_key(data['hierarchy_key'])
            if parent_key in items_by_key:
                items_by_key[parent_key].addChild(item)
            else:
                self.addTopLevelItem(item)
            items_by_key[data['hierarchy_key']] = item

        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            self.calculate_total_strength(item)
            self.calculate_average_experience(item)

        self.expandToDepth(2)

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

    def calculate_total_strength(self, item: QTreeWidgetItem) -> float:
        row_index = item.data(0, Qt.UserRole)
        if row_index is None:
            total = 0
        else:
            row = self.data.df.iloc[row_index]
            try:
                total = float(row.get("Head Count", 0) or 0)
            except (ValueError, TypeError):
                total = 0

        for i in range(item.childCount()):
            child_item = item.child(i)
            child_total = self.calculate_total_strength(child_item)
            total += child_total

        display_val = str(int(total)) if total == int(total) else str(total)
        item.setText(2, display_val)
        return total

    def calculate_average_experience(self, item: QTreeWidgetItem) -> float:
        row_index = item.data(0, Qt.UserRole)
        if row_index is None:
            return 0.0

        row = self.data.df.iloc[row_index]
        try:
            own_exp = float(row.get("Experience", 0) or 0)
        except (ValueError, TypeError):
            own_exp = 0.0

        child_exps = []
        for i in range(item.childCount()):
            child_item = item.child(i)
            child_exp = self.calculate_average_experience(child_item)
            child_row_index = child_item.data(0, Qt.UserRole)
            if child_row_index is not None:
                child_row = self.data.df.iloc[child_row_index]
                child_formation = str(child_row.get("Formation", "") or "")
                if "SupplyWagon" not in child_formation:
                    child_exps.append(child_exp)

        if item.childCount() == 0:
            item.setText(3, f"{own_exp:.2f}")
            return own_exp

        avg_exp = (sum(child_exps) / len(child_exps)) if child_exps else own_exp
        item.setText(3, f"{avg_exp:.2f}")
        return avg_exp

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
                row_index = item.data(0, Qt.UserRole)
                if row_index is not None:
                    row = self.data.df.iloc[row_index]
                    unit_data = {
                        "row_index": row_index,
                        "name": str(row.get("NAME1", f"Unit {row_index}")),
                        "side": int(row.get("SIDE 1", 1) or 1),
                        "level": int(self.data.get_level_from_hierarchy(row) or 1),
                        "formation": str(row.get("Formation", "")),
                        "head_count": int(row.get("Head Count", 0) or 0),
                    }

                    mime_data = QMimeData()
                    mime_data.setData("application/x-unit-drop", QByteArray(json.dumps(unit_data).encode('utf-8')))

                    drag = QDrag(self)
                    drag.setMimeData(mime_data)
                    drag.exec(Qt.DropAction.CopyAction)

        super().mousePressEvent(event)

    def on_selection_changed(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        if row_index is not None:
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
        menu.addAction("Insert Unit Template", self.action_insert_template)
        menu.addAction("Copy CSV Format to Clipboard", self.action_copy_csv_format)

        menu.exec(self.mapToGlobal(position))

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

        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        if row_index is None:
            QMessageBox.warning(self, "Delete Unit", "Cannot delete this item")
            return

        try:
            num_deleted = self.data.delete_unit(row_index)
            self.populate()
            self.unit_deleted.emit(num_deleted)

            num_subordinates = num_deleted - 1
            if num_subordinates > 0:
                QMessageBox.information(self, "Delete Unit",
                                        f"Deleted unit and {num_subordinates} subordinates")
            else:
                QMessageBox.information(self, "Delete Unit", "Unit deleted")
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", f"Failed to delete unit:\n{str(e)}")

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
