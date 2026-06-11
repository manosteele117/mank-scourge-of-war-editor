from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QComboBox,
    QLineEdit, QLabel, QPushButton,
)
from PySide6.QtCore import Qt, Signal, QEvent, QPoint
from core.oob_model import OOBData
from gui.oob_dropdowns import (
    has_dropdown, get_formation_options, get_weapon_options,
    get_unitglobal_class_options, get_gfxpack_options,
)
import pandas as pd

DISCOURAGED_FIELDS = {
    "line_number", "SIDE 1", "ARMY 2", "CORPS 3",
    "DIV 4", "BGDE 5", "BTN 6",
}


class OOBDetailsWidget(QWidget):
    """Widget for displaying and editing unit detail information."""

    detail_changed = Signal(str)

    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)
        self.data = data
        self.current_row_index = None
        self._widgets: dict[int, QWidget] = {}

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
        self.details_table.installEventFilter(self)

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
            QLineEdit {
                background-color: #161616;
                color: #e0e0e0;
                border: 1px solid #333333;
                padding: 1px 4px;
                selection-background-color: #336699;
            }
            QComboBox {
                background-color: #161616;
                color: #e0e0e0;
                border: 1px solid #333333;
                padding: 1px 4px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top left;
                width: 16px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #333333;
                border: 1px solid #444444;
            }
        """)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.details_table)
        self.setLayout(layout)

    def _get_combo_options(self, column: str, row_dict: dict) -> list[str]:
        if column == "Formation":
            return get_formation_options(row_dict)
        elif column == "Weapon":
            return get_weapon_options(row_dict)
        elif column == "CLASS":
            return get_unitglobal_class_options()
        elif column in ("FLAGS", "FLAG2"):
            return get_gfxpack_options()
        return []

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if obj is self.details_table or isinstance(obj, QComboBox):
                return True
        return super().eventFilter(obj, event)

    def populate(self, row_index: int) -> None:
        if self.data.df is None or row_index is None:
            self.clear()
            return

        if row_index < 0 or row_index >= len(self.data.df):
            self.clear()
            return

        self.current_row_index = row_index
        row = self.data.df.iloc[row_index]
        columns = list(row.index)
        row_dict = row.to_dict()

        self._widgets.clear()
        self.details_table.blockSignals(True)
        try:
            self.details_table.setRowCount(len(columns))
            for i, column in enumerate(columns):
                field_item = QTableWidgetItem(str(column))
                field_item.setFlags(field_item.flags() & ~Qt.ItemIsEditable)
                self.details_table.setItem(i, 0, field_item)

                val = row[column]
                display = "" if pd.isna(val) else str(val)

                if has_dropdown(column):
                    options = self._get_combo_options(column, row_dict)
                    if options:
                        combo = QComboBox()
                        combo.setEditable(True)
                        combo.addItems(options)
                        combo.setCurrentText(display)
                        combo.setProperty("field_name", column)
                        combo.currentTextChanged.connect(
                            lambda text, c=combo: self._on_widget_changed(c, text)
                        )
                        combo.installEventFilter(self)
                        self.details_table.setCellWidget(i, 1, combo)
                        self._widgets[i] = combo
                        continue

                edit = QLineEdit(display)
                edit.setProperty("field_name", column)
                if column in DISCOURAGED_FIELDS:
                    edit.installEventFilter(self)
                    edit.setProperty("discouraged", True)
                if column in ("SIDE 1", "ARMY 2", "CORPS 3", "DIV 4", "BGDE 5", "BTN 6"):
                    edit.setReadOnly(True)
                edit.editingFinished.connect(
                    lambda e=edit: self._on_widget_changed(e, e.text())
                )
                if column == "line_number":
                    edit.setReadOnly(True)
                    has_original = (
                        self.data._original_df is not None
                        and not pd.isna(val)
                        and str(val).strip() != ""
                    )
                    reset_btn = QPushButton("Reset")
                    reset_btn.setToolTip(
                        "Reset this unit's stats to original OOB values. "
                        "Hierarchy/location values are not reverted."
                    )
                    reset_btn.setFixedWidth(50)
                    reset_btn.setEnabled(has_original)
                    if has_original:
                        reset_btn.clicked.connect(self._on_reset_clicked)
                    container = QWidget()
                    container_layout = QHBoxLayout(container)
                    container_layout.setContentsMargins(0, 0, 0, 0)
                    container_layout.setSpacing(4)
                    container_layout.addWidget(edit)
                    container_layout.addWidget(reset_btn)
                    self.details_table.setCellWidget(i, 1, container)
                    self._widgets[i] = container
                else:
                    self.details_table.setCellWidget(i, 1, edit)
                    self._widgets[i] = edit
            self.details_table.resizeRowsToContents()
            self.details_table.resizeColumnToContents(0)
        finally:
            self.details_table.blockSignals(False)
        self.details_table.clearFocus()

    def _on_widget_changed(self, widget, text: str) -> None:
        if self.current_row_index is None or self.data.df is None:
            return
        field_name = widget.property("field_name")
        if not field_name:
            return
        new_value = text if text else pd.NA
        self.data.set_cell(self.current_row_index, field_name, new_value)
        self.detail_changed.emit(field_name)

    def _on_reset_clicked(self) -> None:
        if self.current_row_index is None or self.data.df is None:
            return
        row = self.data.df.iloc[self.current_row_index]
        line_number = row.get("line_number")
        if pd.isna(line_number) or str(line_number).strip() == "":
            return
        self.data.reset_row_from_original(int(line_number))
        self.populate(self.current_row_index)
        self.detail_changed.emit("")

    def clear(self) -> None:
        self.current_row_index = None
        self._widgets.clear()
        self.details_table.clearContents()
        self.details_table.setRowCount(0)

    def on_detail_cell_changed(self, item: QTableWidgetItem) -> None:
        if self.current_row_index is None or self.data.df is None:
            return

        row_in_table = item.row()
        col = item.column()
        if col != 1:
            return

        if row_in_table in self._widgets:
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
            self.detail_changed.emit(field_name)
