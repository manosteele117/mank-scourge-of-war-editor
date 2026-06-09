import os
from pathlib import Path
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QAbstractItemView, QFrame, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from gui.oob_dropdowns import get_gfx_options


MAPLOCATIONS_HEADER = [
    "Name", "ID", "Priority", "Type", "AI",
    "loc x", "loc z", "radius", "Men", "Points",
    "Fatigue", "Morale", "Ammo", "OccMod",
    "Beg", "End", "Interval", "Sprite",
    "Army1", "Army2", "Army3",
]

PRIORITY_COL = MAPLOCATIONS_HEADER.index("Priority")
NAME_COL = MAPLOCATIONS_HEADER.index("Name")
ID_COL = MAPLOCATIONS_HEADER.index("ID")
LOC_X_COL = MAPLOCATIONS_HEADER.index("loc x")
LOC_Z_COL = MAPLOCATIONS_HEADER.index("loc z")
SPRITE_COL = MAPLOCATIONS_HEADER.index("Sprite")
ARMY1_COL = MAPLOCATIONS_HEADER.index("Army1")
ARMY2_COL = MAPLOCATIONS_HEADER.index("Army2")
ARMY3_COL = MAPLOCATIONS_HEADER.index("Army3")

COMBO_COLUMNS = {PRIORITY_COL, SPRITE_COL, ARMY1_COL, ARMY2_COL, ARMY3_COL}
PRIORITY_OPTIONS = ["major", "minor"]


