import os
from pathlib import Path
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QAbstractItemView, QFrame, QComboBox, QGroupBox, QScrollArea,
    QSpinBox, QLineEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from gui.oob_dropdowns import get_gfx_options
from gui.oob_rich_text_editor import RichTextEditor


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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(16)

        # ── Objectives section ─────────────────────────────────────
        objectives_group = self._create_objectives_section()
        scroll_layout.addWidget(objectives_group, 0)

        # ── Settings + Intro side by side ──────────────────────────
        settings_intro_row = QHBoxLayout()
        settings_intro_row.setSpacing(12)

        settings_group = self._create_settings_section()
        settings_group.setSizePolicy(
            settings_group.sizePolicy().horizontalPolicy(),
            QSizePolicy.Expanding,
        )
        settings_intro_row.addWidget(settings_group, 1)

        intro_group = self._create_intro_section()
        intro_group.setSizePolicy(
            intro_group.sizePolicy().horizontalPolicy(),
            QSizePolicy.Expanding,
        )
        settings_intro_row.addWidget(intro_group, 2)

        scroll_layout.addLayout(settings_intro_row, 1)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Refresh map name on first show
        self.refresh_map_name()

    # ── Sections ──────────────────────────────────────────────────

    def _create_objectives_section(self) -> QGroupBox:
        group = QGroupBox("Objectives")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.export_btn = QPushButton("Export Map Locations")
        self.export_btn.clicked.connect(self._on_export)
        layout.addWidget(self.export_btn)

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

        return group

    def _create_settings_section(self) -> QGroupBox:
        group = QGroupBox("Scenario Settings")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Scenario Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Scenario Name:"))
        self.scenario_name_edit = QLineEdit()
        self.scenario_name_edit.setPlaceholderText("Enter scenario name...")
        name_row.addWidget(self.scenario_name_edit, 1)
        layout.addLayout(name_row)

        # Map (read-only)
        map_row = QHBoxLayout()
        map_row.addWidget(QLabel("Map:"))
        self.map_name_edit = QLineEdit()
        self.map_name_edit.setReadOnly(True)
        self.map_name_edit.setEnabled(False)
        self.map_name_edit.setStyleSheet("""
            QLineEdit:disabled {
                color: #888888;
                background-color: #1a1a1a;
            }
        """)
        map_row.addWidget(self.map_name_edit, 1)
        layout.addLayout(map_row)

        # Start Time
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Start Time:"))
        self.hour_spin = QSpinBox()
        self.hour_spin.setRange(0, 23)
        self.hour_spin.setValue(8)
        self.hour_spin.setPrefix("")
        self.hour_spin.setSpecialValueText("00")
        self.hour_spin.setFixedWidth(55)
        time_row.addWidget(self.hour_spin)
        time_row.addWidget(QLabel(":"))
        self.minute_spin = QSpinBox()
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setValue(0)
        self.minute_spin.setPrefix("")
        self.minute_spin.setSpecialValueText("00")
        self.minute_spin.setFixedWidth(55)
        time_row.addWidget(self.minute_spin)
        time_row.addStretch(1)
        layout.addLayout(time_row)

        # Type
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["MP", "SP", "BP"])
        self.type_combo.setCurrentText("BP")
        self.type_combo.setFixedWidth(80)
        type_row.addWidget(self.type_combo)
        type_row.addStretch(1)
        layout.addLayout(type_row)

        # Victory Conditions (indented sub-group)
        vc_group = QGroupBox("Victory Conditions")
        vc_group.setStyleSheet("QGroupBox { margin-left: 20px; }")
        vc_group.setSizePolicy(
            vc_group.sizePolicy().horizontalPolicy(),
            QSizePolicy.Fixed,
        )
        vc_layout = QVBoxLayout(vc_group)
        vc_layout.setSpacing(6)

        self.victory_edits: dict[str, QLineEdit] = {}
        vc_defaults = {
            "Major Victory": "2000",
            "Minor Victory": "1500",
            "Draw": "1000",
            "Minor Defeat": "500",
            "Major Defeat": "0",
        }
        for label_text in ["Major Victory", "Minor Victory", "Draw",
                           "Minor Defeat", "Major Defeat"]:
            row = QHBoxLayout()
            lbl = QLabel(f"{label_text}:")
            lbl.setFixedWidth(110)
            row.addWidget(lbl)
            edit = QLineEdit()
            edit.setText(vc_defaults[label_text])
            edit.setFixedWidth(100)
            row.addWidget(edit)
            row.addStretch(1)
            vc_layout.addLayout(row)
            self.victory_edits[label_text] = edit

        layout.addWidget(vc_group)

        layout.addStretch()

        return group

    def _create_intro_section(self) -> QGroupBox:
        group = QGroupBox("Scenario Intro")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.intro_editor = RichTextEditor()
        layout.addWidget(self.intro_editor)

        self.intro_editor._on_insert_details()

        return group

    # ── Map name ──────────────────────────────────────────────────

    def refresh_map_name(self):
        if self.map_viewer.map_ini_path:
            map_name = Path(self.map_viewer.map_ini_path).stem
            self.map_name_edit.setText(map_name)
        else:
            self.map_name_edit.setText("No map loaded")

    # ── Getters ───────────────────────────────────────────────────

    def get_intro_text(self) -> str:
        return self.intro_editor.get_game_text()

    def get_scenario_name(self) -> str:
        return self.scenario_name_edit.text().strip()

    def get_start_time(self) -> tuple[int, int]:
        return (self.hour_spin.value(), self.minute_spin.value())

    def get_type(self) -> str:
        return self.type_combo.currentText()

    def get_victory_conditions(self) -> dict[str, str]:
        return {label: edit.text().strip()
                for label, edit in self.victory_edits.items()}

    # ── Intro text editor ────────────────────────────────────────

    def refresh_intro_editor(self):
        """Repopulate the intro editor with current scenario details."""
        self.intro_editor._on_insert_details()

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
