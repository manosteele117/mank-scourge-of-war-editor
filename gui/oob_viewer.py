import sys
import os
import json
import logging
import traceback
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFileDialog, QLabel, QPushButton, QSplitter, QMessageBox, QTabWidget,
    QFrame, QDialog, QDialogButtonBox, QScrollArea,
)
from PySide6.QtGui import QColor, QPalette, QIcon
from PySide6.QtCore import Qt

from core.app_config import AppConfig
from core.oob_model import OOBData
from core.oob_validation import OOBValidator
from gui.oob_tree_view import OOBTreeWidget
from gui.oob_details_view import OOBDetailsWidget
from gui.layout_viewer.oob_visual_view import OOBVisualWidget
from gui.oob_shared_toolbar import OOBSharedToolbar
from gui.oob_map_view import OOBMapWidget, set_debug_formation_plot
from gui.oob_scenario_tab import ScenarioTab
from gui.oob_files_tab import FilesTab
from gui.oob_settings_tab import SettingsTab
from gui.oob_dropdowns import (
    load_rifles, load_artillery, load_gfx, load_unitglobal, load_gfxpack,
)


def apply_dark_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#121212"))
    palette.setColor(QPalette.WindowText, QColor("#ffffff"))
    palette.setColor(QPalette.Base, QColor("#1a1a1a"))
    palette.setColor(QPalette.AlternateBase, QColor("#181818"))
    palette.setColor(QPalette.ToolTipBase, QColor("#2a2a2a"))
    palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.Text, QColor("#ffffff"))
    palette.setColor(QPalette.Button, QColor("#1f1f1f"))
    palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor("#2979ff"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Link, QColor("#64b5f6"))

    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget {
            background: #121212;
            color: #ffffff;
        }

        QMainWindow, QSplitter, QFrame {
            background: #121212;
        }

        QPushButton {
            background-color: #1f1f1f;
            color: #ffffff;
            border: 1px solid #333333;
            padding: 6px 10px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #2d2d2d;
        }
        QPushButton:pressed {
            background-color: #383838;
        }

        QLabel {
            color: #ffffff;
        }

        QTableWidget, QTreeView {
            background-color: #2c2c2c;
            color: #ffffff;
            gridline-color: #ffffff;
        }

        QHeaderView::section {
            background-color: #1f1f1f;
            color: #ffffff;
            border: 1px solid #333333;
        }

        QFrame[frameShape="4"], QFrame[frameShape="5"] {
            color: #333333;
        }

        QTableWidget QTableCornerButton::section {
            background-color: #1f1f1f;
            border: 1px solid #333333;
        }

        QTabWidget::pane {
            border: 1px solid #333333;
            background-color: #121212;
        }

        QTabBar::tab {
            background-color: #1f1f1f;
            color: #ffffff;
            padding: 6px 14px;
            border: 1px solid #333333;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }

        QTabBar::tab:selected {
            background-color: #2d2d2d;
            color: #ffffff;
        }

        QTabBar::tab:!selected:hover {
            background-color: #2a2a2a;
        }

        QMenu {
            background-color: #1f1f1f;
            color: #ffffff;
            border: 1px solid #333333;
        }

        QMenu::item:selected {
            background-color: #3a3a3a;
            color: #ffffff;
        }

        QMenu::item:disabled {
            color: #5a5a5a;
            background-color: transparent;
        }

        QMenu::separator {
            height: 1px;
            background: #444444;
            margin: 4px 6px;
        }

        QGroupBox {
            font-weight: bold;
            border: 1px solid #444444;
            border-radius: 4px;
            margin-top: 12px;
            padding-top: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }

        QMessageBox {
            background-color: #121212;
            color: #ffffff;
        }

        QToolTip {
            background-color: #2a2a2a;
            color: #ffffff;
            border: 1px solid #444444;
        }
    """)


class OOBViewer(QMainWindow):
    """Main window orchestrator for the OOB editor."""

    _TEMPLATES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "units")

    def __init__(self, csv_path=None):
        super().__init__()

        self.setWindowTitle("Mank Scourge of War Editor - v0.1")
        self.resize(1400, 900)

        self.data = OOBData()
        self.validator = OOBValidator(self.data)
        self.config = AppConfig()

        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)

        self._init_controls()
        self._init_panels()
        self._init_tabs()
        self._wire_signals()
        self._restore_state()
        self._load_oob(csv_path)

    # ── UI construction ─────────────────────────────────────────────

    def _init_controls(self):
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        self.new_button = QPushButton("New OOB")
        self.new_button.clicked.connect(self.new_oob)
        controls_layout.addWidget(self.new_button)

        self.save_button = QPushButton("Save OOB")
        self.save_button.clicked.connect(self.save_csv_dialog)
        self.save_button.setEnabled(False)
        controls_layout.addWidget(self.save_button)

        self.save_scenario_button = QPushButton("Save Scenario")
        self.save_scenario_button.clicked.connect(self.save_scenario_dialog)
        self.save_scenario_button.setEnabled(False)
        controls_layout.addWidget(self.save_scenario_button)

        self.validate_button = QPushButton("Validate OOB")
        self.validate_button.clicked.connect(self.show_validation_report)
        self.validate_button.setEnabled(False)
        self._set_validation_state("unknown")
        controls_layout.addWidget(self.validate_button)

        self.filename_label = QLabel("")
        self.filename_label.setStyleSheet("color: #888; padding-left: 8px;")
        controls_layout.addWidget(self.filename_label)

        controls_layout.addStretch()

        controls_container = QWidget()
        controls_container.setLayout(controls_layout)
        controls_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_container.setMaximumHeight(60)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)

        self.left_splitter.addWidget(controls_container)
        self.main_splitter.addWidget(self.left_splitter)
        self.layout.addWidget(self.main_splitter, 1)

    def _init_panels(self):
        # Tree view
        self.tree = OOBTreeWidget(self.data)
        self.left_splitter.addWidget(self.tree)

        # Shared toolbar
        self.shared_toolbar = OOBSharedToolbar()
        self.shared_toolbar.setDisabled(True)
        self.left_splitter.addWidget(self.shared_toolbar)

        # Visual layout (hidden by default)
        self.visual = OOBVisualWidget(self.data)
        self.visual.setVisible(False)
        self.left_splitter.addWidget(self.visual)

        self.left_splitter.setStretchFactor(0, 0)
        self.left_splitter.setStretchFactor(1, 1)
        self.left_splitter.setStretchFactor(2, 0)
        self.left_splitter.setStretchFactor(3, 2)

    def _init_tabs(self):
        self.right_tab_widget = QTabWidget()

        self.files_tab = FilesTab()
        self.right_tab_widget.addTab(self.files_tab, "Files")

        # Map viewer
        self.map_viewer = OOBMapWidget(
            oob_data=self.data,
            map_ini=self.config.get_path("map-ini"),
            drills=self.config.get_path("drills"))
        self.right_tab_widget.addTab(self.map_viewer, "Map")

        # Details
        self.details = OOBDetailsWidget(self.data)
        self.right_tab_widget.addTab(self.details, "Details")

        # Scenario
        self.scenario = ScenarioTab(self.map_viewer)
        self.right_tab_widget.addTab(self.scenario, "Scenario")

        # Battlescript (placeholder)
        self.battlescript_tab = QWidget()
        self.right_tab_widget.addTab(self.battlescript_tab, "Battlescript")

        # Settings
        self.settings_tab = SettingsTab()
        self.right_tab_widget.addTab(self.settings_tab, "Settings")

        self.main_splitter.addWidget(self.right_tab_widget)
        self.main_splitter.setStretchFactor(0, 7)
        self.main_splitter.setStretchFactor(1, 1)

    def _wire_signals(self):
        # Tree → viewer
        self.tree.unit_selected.connect(self.on_unit_selected)
        self.tree.unit_deleted.connect(self.on_unit_deleted)
        self.tree.unit_moved.connect(self.on_unit_moved)
        self.tree.unit_added.connect(self._on_unit_added)

        # Shared toolbar
        self.shared_toolbar.regen_indices_requested.connect(self.action_regenerate_indices)
        self.shared_toolbar.regenerate_layout_requested.connect(
            lambda: self.visual._on_regenerate_view())
        self.shared_toolbar.toggle_layout_view_requested.connect(
            lambda checked: self._toggle_layout_view(checked))
        self.shared_toolbar.placement_filter_changed.connect(
            lambda filter_state: self.tree.set_placement_filter(filter_state))

        # Visual layout
        self.visual.unit_selected.connect(self.on_unit_selected)

        # Details
        self.details.detail_changed.connect(self._on_detail_edited)

        # Map viewer
        self.map_viewer.unit_selected.connect(self.on_unit_selected)
        self.map_viewer.unit_placed.connect(self._on_placement_changed)
        self.map_viewer.unit_removed.connect(self._on_placement_changed)
        self.map_viewer.map_loaded.connect(
            lambda path: self.config.set("paths", "map-ini", path))
        self.map_viewer.map_loaded.connect(
            lambda path: self.scenario.refresh_map_name())
        self.map_viewer.toggle_names_cb.toggled.connect(
            lambda checked: self.config.set("map-settings", "toggle_names", str(checked).lower()))
        self.map_viewer.name_level_slider.valueChanged.connect(
            lambda value: self.config.set("map-settings", "name_level", str(value)))

        # Files tab
        self.files_tab.file_changed.connect(self._on_file_changed)
        self.files_tab.template_toggled.connect(self._on_template_toggled)
        self.files_tab.reload_templates.connect(self._on_load_templates)
        self.files_tab.load_defaults_requested.connect(self._on_load_game_defaults)

        # Settings tab
        self.settings_tab.setting_changed.connect(self._on_setting_changed)

    def _restore_state(self):
        """Restore persisted config, templates, and dropdown data."""
        # Template files
        enabled_state = self._load_template_enabled_state()
        self.files_tab.scan_template_files(self._TEMPLATES_DIR, enabled_state)
        enabled_files = self.files_tab.get_enabled_template_files()
        self.tree.load_templates(enabled_files if enabled_files else None)
        self.tree.load_pools()

        # Dropdown data
        for key, loader in [
            ("rifles", load_rifles), ("artillery", load_artillery),
            ("gfx", load_gfx), ("unitglobal", load_unitglobal),
            ("gfxpack", load_gfxpack),
        ]:
            path = self.config.get_path(key)
            if path:
                loader(path)

        # Settings
        set_debug_formation_plot(self.config.get_bool("debug_formation_plot", False))
        debug_log = self.config.get_bool("debug_logging", False)
        logging.getLogger().setLevel(logging.WARNING)
        logging.getLogger("gui").setLevel(logging.DEBUG if debug_log else logging.WARNING)

        self.settings_tab.apply_settings(self.config.load_all())
        self.map_viewer.set_tile_scale(self.config.get_int("tile_scale", 512))
        self.map_viewer.set_units_per_yard(self.config.get_int("units_per_yard", 30))
        self.map_viewer.set_formation_plot_level(self.config.get_int("formation_plot_level", 5))

        # Map name display settings
        self.map_viewer.toggle_names_cb.setChecked(
            self.config.get_bool("toggle_names", False))
        self.map_viewer.name_level_slider.setValue(
            self.config.get_int("name_level", 3))

        # File path labels
        for key in ("oob", "drills", "rifles", "artillery", "gfx", "gfxpack", "unitglobal", "oobnames"):
            path = self.config.get_path(key)
            if path:
                self.files_tab.set_entry_path(key, path)

        if self.config.get_path("map-ini"):
            self.right_tab_widget.setCurrentWidget(self.map_viewer)

    def _load_oob(self, csv_path):
        """Load OOB from CLI arg, config, or skip."""
        cli_path = csv_path
        config_path = self.config.get_path("oob") or None
        self._oob_path = cli_path or config_path
        if self._oob_path:
            self.load_csv(self._oob_path)

    # ── File / scenario I/O ─────────────────────────────────────────

    def load_csv(self, path):
        try:
            self.data.load_csv(path)
            self.print_validation_report()
            self.map_viewer._clear_all_units()
            self.tree.populate()
            self.visual.populate()
            self.details.clear()
            self.scenario.refresh_intro_editor()
            self.save_button.setEnabled(True)
            self.save_scenario_button.setEnabled(True)
            self.validate_button.setEnabled(True)
            self.shared_toolbar.setDisabled(False)
            self.files_tab.set_entry_path("oob", path)
            self.filename_label.setText(os.path.basename(path))
        except Exception as e:
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to load OOB file:\n{path}\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def save_csv(self, path):
        try:
            self.data.save_csv(path)
            self.load_csv(path)
            QMessageBox.information(self, "Save Successful",
                                    f"OOB file saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error",
                                 f"Failed to save CSV to:\n{path}\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def new_oob(self):
        reply = QMessageBox.question(
            self, "New OOB",
            "This will discard any unsaved changes and load a blank template.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            template_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "templates", "headers", "oob_headers.csv")
            )
            self.load_csv(template_path)

    def save_csv_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save OOB CSV", "", "CSV Files (*.csv)")
        if path:
            self.save_csv(path)
            self.config.set("paths", "oob", path)

    def save_scenario_dialog(self):
        import re as _re
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Output")
        os.makedirs(base_dir, exist_ok=True)

        scenario_name = self.scenario.get_scenario_name().strip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if scenario_name:
            safe_name = _re.sub(r'[<>:"/\\|?*]', '_', scenario_name)
            scenario_dir = os.path.join(base_dir, f"{safe_name}_{timestamp}")
            inner_name = safe_name
        else:
            scenario_dir = os.path.join(base_dir, f"Generated_Scenario_{timestamp}")
            inner_name = f"Generated_Scenario_{timestamp}"

        if os.path.exists(scenario_dir):
            reply = QMessageBox.question(
                self, "Folder Exists",
                f"The folder already exists:\n{scenario_dir}\n\nOverwrite?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        map_name = self.map_viewer.map_ini_path.stem if self.map_viewer.map_ini_path else ""
        oob_filename = os.path.basename(self._oob_path) if self._oob_path else ""
        oob_names_path = self.config.get_path("oobnames") or None

        try:
            auto_fill_supply = self.config.get_bool("auto_fill_supply_on_save", True)
            self.data.save_scenario(
                scenario_dir, map_name, oob_filename,
                self.map_viewer.get_placed_units_data(),
                self.map_viewer.get_all_objectives_data(),
                intro_text=self.scenario.get_intro_text(),
                start_time=f"{self.scenario.get_start_time()[0]:02d}:{self.scenario.get_start_time()[1]:02d}:00",
                victory_conditions=self.scenario.get_victory_conditions(),
                oob_names_path=oob_names_path,
                scenario_name=scenario_name,
                inner_scenario_name=inner_name,
                auto_fill_supply=auto_fill_supply,
            )
            QMessageBox.information(self, "Save Successful",
                                    f"Scenario file saved to:\n{scenario_dir}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error",
                                 f"Failed to save scenario to:\n{scenario_dir}\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    # ── Validation ──────────────────────────────────────────────────

    def show_validation_report(self):
        issues = self.validator.validate()
        total = len(self.data.df) if self.data.df is not None else 0
        self._set_validation_state("fail" if issues else "pass")
        self._show_validation_dialog(issues, total)

    def print_validation_report(self):
        issues = self.validator.validate()
        total = len(self.data.df) if self.data.df is not None else 0
        self._set_validation_state("fail" if issues else "pass")
        if not issues:
            print(f"Validation passed: all checks passed across {total} units.")
            return
        print(f"Validation: {len(issues)} issue(s) found across {total} units.\n")
        grouped = {}
        for issue in issues:
            grouped.setdefault(issue.check_name, []).append(issue)
        for check_name, check_issues in grouped.items():
            print(f"--- {check_name} ({len(check_issues)} issue(s)) ---")
            for issue in check_issues:
                print(f"  Line {issue.line_number}: {issue.unit_name}")
                for line in issue.message.split("\n"):
                    print(f"    {line}")
            print()

    def _set_validation_state(self, state: str):
        if state == "fail":
            self.validate_button.setStyleSheet(
                "QPushButton { color: #f44336; font-weight: bold; }")
        elif state == "pass":
            self.validate_button.setStyleSheet(
                "QPushButton { color: #66bb6a; font-weight: bold; }")
        else:
            self.validate_button.setStyleSheet(
                "QPushButton { color: #ffffff; font-weight: normal; }")

    def _show_validation_dialog(self, issues, total: int):
        dialog = QDialog(self)
        dialog.setWindowTitle("OOB Validation Report")
        dialog.setMinimumSize(700, 500)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(8)

        if not issues:
            lbl = QLabel(f"All checks passed across {total} units.")
            lbl.setStyleSheet("color: #66bb6a; font-size: 14px; font-weight: bold; padding: 12px;")
            scroll_layout.addWidget(lbl)
        else:
            header = QLabel(f"{len(issues)} issue(s) found across {total} units.")
            header.setStyleSheet("color: #ffa726; font-size: 14px; font-weight: bold; padding: 4px 12px;")
            scroll_layout.addWidget(header)

            grouped = {}
            for issue in issues:
                grouped.setdefault(issue.check_name, []).append(issue)

            for check_name, check_issues in grouped.items():
                cat_label = QLabel(f"{check_name} ({len(check_issues)} issue(s))")
                cat_label.setStyleSheet("color: #90a4ae; font-size: 12px; font-weight: bold; padding-top: 8px;")
                scroll_layout.addWidget(cat_label)

                for issue in check_issues:
                    frame = QFrame()
                    frame.setStyleSheet(
                        "QFrame { background: #252525; border-left: 3px solid #ffa726; "
                        "border-radius: 2px; }")
                    frame_layout = QVBoxLayout(frame)
                    frame_layout.setContentsMargins(10, 8, 10, 8)
                    frame_layout.setSpacing(4)

                    title = QLabel(f"Line {issue.line_number}:  {issue.unit_name}")
                    title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
                    title.setWordWrap(True)
                    frame_layout.addWidget(title)

                    detail = QLabel(issue.message)
                    detail.setStyleSheet("color: #bbbbbb; font-size: 12px;")
                    detail.setWordWrap(True)
                    frame_layout.addWidget(detail)

                    scroll_layout.addWidget(frame)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.close)
        layout.addWidget(button_box)

        dialog.exec()

    # ── Selection propagation ───────────────────────────────────────

    def on_unit_selected(self, row_index: int):
        self.tree.blockSignals(True)
        try:
            self.tree.select_unit(row_index)
        finally:
            self.tree.blockSignals(False)
        self.details.populate(row_index)
        self.visual.highlight_unit(row_index)
        self.map_viewer.select_unit(row_index)

    def on_unit_deleted(self, num_deleted: int, deleted_row_indices: list):
        self._set_validation_state("unknown")
        self.visual.populate()
        self.map_viewer.remove_units_by_row_indices(deleted_row_indices)
        self.map_viewer.shift_placed_unit_indices(deleted_row_indices)
        self._on_placement_changed()

    def on_unit_moved(self, source_row_indices: list):
        self._set_validation_state("unknown")
        self.visual.populate()

    def _on_unit_added(self):
        self._set_validation_state("unknown")

    def _on_detail_edited(self, field_name: str = ""):
        self._set_validation_state("unknown")
        if field_name in ("NAME1", "Experience", "Head Count"):
            self.tree.populate_with_expansion()

    def _on_placement_changed(self):
        self.tree.set_placed_row_indices(self.map_viewer.placed_row_indices)

    # ── File change handlers ────────────────────────────────────────

    def _on_file_changed(self, config_key: str, file_path: str):
        self.config.set("paths", config_key, file_path)
        if config_key == "oob":
            self.load_csv(file_path)
        elif config_key == "drills":
            self.map_viewer._load_formations(file_path)
        elif config_key == "rifles":
            load_rifles(file_path)
        elif config_key == "artillery":
            load_artillery(file_path)
        elif config_key == "gfx":
            load_gfx(file_path)
            self.scenario.refresh_objectives()
        elif config_key == "unitglobal":
            load_unitglobal(file_path)
        elif config_key == "gfxpack":
            load_gfxpack(file_path)
        elif config_key == "map-ini":
            self.map_viewer.load_map_from_ini(file_path)
        elif config_key == "oobnames":
            pass  # path stored; loaded on demand

    def _on_setting_changed(self, key: str, value: str):
        if key == "debug_formation_plot":
            set_debug_formation_plot(value == "true")
        elif key == "debug_logging":
            logging.getLogger().setLevel(logging.WARNING)
            logging.getLogger("gui").setLevel(logging.DEBUG if value == "true" else logging.WARNING)
        elif key == "tile_scale":
            self.map_viewer.set_tile_scale(int(value))
        elif key == "units_per_yard":
            self.map_viewer.set_units_per_yard(int(value))
        elif key == "formation_plot_level":
            self.map_viewer.set_formation_plot_level(int(value))
        self.config.set("settings", key, value)

    # ── Templates ───────────────────────────────────────────────────

    def _on_load_templates(self):
        current_state = self.files_tab.get_template_enabled_state()
        self.files_tab.scan_template_files(self._TEMPLATES_DIR, current_state)
        enabled_files = self.files_tab.get_enabled_template_files()
        self.tree.load_templates(enabled_files if enabled_files else None)
        self.tree.load_pools()
        count = len(self.tree._templates)
        pool_count = len(self.data.templates._pool_cache)
        QMessageBox.information(self, "Reload Templates",
                                f"Loaded {count} template(s) and {pool_count} pool(s).")

    def _on_template_toggled(self, file_path: str, enabled: bool):
        self._save_template_enabled_state()
        enabled_files = self.files_tab.get_enabled_template_files()
        self.tree.load_templates(enabled_files if enabled_files else None)

    def _load_template_enabled_state(self) -> dict:
        raw = self.config.get("template_files_enabled", "")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    def _save_template_enabled_state(self):
        state = self.files_tab.get_template_enabled_state()
        self.config.set("paths", "template_files_enabled", json.dumps(state))

    # ── Misc ────────────────────────────────────────────────────────

    def _on_load_game_defaults(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Game Executable", "", "Executables (*.exe)")
        if not path:
            return
        exe_name = os.path.basename(path).lower()
        exe_dir = os.path.dirname(path)
        if exe_name == "sow64.exe":
            base_dir = os.path.join(exe_dir, "Base")
        elif exe_name == "sowgbx64.exe":
            base_dir = os.path.join(exe_dir, "BaseGB")
        elif os.path.isdir(os.path.join(exe_dir, "Base")):
            base_dir = os.path.join(exe_dir, "Base")
        elif os.path.isdir(os.path.join(exe_dir, "BaseGB")):
            base_dir = os.path.join(exe_dir, "BaseGB")
        else:
            QMessageBox.warning(self, "Load Game Defaults",
                                f"Could not determine game data directory from:\n{path}")
            return
        self.files_tab.apply_game_defaults(base_dir)

    def _toggle_layout_view(self, visible: bool):
        self.visual.setVisible(visible)
        self.shared_toolbar.toggle_layout_view_button.setText(
            "Hide Layout" if visible else "Show Layout")

    def action_regenerate_indices(self):
        reply = QMessageBox.question(
            self, "Regenerate Hierarchy Indices",
            "Regenerate all hierarchy indices sequentially under each parent?\n\n"
            "This will renumber all units 1, 2, 3... under each parent.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.data.regenerate_hierarchy_indices()
            self.tree.populate_with_expansion()
            self.visual.populate()
            QMessageBox.information(self, "Regenerate Complete",
                                    "Hierarchy indices have been regenerated.")
        except Exception as e:
            QMessageBox.critical(self, "Regenerate Error",
                                 f"Failed to regenerate hierarchy indices:\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")


def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "icons", "mank_big_logo_noflag.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    csv_path = sys.argv[1] if len(sys.argv) > 1 else None

    viewer = OOBViewer(csv_path)
    viewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
