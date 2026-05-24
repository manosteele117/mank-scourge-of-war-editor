from PySide6.QtWidgets import (
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QSplitter,
    QVBoxLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView
from oob_model import OOBData
import pandas as pd


class OOBDetailsWidget(QWidget):
    """
    Widget for displaying and editing unit detail information.
    Uses a horizontal splitter with left and right tables.
    """
    
    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)
        
        self.data = data
        self.current_row_index = None
        
        # Create splitter for left/right detail views
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Left detail view (before Head Count)
        self.details_left = QTableWidget()
        self.details_left.setColumnCount(2)
        self.details_left.setHorizontalHeaderLabels(["Field", "Value"])
        self.details_left.horizontalHeader().setStretchLastSection(True)
        self.details_left.horizontalHeader().setDefaultSectionSize(100)
        self.details_left.verticalHeader().setVisible(False)
        self.details_left.verticalHeader().setDefaultSectionSize(16)
        self.details_left.setShowGrid(False)
        self.details_left.setAlternatingRowColors(True)
        self.details_left.itemChanged.connect(self.on_detail_cell_changed)
        
        # Right detail view (Head Count onwards)
        self.details_right = QTableWidget()
        self.details_right.setColumnCount(2)
        self.details_right.setHorizontalHeaderLabels(["Field", "Value"])
        self.details_right.horizontalHeader().setStretchLastSection(True)
        self.details_right.horizontalHeader().setDefaultSectionSize(100)
        self.details_right.verticalHeader().setVisible(False)
        self.details_right.verticalHeader().setDefaultSectionSize(16)
        self.details_right.setShowGrid(False)
        self.details_right.setAlternatingRowColors(True)
        self.details_right.itemChanged.connect(self.on_detail_cell_changed)
        
        self.splitter.addWidget(self.details_left)
        self.splitter.addWidget(self.details_right)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        
        # Layout
        layout = QVBoxLayout(self)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #161616;
                alternate-background-color: #1f1f1f;
                color: #e0e0e0;
                gridline-color: #333333;
            }
            QTableWidget::item {
                color: #e0e0e0;
            }
            QHeaderView::section {
                background-color: #1f1f1f;
                color: #e0e0e0;
                border: 1px solid #333333;
            }
        """)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
        self.setLayout(layout)
    
    def populate(self, row_index: int) -> None:
        """
        Populate the detail views for a specific row.
        
        Args:
            row_index: Index of the row to display
        """
        if self.data.df is None or row_index is None:
            self.clear()
            return
        
        self.current_row_index = row_index
        row = self.data.df.iloc[row_index]
        
        # Find the index of "Head Count" column
        head_count_idx = None
        for i, col in enumerate(row.index):
            if col == "Head Count":
                head_count_idx = i
                break
        
        if head_count_idx is None:
            head_count_idx = len(row.index)
        
        # Split columns
        left_cols = row.index[:head_count_idx]
        right_cols = row.index[head_count_idx:]
        
        # Populate left table (before Head Count)
        self.details_left.clearContents()
        self.details_left.setRowCount(len(left_cols))
        
        for i, column in enumerate(left_cols):
            field_item = QTableWidgetItem(str(column))
            value_item = QTableWidgetItem(str(row[column]))
            
            field_item.setFlags(field_item.flags() & ~Qt.ItemIsEditable)
            # Make value item editable
            
            self.details_left.setItem(i, 0, field_item)
            self.details_left.setItem(i, 1, value_item)
        
        self.details_left.resizeColumnsToContents()
        self.details_left.resizeRowsToContents()
        
        # Populate right table (Head Count onwards)
        self.details_right.clearContents()
        self.details_right.setRowCount(len(right_cols))
        
        for i, column in enumerate(right_cols):
            field_item = QTableWidgetItem(str(column))
            value_item = QTableWidgetItem(str(row[column]))
            
            field_item.setFlags(field_item.flags() & ~Qt.ItemIsEditable)
            # Make value item editable
            
            self.details_right.setItem(i, 0, field_item)
            self.details_right.setItem(i, 1, value_item)
        
        self.details_right.resizeColumnsToContents()
        self.details_right.resizeRowsToContents()
    
    def clear(self) -> None:
        """Clear all detail views."""
        self.current_row_index = None
        self.details_left.clearContents()
        self.details_right.clearContents()
        self.details_left.setRowCount(0)
        self.details_right.setRowCount(0)
    
    def on_detail_cell_changed(self, item: QTableWidgetItem) -> None:
        """Handle changes to detail table cells and update the dataframe."""
        if self.current_row_index is None or self.data.df is None:
            return
        
        # Determine which table and get the field name
        table = self.sender()
        row_in_table = item.row()
        col = item.column()
        
        # Only update on value column changes (column 1)
        if col != 1:
            return
        
        field_name = None
        if table == self.details_left:
            field_name = self.details_left.item(row_in_table, 0).text()
        elif table == self.details_right:
            field_name = self.details_right.item(row_in_table, 0).text()
        
        if field_name:
            new_value = item.text()
            if new_value == "<NA>":
                new_value = pd.NA
            else:
                try:
                    new_value = int(new_value)
                except ValueError:
                    pass  # Keep as string if not an integer
            
            self.data.set_cell(self.current_row_index, field_name, new_value)
