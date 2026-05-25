from PySide6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QMessageBox,
    QHeaderView,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from oob_model import OOBData
import pandas as pd


class OOBTreeWidget(QTreeWidget):
    """
    Tree widget for displaying Order of Battle hierarchy.
    
    Signals:
        unit_deleted: Emitted when a unit is deleted; carries number of units deleted
        unit_selected: Emitted when a unit is selected; carries row index
    """
    
    unit_deleted = Signal(int)  # number of units deleted
    unit_selected = Signal(int)  # row_index
    delete_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    insert_template_requested = Signal()
    
    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)
        
        self.data = data
        
        # Setup tree appearance
        self.setColumnCount(4)
        self.setHeaderLabels(["Unit", "Level", "Strength", "Line"])
        
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
        #self.setAlternatingRowColors(True)

        # Expand first column to fit content
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        
        # Enable context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def populate(self) -> None:
        """Populate tree from OOBData dataframe."""
        self.clear()
        
        if self.data.df is None:
            return
        
        # Map hierarchy keys to tree items
        items_by_key = {}
        
        # First pass: collect all items with their hierarchy data
        items_data = []
        for idx, row in self.data.df.iterrows():
            try:
                level = self.data.get_level_from_hierarchy(row)
                
                if level is None:
                    continue
                
                hierarchy_key = self.data.get_hierarchy_key(row, idx)
                name = str(row.get("NAME1", "Unknown"))
                strength = row.get("Head Count", "")
                level_info = self.data.get_hierarchy_level_name_and_index(hierarchy_key)
                line_num = idx + 2  # +1 for header, +1 for 1-based indexing
                side = int(row.get("SIDE 1", 0) or 0)
                
                items_data.append({
                    'idx': idx,
                    'level': level,
                    'hierarchy_key': hierarchy_key,
                    'name': name,
                    'strength': strength,
                    'level_info': level_info,
                    'line_num': line_num,
                    'side': side
                })
                
            except ValueError as e:
                raise ValueError(f"Invalid data in CSV: {str(e)}")
        
        # Second pass: sort by hierarchy level and add to tree
        items_data.sort(key=lambda x: x['level'])
        
        for data in items_data:
            item = QTreeWidgetItem([
                data['name'],
                data['level_info'],
                str(data['strength']),
                str(data['line_num'])
            ])
            
            item.setData(0, Qt.UserRole, data['idx'])
            self.apply_side_colors(item, data['side'])

            # Get parent hierarchy key
            parent_key = self.data.get_parent_key(data['hierarchy_key'])
            
            # Find or add to parent
            if parent_key in items_by_key:
                items_by_key[parent_key].addChild(item)
            else:
                # Top-level item (no parent exists)
                self.addTopLevelItem(item)
            
            # Store this item for future children
            items_by_key[data['hierarchy_key']] = item
        
        # Calculate total strengths for each unit including subordinates
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            self.calculate_total_strength(item)
        
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
        """
        Apply side-specific background colors to the row.

        Args:
            item: Tree item to style.
            side: Side number from the data (1 or 2).
        """
        if side == 1:
            background = QColor("#2c2c40")  # blue for Side 1 (adjusted from 2c2c2c from base stylesheet)
            foreground = QColor("#ffffff")
        elif side == 2:
            background = QColor("#402c2c")  # red for Side 2 (adjusted from 2c2c2c from base stylesheet)
            foreground = QColor("#ffffff")
        else:
            return

        for col in range(self.columnCount()):
            item.setBackground(col, QBrush(background))
            item.setForeground(col, QBrush(foreground))
            item.setData(col, Qt.UserRole + 1, background)

    def calculate_total_strength(self, item: QTreeWidgetItem) -> float:
        """
        Recursively calculate total strength of a unit and all its subordinates.
        Updates the item's strength display.
        
        Args:
            item: Tree item to calculate strength for
            
        Returns:
            Total strength value
        """
        row_index = item.data(0, Qt.UserRole)
        if row_index is None:
            total = 0
        else:
            row = self.data.df.iloc[row_index]
            try:
                total = float(row.get("Head Count", 0) or 0)
            except (ValueError, TypeError):
                total = 0
        
        # Add strengths from all children
        for i in range(item.childCount()):
            child_item = item.child(i)
            child_total = self.calculate_total_strength(child_item)
            total += child_total
        
        # Update the item's strength display
        display_val = str(int(total)) if total == int(total) else str(total)
        item.setText(2, display_val)
        
        return total

    def find_item_by_row_index(self, row_index: int) -> QTreeWidgetItem | None:
        """
        Find the tree widget item that represents the given data row index.
        """
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
        """
        Select and scroll to the unit with the given row index.
        """
        current = self.currentItem()
        if current is not None and current.data(0, Qt.UserRole) == row_index:
            return

        item = self.find_item_by_row_index(row_index)
        if item is None:
            return

        # Expand parent chain so the item is visible
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

    def on_selection_changed(self) -> None:
        """Handle tree selection changes."""
        items = self.selectedItems()
        
        if not items:
            return
        
        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        
        if row_index is not None:
            self.unit_selected.emit(row_index)
    
    def show_context_menu(self, position) -> None:
        """Display context menu at the right-click position."""
        item = self.itemAt(position)
        
        if not item:
            return
        
        menu = QMenu()
        menu.addAction("Delete", self.action_delete)
        menu.addSeparator()
        menu.addAction("Collapse All", self.action_collapse_all)
        menu.addAction("Expand All", self.action_expand_all)
        menu.addSeparator()
        menu.addAction("Insert Unit Template", self.action_insert_template)
        menu.addAction("Copy CSV Format to Clipboard", self.action_copy_csv_format)
        
        menu.exec(self.mapToGlobal(position))
    
    def action_delete(self) -> None:
        """Delete the selected unit and all subordinates."""
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
        """Collapse all items in the tree."""
        self.collapseAll()
    
    def action_expand_all(self) -> None:
        """Expand all items in the tree."""
        self.expandAll()
    
    def action_insert_template(self) -> None:
        """Insert a new unit template under the selected unit."""
        items = self.selectedItems()
        
        if not items:
            QMessageBox.warning(self, "Insert Template", "No parent unit selected")
            return
        
        item = items[0]
        row_index = item.data(0, Qt.UserRole)
        
        if row_index is None:
            QMessageBox.warning(self, "Insert Template", "Cannot insert under this item")
            return
        
        # Emit signal; main window will handle the dialog and actual insertion
        self.insert_template_requested.emit()
    
    def action_copy_csv_format(self) -> None:
        """Copy the selected unit's data in CSV format to system clipboard."""
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
            
            # Create CSV line (comma-separated values)
            csv_line = ",".join(str(val) if pd.notna(val) else "" for val in row.values)
            
            # Copy to system clipboard
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(csv_line)
            
            QMessageBox.information(self, "Copy CSV", "Unit data copied to clipboard in CSV format")
        except Exception as e:
            QMessageBox.critical(self, "Copy CSV Error", f"Failed to copy: {str(e)}")
