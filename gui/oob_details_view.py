from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QComboBox,
    QLineEdit, QLabel,
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

        self._warning_label = QLabel()
        self._warning_label.setWordWrap(True)
        self._warning_label.setMaximumWidth(350)
        self._warning_label.setStyleSheet(
            "background: #2a2a2a; color: #c0a040; font-size: 10px;"
            "padding: 4px 8px; border: 1px solid #555; border-radius: 3px;"
        )
        self._warning_label.hide()

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
        if (event.type() == QEvent.FocusIn
                and obj.property("discouraged")):
            self._show_warning(obj)
        elif (event.type() == QEvent.FocusOut
                and obj.property("discouraged")):
            self._warning_label.hide()
        return super().eventFilter(obj, event)

    def _show_warning(self, edit: QLineEdit) -> None:
        top = self.window()
        if self._warning_label.parent() != top:
            self._warning_label.setParent(top)
        pos = edit.mapToGlobal(QPoint(0, 0))
        parent_pos = top.mapFromGlobal(pos)
        self._warning_label.setText(
            "This field is managed by this application, and should not be edited "
            "by hand, use the cut/paste/drag/insert commands to achieve the same result."
        )
        self._warning_label.adjustSize()
        label_y = parent_pos.y() - self._warning_label.sizeHint().height()
        self._warning_label.move(parent_pos.x(), label_y)
        self._warning_label.show()
        self._warning_label.raise_()

    def populate(self, row_index: int) -> None:
        self._warning_label.hide()
        if self.data.df is None or row_index is None:
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
                        self.details_table.setCellWidget(i, 1, combo)
                        self._widgets[i] = combo
                        continue

                edit = QLineEdit(display)
                edit.setProperty("field_name", column)
                if column in DISCOURAGED_FIELDS:
                    edit.installEventFilter(self)
                    edit.setProperty("discouraged", True)
                edit.editingFinished.connect(
                    lambda e=edit: self._on_widget_changed(e, e.text())
                )
                self.details_table.setCellWidget(i, 1, edit)
                self._widgets[i] = edit
            self.details_table.resizeRowsToContents()
            self.details_table.resizeColumnToContents(0)
        finally:
            self.details_table.blockSignals(False)

    def _on_widget_changed(self, widget, text: str) -> None:
        if self.current_row_index is None or self.data.df is None:
            return
        field_name = widget.property("field_name")
        if not field_name:
            return
        new_value = text if text else pd.NA
        self.data.set_cell(self.current_row_index, field_name, new_value)
        self.detail_changed.emit(field_name)

    def clear(self) -> None:
        self.current_row_index = None
        self._warning_label.hide()
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
