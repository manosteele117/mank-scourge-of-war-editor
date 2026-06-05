import sys
import os
import configparser
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFileDialog, QLabel, QPushButton, QSplitter, QMessageBox, QTabWidget,
    QFrame,
)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt

from core.oob_model import OOBData
from core.oob_validation import OOBValidator
from gui.oob_tree_view import OOBTreeWidget
from gui.oob_details_view import OOBDetailsWidget
from gui.oob_visual_view import OOBVisualWidget
from gui.oob_map_view import OOBMapWidget
from gui.oob_scenario_tab import ScenarioTab


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

        self.load_button = QPushButton("Load OOB")
        self.load_button.clicked.connect(self.load_csv_dialog)
        controls_layout.addWidget(self.load_button)

        self.save_button = QPushButton("Save OOB")
        self.save_button.clicked.connect(self.save_csv_dialog)
        self.save_button.setEnabled(False)
        controls_layout.addWidget(self.save_button)

        self.save_scenario_button = QPushButton("Save Scenario")
        self.save_scenario_button.clicked.connect(self.save_scenario_dialog)
        self.save_scenario_button.setEnabled(False)
        controls_layout.addWidget(self.save_scenario_button)

        self.regen_button = QPushButton("Regen Indices")
        self.regen_button.clicked.connect(self.action_regenerate_indices)
        self.regen_button.setEnabled(False)
        self.regen_button.setToolTip("Regenerate hierarchy indices sequentially under each parent")
        controls_layout.addWidget(self.regen_button)

        self.status_label = QLabel("No file loaded")
        controls_layout.addWidget(self.status_label)

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
        self.tree.zoom_to_unit_requested.connect(self.on_zoom_to_unit)

        self.visual = OOBVisualWidget(self.data)
        self.visual.unit_selected.connect(self.on_unit_selected)

        self.details = OOBDetailsWidget(self.data)

        self.config = self._load_config()
        self.map_viewer = OOBMapWidget(
            oob_data=self.data,
            map_ini=self.config.get("map-ini"),
            drills=self.config.get("drills"))

        self.map_viewer.unit_selected.connect(self.on_unit_selected)

        self.scenario = ScenarioTab(self.map_viewer)

        vseparator = QFrame()
        vseparator.setFrameShape(QFrame.Shape.VLine)
        vseparator.setFrameShadow(QFrame.Shadow.Sunken)
        controls_layout.addWidget(vseparator)

        self.load_formations_button = QPushButton("Load Formations")
        self.load_formations_button.clicked.connect(
            lambda: self.map_viewer.load_formations_dialog())
        controls_layout.addWidget(self.load_formations_button)

        self.drills_label = QLabel("No drills file loaded")
        controls_layout.addWidget(self.drills_label)

        self.map_viewer.drills_loaded.connect(
            lambda path: self.drills_label.setText(f"Drills: {path}"))
        if self.map_viewer.drills_path:
            self.drills_label.setText(f"Drills: {self.map_viewer.drills_path}")

        self.right_tab_widget = QTabWidget()
        self.right_tab_widget.addTab(self.details, "Details")
        self.right_tab_widget.addTab(self.map_viewer, "Map")
        self.right_tab_widget.addTab(self.scenario, "Scenario")

        self.left_splitter.addWidget(self.tree)
        self.left_splitter.addWidget(self.visual)
        self.left_splitter.setStretchFactor(0, 1)
        self.left_splitter.setStretchFactor(1, 2)

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_tab_widget)
        self.main_splitter.setStretchFactor(0, 7)
        self.main_splitter.setStretchFactor(1, 1)

        self.layout.addWidget(self.main_splitter, 1)
        self.load_csv(csv_path)

    def _load_config(self) -> dict:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "app_config.ini")
        parser = configparser.ConfigParser()
        if os.path.exists(config_path):
            parser.read(config_path)
        return {
            "map-ini": parser.get("paths", "map-ini", fallback=""),
            "drills": parser.get("paths", "drills", fallback=""),
        }

    def load_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open OOB CSV", "", "CSV Files (*.csv)")
        if path:
            self.load_csv(path)

    def save_csv_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save OOB CSV", "", "CSV Files (*.csv)")
        if path:
            self.save_csv(path)

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

        oob_status_path = self.status_label.text()
        oob_filename = os.path.basename(oob_status_path) if oob_status_path else ""

        try:
            self.data.save_scenario(scenario_dir, map_name, oob_filename, placed_units)
            QMessageBox.information(
                self, "Save Successful",
                f"Scenario file saved to:\n{scenario_dir}")
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save scenario:\n{str(e)}")

    def load_csv(self, path):
        try:
            self.data.load_csv(path)

            warnings = self.validator.validate_unit_stats()
            if warnings:
                print("OOB Validation Warnings:")
                for warning in warnings:
                    print(f"  {warning}\n")

            self.map_viewer._clear_all_units()
            self.tree.populate()
            self.visual.populate()
            self.details.clear()

            self.status_label.setText(path)
            self.save_button.setEnabled(True)
            self.save_scenario_button.setEnabled(True)
            self.regen_button.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def save_csv(self, path):
        try:
            self.data.save_csv(path)
            QMessageBox.information(
                self, "Save Successful",
                f"OOB file saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save CSV:\n{str(e)}")

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
        self.visual.populate()
        self.map_viewer.remove_units_by_row_indices(deleted_row_indices)

    def on_zoom_to_unit(self, row_index: int):
        self.map_viewer.on_unit_double_clicked(row_index)

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
            self.tree.populate()
            self.visual.populate()
            QMessageBox.information(self, "Regenerate Complete",
                                    "Hierarchy indices have been regenerated.")
        except Exception as e:
            QMessageBox.critical(self, "Regenerate Error",
                                 f"Failed to regenerate indices:\n{str(e)}")


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
