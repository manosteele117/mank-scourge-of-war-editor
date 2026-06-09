import sys
import os
import configparser
import traceback
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFileDialog, QLabel, QPushButton, QSplitter, QMessageBox, QTabWidget,
    QFrame, QDialog, QDialogButtonBox, QScrollArea,
)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt

from core.oob_model import OOBData
from core.oob_validation import OOBValidator
from gui.oob_tree_view import OOBTreeWidget
from gui.oob_details_view import OOBDetailsWidget
from gui.oob_visual_view import OOBVisualWidget
from gui.oob_shared_toolbar import OOBSharedToolbar
from gui.oob_map_view import OOBMapWidget
from gui.oob_scenario_tab import ScenarioTab
from gui.oob_files_tab import FilesTab
from gui.oob_dropdowns import (
    load_rifles, load_artillery, load_gfx, load_unitglobal, load_gfxpack,
)


def apply_dark_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#121212"))
    palette.setColor(QPalette.WindowText, QColor("#ffffff"))
    palette.setColor(QPalette.Base, QColor("#1a1a1a"))
    palette.setColor(QPalette.AlternateBase, QColor("#181818"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
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

        QMessageBox {
            background-color: #121212;
            color: #ffffff;
        }
    """)


class OOBViewer(QMainWindow):
    def __init__(self, csv_path=None):
        super().__init__()

        self.setWindowTitle("Order of Battle Viewer")
        self.resize(1400, 900)

        self.data = OOBData()
        self.validator = OOBValidator(self.data)
        self._propagating_selection: bool = False

        self.central = QWidget()
        self.setCentralWidget(self.central)

        self.layout = QVBoxLayout(self.central)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

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

        controls_layout.addStretch()

        controls_container = QWidget()
        controls_container.setLayout(controls_layout)
        controls_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_container.setMaximumHeight(60)

        self.layout.addWidget(controls_container, 0)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)

        self.tree = OOBTreeWidget(self.data)
        self.tree.unit_selected.connect(self.on_unit_selected)
        self.tree.unit_deleted.connect(self.on_unit_deleted)
        self.tree.unit_moved.connect(self.on_unit_moved)
        self.tree.unit_added.connect(self._on_unit_added)

        self.shared_toolbar = OOBSharedToolbar()
        self.shared_toolbar.regen_indices_requested.connect(self.action_regenerate_indices)
        self.shared_toolbar.regenerate_layout_requested.connect(
            lambda: self.visual._on_regenerate_view())
        self.shared_toolbar.toggle_layout_view_requested.connect(
            lambda checked: self._toggle_layout_view(checked))
        self.shared_toolbar.placement_filter_changed.connect(
            lambda filter_state: self.tree.set_placement_filter(filter_state))
        self.shared_toolbar.setDisabled(True)

        self.visual = OOBVisualWidget(self.data)
        self.visual.unit_selected.connect(self.on_unit_selected)
        self.visual.setVisible(False)

        self.details = OOBDetailsWidget(self.data)
        self.details.detail_changed.connect(self._on_detail_edited)

        self.config = self._load_config()

        self.map_viewer = OOBMapWidget(
            oob_data=self.data,
            map_ini=self.config.get("map-ini"),
            drills=self.config.get("drills"))

        self.map_viewer.unit_selected.connect(self.on_unit_selected)
        self.map_viewer.unit_placed.connect(self._on_placement_changed)
        self.map_viewer.unit_removed.connect(self._on_placement_changed)
        self.map_viewer.map_loaded.connect(
            lambda path: self._save_config(**{"map-ini": path}))

        self.scenario = ScenarioTab(self.map_viewer)

        self.right_tab_widget = QTabWidget()
        self.right_tab_widget.addTab(self.details, "Details")
        self.right_tab_widget.addTab(self.map_viewer, "Map")
        self.right_tab_widget.addTab(self.scenario, "Scenario")

        self.files_tab = FilesTab()
        self.files_tab.file_changed.connect(self._on_file_changed)
        self.files_tab.template_toggled.connect(self._on_template_toggled)
        self.files_tab.reload_templates.connect(self._on_load_templates)
        self.files_tab.load_defaults_requested.connect(self._on_load_game_defaults)
        self.right_tab_widget.addTab(self.files_tab, "Files/Settings")

        # Scan template files and load with enabled state
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates", "units")
        enabled_state = self._load_template_enabled_state()
        self.files_tab.scan_template_files(templates_dir, enabled_state)
        enabled_files = self.files_tab.get_enabled_template_files()
        self.tree.load_templates(enabled_files if enabled_files else None)
        self.tree.load_pools()

        # Load rifles and artillery for dropdown options
        if self.config.get("rifles"):
            load_rifles(self.config["rifles"])
        if self.config.get("artillery"):
            load_artillery(self.config["artillery"])
        if self.config.get("gfx"):
            load_gfx(self.config["gfx"])
        if self.config.get("unitglobal"):
            load_unitglobal(self.config["unitglobal"])
        if self.config.get("gfxpack"):
            load_gfxpack(self.config["gfxpack"])

        if self.config.get("map-ini"):
            self.right_tab_widget.setCurrentWidget(self.map_viewer)

        self.left_splitter.addWidget(self.tree)
        self.left_splitter.addWidget(self.shared_toolbar)
        self.left_splitter.addWidget(self.visual)
        self.left_splitter.setStretchFactor(0, 1)
        self.left_splitter.setStretchFactor(1, 0)
        self.left_splitter.setStretchFactor(2, 2)

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_tab_widget)
        self.main_splitter.setStretchFactor(0, 7)
        self.main_splitter.setStretchFactor(1, 1)

        self.layout.addWidget(self.main_splitter, 1)

        # Initialize FilesTab with saved config values
        for key in ("oob", "drills", "rifles", "artillery", "gfx",
                    "gfxpack", "unitglobal"):
            path = self.config.get(key)
            if path:
                self.files_tab.set_entry_path(key, path)

        # Resolve OOB path: command line > config > None
        cli_path = csv_path if csv_path else None
        config_path = self.config.get("oob") or None
        self._oob_path = cli_path if cli_path else config_path
        if self._oob_path:
            self.load_csv(self._oob_path)

    def _load_config(self) -> dict:
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config")
        config_path = os.path.join(config_dir, "app_config.ini")
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        if not os.path.exists(config_path):
            parser = configparser.ConfigParser()
            parser.add_section("paths")
            for key in ("map-ini", "drills", "oob", "rifles", "artillery",
                        "gfx", "gfxpack", "unitglobal"):
                parser.set("paths", key, "")
            with open(config_path, "w") as f:
                parser.write(f)
        parser = configparser.ConfigParser()
        parser.read(config_path)
        return {
            key: parser.get("paths", key, fallback="")
            for key in ("map-ini", "drills", "oob", "rifles", "artillery",
                        "gfx", "gfxpack", "unitglobal",
                        "template_files_enabled")
        }

    def _save_config(self, **kwargs):
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config")
        config_path = os.path.join(config_dir, "app_config.ini")
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        parser = configparser.ConfigParser()
        parser.read(config_path)
        if "paths" not in parser:
            parser.add_section("paths")
        for key, val in kwargs.items():
            parser.set("paths", key, val)
        with open(config_path, "w") as f:
            parser.write(f)

    def load_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open OOB CSV", "", "CSV Files (*.csv)")
        if path:
            self.load_csv(path)
            self._save_config(oob=path)

    def _on_file_changed(self, config_key: str, file_path: str):
        self._save_config(**{config_key: file_path})
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

    def save_csv_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save OOB CSV", "", "CSV Files (*.csv)")
        if path:
            self.save_csv(path)
            self._save_config(oob=path)

    def save_scenario_dialog(self):
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Output")
        os.makedirs(base_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scenario_dir = os.path.join(base_dir, f"Generated_Scenario_{timestamp}")

        placed_units = self.map_viewer.get_placed_units_data()

        if self.map_viewer.map_ini_path is not None:
            map_name = self.map_viewer.map_ini_path.stem
        else:
            map_name = ""

        oob_filename = os.path.basename(self._oob_path) if self._oob_path else ""

        objectives = self.map_viewer.get_all_objectives_data()

        try:
            self.data.save_scenario(scenario_dir, map_name, oob_filename, placed_units, objectives)
            QMessageBox.information(
                self, "Save Successful",
                f"Scenario file saved to:\n{scenario_dir}")
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save scenario to:\n{scenario_dir}\n\n"
                f"Error: {type(e).__name__}: {str(e)}\n\n"
                f"Stack trace:\n{traceback.format_exc()}")

    def show_validation_report(self):
        issues = self.validator.validate()
        total = len(self.data.df) if self.data.df is not None else 0
        if issues:
            self._set_validation_state("fail")
        else:
            self._set_validation_state("pass")
        self._show_validation_dialog(issues, total)

    def print_validation_report(self):
        issues = self.validator.validate()
        total = len(self.data.df) if self.data.df is not None else 0
        if issues:
            self._set_validation_state("fail")
        else:
            self._set_validation_state("pass")
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
            self.validate_button.setText("Validate OOB")
            self.validate_button.setStyleSheet(
                "QPushButton { color: #f44336; font-weight: bold; }")
        elif state == "pass":
            self.validate_button.setText("Validate OOB")
            self.validate_button.setStyleSheet(
                "QPushButton { color: #66bb6a; font-weight: bold; }")
        else:
            self.validate_button.setText("Validate OOB")
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

    def load_csv(self, path):
        try:
            self.data.load_csv(path)

            self.print_validation_report()

            self.map_viewer._clear_all_units()
            self.tree.populate()
            self.visual.populate()
            self.details.clear()

            self.save_button.setEnabled(True)
            self.save_scenario_button.setEnabled(True)
            self.validate_button.setEnabled(True)
            self.shared_toolbar.setDisabled(False)
            self.files_tab.set_entry_path("oob", path)

        except Exception as e:
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to load OOB file:\n{path}\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def save_csv(self, path):
        try:
            self.data.save_csv(path)
            self.load_csv(path)
            QMessageBox.information(
                self, "Save Successful",
                f"OOB file saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save CSV to:\n{path}\n\n"
                f"Error: {type(e).__name__}: {str(e)}\n\n"
                f"Stack trace:\n{traceback.format_exc()}")

    def on_unit_selected(self, row_index: int):
        if self._propagating_selection:
            return
        self._propagating_selection = True
        try:
            # Skip tree.select_unit() when the tree itself initiated the selection
            # — it already has the right selection state and we must not clear it.
            if not self.tree._selection_from_tree:
                self.tree.select_unit(row_index)
            self.details.populate(row_index)
            self.visual.highlight_unit(row_index)
            self.map_viewer.select_unit(row_index)
        finally:
            self._propagating_selection = False
            self.tree._selection_from_tree = False

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
        if field_name in ("Experience", "Head Count"):
            self.tree.populate_with_expansion()

    def _on_load_templates(self):
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates", "units")
        current_state = self.files_tab.get_template_enabled_state()
        self.files_tab.scan_template_files(templates_dir, current_state)
        enabled_files = self.files_tab.get_enabled_template_files()
        self.tree.load_templates(enabled_files if enabled_files else None)
        self.tree.load_pools()
        count = len(self.tree._templates)
        pool_count = len(self.data._pool_cache)
        QMessageBox.information(self, "Reload Templates",
                                f"Loaded {count} template(s) and {pool_count} pool(s).")

    def _on_template_toggled(self, file_path: str, enabled: bool):
        self._save_template_enabled_state()
        enabled_files = self.files_tab.get_enabled_template_files()
        self.tree.load_templates(enabled_files if enabled_files else None)

    def _load_template_enabled_state(self) -> dict:
        import json
        raw = self.config.get("template_files_enabled", "")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    def _save_template_enabled_state(self):
        import json
        state = self.files_tab.get_template_enabled_state()
        self._save_config(template_files_enabled=json.dumps(state))

    def on_zoom_to_unit(self, row_index: int):
        self.map_viewer.on_unit_double_clicked(row_index)

    def _toggle_layout_view(self, visible: bool):
        self.visual.setVisible(visible)
        self.shared_toolbar.toggle_layout_view_button.setText(
            "Hide Layout" if visible else "Show Layout")

    def _on_placement_changed(self):
        self.tree.set_placed_row_indices(self.map_viewer.placed_row_indices)

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

    csv_path = None
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]

    viewer = OOBViewer(csv_path)
    viewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