class ScenarioTab(QWidget):
    """Scenario tab for managing objectives and future scenario settings."""

    def __init__(self, map_widget, parent=None):
        super().__init__(parent)
        self.map_viewer = map_widget
        self._updating_table = False

        self._init_ui()

        self.map_viewer.objective_placed.connect(self._on_objectives_changed)
        self.map_viewer.objective_removed.connect(self._on_objectives_changed)
        self.map_viewer.objective_moved.connect(self._on_objective_moved)

    # ── UI setup ─────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Objectives section header ──
        obj_header = QHBoxLayout()
        obj_title = QLabel("Objectives")
        obj_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        obj_header.addWidget(obj_title)
        obj_header.addStretch(1)

        self.export_btn = QPushButton("Export Map Locations")
        self.export_btn.clicked.connect(self._on_export)
        obj_header.addWidget(self.export_btn)

        layout.addLayout(obj_header)

        # ── Single objectives table (all fields) ──
        self.objectives_table = QTableWidget()
        self.objectives_table.setColumnCount(len(MAPLOCATIONS_HEADER))
        self.objectives_table.setHorizontalHeaderLabels(MAPLOCATIONS_HEADER)
        self.objectives_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.objectives_table.horizontalHeader().setStretchLastSection(False)
        self.objectives_table.verticalHeader().setVisible(False)
        self.objectives_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.objectives_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.objectives_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.objectives_table.customContextMenuRequested.connect(
            self._on_objectives_context_menu)
        self.objectives_table.cellChanged.connect(self._on_cell_changed)

        layout.addWidget(self.objectives_table)

        # ── Separator + Scenario Settings placeholder ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        settings_title = QLabel("Scenario Settings")
        settings_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(settings_title)

        settings_placeholder = QLabel("Future scenario settings will appear here.")
        settings_placeholder.setStyleSheet("color: #888888;")
        layout.addWidget(settings_placeholder)

        layout.addStretch(1)

    # ── Objectives table sync ────────────────────────────────────

    def refresh_objectives(self):
        self._updating_table = True
        try:
            objectives = self.map_viewer.get_all_objectives_data()
            gfx_options = get_gfx_options()

            self.objectives_table.setRowCount(len(objectives))
            for row, obj in enumerate(objectives):
                obj_id = obj["id"]
                fields = obj["fields"]

                for col, col_name in enumerate(MAPLOCATIONS_HEADER):
                    if col in COMBO_COLUMNS:
                        combo = QComboBox()
                        combo.setEditable(True)
                        if col == PRIORITY_COL:
                            combo.addItems(PRIORITY_OPTIONS)
                        else:
                            combo.addItems(gfx_options)
                        current_val = str(fields.get(col_name, ""))
                        combo.setCurrentText(current_val)
                        combo.currentTextChanged.connect(
                            lambda text, oid=obj_id, cn=col_name: self._on_combo_changed(oid, cn, text))
                        self.objectives_table.setCellWidget(row, col, combo)
                    else:
                        value = str(fields.get(col_name, ""))
                        item = QTableWidgetItem(value)
                        if col in (NAME_COL, ID_COL, LOC_X_COL, LOC_Z_COL):
                            item.setData(Qt.UserRole, obj_id)
                        self.objectives_table.setItem(row, col, item)
        finally:
            self._updating_table = False

    def _on_objectives_changed(self, _id=None):
        self.refresh_objectives()

    def _on_objective_moved(self, objective_id: int, world_x: int, world_z: int):
        if self._updating_table:
            return
        self._updating_table = True
        try:
            for row in range(self.objectives_table.rowCount()):
                item = self.objectives_table.item(row, NAME_COL)
                if item is not None and item.data(Qt.UserRole) == objective_id:
                    x_item = self.objectives_table.item(row, LOC_X_COL)
                    z_item = self.objectives_table.item(row, LOC_Z_COL)
                    if x_item:
                        x_item.setText(str(world_x))
                    if z_item:
                        z_item.setText(str(world_z))
                    break
        finally:
            self._updating_table = False

    # ── Cell edits → update objective fields ─────────────────────

    def _on_cell_changed(self, item: QTableWidgetItem):
        if self._updating_table:
            return
        if item.column() in COMBO_COLUMNS:
            return

        row = item.row()
        col = item.column()
        col_name = MAPLOCATIONS_HEADER[col]

        # Find the objective_id from the Name column's UserRole data
        id_item = self.objectives_table.item(row, NAME_COL)
        if id_item is None:
            return
        obj_id = id_item.data(Qt.UserRole)
        if obj_id is None:
            return

        obj_data = self.map_viewer.get_objective_data(obj_id)
        if obj_data is None:
            return

        new_value = item.text()

        if col == NAME_COL:
            obj_data["name"] = new_value
            obj_data["fields"]["Name"] = new_value
            obj_data["fields"]["ID"] = new_value
            map_item = self.map_viewer.objectives_by_id.get(obj_id)
            if map_item is not None:
                map_item.name = new_value
                map_item.fields["Name"] = new_value
                map_item.fields["ID"] = new_value
                map_item.update()
            # Also update the ID column cell
            id_cell = self.objectives_table.item(row, ID_COL)
            if id_cell is not None and id_cell.text() != new_value:
                id_cell.setText(new_value)
        elif col == ID_COL:
            obj_data["fields"]["ID"] = new_value
            map_item = self.map_viewer.objectives_by_id.get(obj_id)
            if map_item is not None:
                map_item.fields["ID"] = new_value
        elif col == LOC_X_COL:
            try:
                new_x = int(new_value)
            except ValueError:
                return
            self.map_viewer.move_objective(obj_id, new_x, obj_data["world_z"])
        elif col == LOC_Z_COL:
            try:
                new_z = int(new_value)
            except ValueError:
                return
            self.map_viewer.move_objective(obj_id, obj_data["world_x"], new_z)
        else:
            obj_data["fields"][col_name] = new_value

    def _on_combo_changed(self, obj_id: int, field_name: str, new_value: str):
        if self._updating_table:
            return
        obj_data = self.map_viewer.get_objective_data(obj_id)
        if obj_data is not None:
            obj_data["fields"][field_name] = new_value

    # ── Context menu on objectives table ─────────────────────────

    def _on_objectives_context_menu(self, pos):
        rows = self.objectives_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        id_item = self.objectives_table.item(row, NAME_COL)
        if id_item is None:
            return
        obj_id = id_item.data(Qt.UserRole)
        if obj_id is None:
            return

        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Delete Objective",
                       lambda: self.map_viewer.remove_objective(obj_id))
        menu.exec(self.objectives_table.viewport().mapToGlobal(pos))

    # ── Export ───────────────────────────────────────────────────

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Map Locations", "", "CSV Files (*.csv)")
        if not path:
            return

        template = Path(__file__).parent.parent / "templates" / "maplocations.csv"
        if not template.exists():
            QMessageBox.warning(self, "Export Error",
                                f"Template not found:\n{template}")
            return

        with open(template, "r", encoding="cp1252") as f:
            header = f.readline().strip()

        objectives = self.map_viewer.get_all_objectives_data()
        with open(path, "w", encoding="cp1252") as f:
            f.write(header + "\n")
            for obj in objectives:
                fields = obj["fields"]
                row = ",".join(str(fields.get(col, "")) for col in MAPLOCATIONS_HEADER)
                f.write(row + "\n")

        QMessageBox.information(
            self, "Export Successful",
            f"Map locations exported to:\n{path}\n"
            f"({len(objectives)} objective(s))")
