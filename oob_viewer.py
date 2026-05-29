import sys
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStyledItemDelegate,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QFileDialog,
    QLabel,
    QPushButton,
    QSplitter,
    QMessageBox,
    QTabWidget,
)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt


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

        QTableWidget QTableCornerButton::section {
            background-color: #1f1f1f;
            border: 1px solid #333333;
        }

        QMenu {
            background-color: #1f1f1f;
            color: #ffffff;
            border: 1px solid #333333;
        }

        QMessageBox {
            background-color: #121212;
            color: #ffffff;
        }
    """)

from oob_model import OOBData
from oob_validation import OOBValidator
from oob_tree_view import OOBTreeWidget
from oob_details_view import OOBDetailsWidget
from oob_visual_view import OOBVisualWidget
from oob_map_view import OOBMapWidget



class OOBViewer(QMainWindow):
    def __init__(self, csv_path=None):
        super().__init__()

        self.setWindowTitle("Order of Battle Viewer")
        self.resize(1400, 900)

        # Initialize data model
        self.data = OOBData()
        self.validator = OOBValidator(self.data)

        self.central = QWidget()
        self.setCentralWidget(self.central)

        self.layout = QVBoxLayout(self.central)

        # Top controls
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

        self.status_label = QLabel("No file loaded")
        controls_layout.addWidget(self.status_label)

        controls_layout.addStretch()

        controls_container = QWidget()
        controls_container.setLayout(controls_layout)
        controls_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_container.setMaximumHeight(60)

        self.layout.addWidget(controls_container, 0)

        # Main content split left/right with tree and visual stacked vertically on the left,
        # and details shown on the right.
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)

        # Tree view
        self.tree = OOBTreeWidget(self.data)
        self.tree.unit_selected.connect(self.on_unit_selected)
        self.tree.unit_deleted.connect(self.on_unit_deleted)

        # Visual view (formations visualization)
        self.visual = OOBVisualWidget(self.data)
        self.visual.unit_selected.connect(self.on_unit_selected)

        # Details view
        self.details = OOBDetailsWidget(self.data)

        # Map view
        self.map_viewer = OOBMapWidget()
        
        # Wire tree selection to map for unit placement
        self.tree.unit_selected.connect(self.on_tree_unit_selected)

        # Tab widget to switch between details and map views
        self.right_tab_widget = QTabWidget()
        self.right_tab_widget.addTab(self.details, "Details")
        self.right_tab_widget.addTab(self.map_viewer, "Map")

        self.left_splitter.addWidget(self.tree)
        self.left_splitter.addWidget(self.visual)
        self.left_splitter.setStretchFactor(0, 1)  # tree
        self.left_splitter.setStretchFactor(1, 2)  # visual

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_tab_widget)
        self.main_splitter.setStretchFactor(0, 7)  # left stack
        self.main_splitter.setStretchFactor(1, 1)  # details/map tabs

        self.layout.addWidget(self.main_splitter, 1)

        if csv_path:
            self.load_csv(csv_path)

    def load_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open OOB CSV",
            "",
            "CSV Files (*.csv)"
        )

        if path:
            self.load_csv(path)

    def save_csv_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save OOB CSV",
            "",
            "CSV Files (*.csv)"
        )

        if path:
            self.save_csv(path)

    def save_scenario_dialog(self):
        MAP_NAME = "Waterloo"  # Todo
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Output")
        os.makedirs(base_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scenario_dir = os.path.join(base_dir, f"Generated_Scenario_{timestamp}")

        # Collect placed units data from the map widget
        placed_units = self.map_viewer.get_placed_units_data()

        try:
            self.data.save_scenario(scenario_dir, MAP_NAME, self.status_label.text(), placed_units)
            QMessageBox.information(
                self,
                "Save Successful",
                f"Scenario file saved to:\n{scenario_dir}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save scenario:\n{str(e)}"
            )

    def load_csv(self, path):
        try:
            self.data.load_csv(path)

            # Validate unit stats and print warnings to console
            warnings = self.validator.validate_unit_stats()
            if warnings:
                print("OOB Validation Warnings:")
                for warning in warnings:
                    print(f"  {warning}\n")

            # Populate tree and visual views, clear details
            self.tree.populate()
            self.visual.populate()
            self.details.clear()

            self.status_label.setText(path)
            self.save_button.setEnabled(True)
            self.save_scenario_button.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Error",
                str(e)
            )

    def save_csv(self, path):
        try:
            self.data.save_csv(path)
            QMessageBox.information(
                self,
                "Save Successful",
                f"OOB file saved to:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save CSV:\n{str(e)}"
            )

    def on_unit_selected(self, row_index: int):
        """Handle unit selection from tree or visual view."""
        self.tree.select_unit(row_index)
        self.details.populate(row_index)
        self.visual.highlight_unit(row_index)
    
    def on_tree_unit_selected(self, row_index: int):
        """Handle unit selection specifically from tree for map placement."""
        # Get unit data
        row = self.data.get_row(row_index)
        unit_name = str(row.get("NAME1", "Unknown"))
        side = int(row.get("SIDE 1", 1))
        level = self.data.get_level_from_hierarchy(row)
        formation = str(row.get("Formation", ""))
        
        # Send to map widget for placement mode
        self.map_viewer.set_pending_unit(row_index, unit_name, side, level, formation)

    def on_unit_deleted(self, num_deleted: int):
        """Handle unit deletion from tree."""
        # Regenerate the visual view after deletion
        self.visual.populate()


def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    # Optional: pass CSV path as command line argument
    csv_path = None

    if len(sys.argv) > 1:
        csv_path = sys.argv[1]

    viewer = OOBViewer(csv_path)
    viewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
