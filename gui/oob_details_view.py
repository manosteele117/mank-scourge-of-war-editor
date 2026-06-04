from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from PySide6.QtCore import Qt
from core.oob_model import OOBData
import pandas as pd


class OOBDetailsWidget(QWidget):
    """Widget for displaying and editing unit detail information."""

    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)
        self.data = data
        self.current_row_index = None

        self.details_table = QTableWidget()
        self.details_table.setColumnCount(2)
        self.details_table.setHorizontalHeaderLabels(["Field", "Value"])
        self.details_table.horizontalHeader().setStretchLastSection(True)
        self.details_table.horizontalHeader().setDefaultSectionSize(100)
        self.details_table.verticalHeader().setVisible(False)
        self.details_table.verticalHeader().setDefaultSectionSize(16)
        self.details_table.setShowGrid(False)
        self.details_table.setAlternatingRowColors(True)
        self.details_table.itemChanged.connect(self.on_detail_cell_changed)

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
        layout.addWidget(self.details_table)
        self.setLayout(layout)

    def populate(self, row_index: int) -> None:
        if self.data.df is None or row_index is None:
            self.clear()
            return

        self.current_row_index = row_index
        row = self.data.df.iloc[row_index]

        self.details_table.blockSignals(True)
        try:
            self.details_table.clearContents()
            self.details_table.setRowCount(len(row.index))

            for i, column in enumerate(row.index):
                field_item = QTableWidgetItem(str(column))
                value_item = QTableWidgetItem(str(row[column]))
                field_item.setFlags(field_item.flags() & ~Qt.ItemIsEditable)
                self.details_table.setItem(i, 0, field_item)
                self.details_table.setItem(i, 1, value_item)

            self.details_table.resizeRowsToContents()
            self.details_table.resizeColumnToContents(0)
        finally:
            self.details_table.blockSignals(False)

    def clear(self) -> None:
        self.current_row_index = None
        self.details_table.clearContents()
        self.details_table.setRowCount(0)

    def on_detail_cell_changed(self, item: QTableWidgetItem) -> None:
        if self.current_row_index is None or self.data.df is None:
            return

        row_in_table = item.row()
        col = item.column()
        if col != 1:
            return

        field_name = self.details_table.item(row_in_table, 0).text()
        if field_name:
            new_value = item.text()
            if new_value == "<NA>":
                new_value = pd.NA
            else:
                try:
                    new_value = int(new_value)
                except ValueError:
                    pass
            self.data.set_cell(self.current_row_index, field_name, new_value)
