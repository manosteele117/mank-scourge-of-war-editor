from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox,
    QPushButton, QFrame, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QGridLayout, QWidget,
)
from PySide6.QtCore import Qt
from constants import LEVEL_NAMES, apply_side_colors_to_item

RESULT_BACK = 0
RESULT_CONFIRM = 1
RESULT_REGENERATE = 2

BRANCHES = [("INF", "Infantry"), ("CAV", "Cavalry"), ("ART", "Artillery")]

_BRANCH_UNIT_NAMES = {
    5: {"INF": "Brigades", "CAV": "Brigades", "ART": "Batteries"},
    6: {"INF": "Regiments", "CAV": "Squadrons", "ART": "Guns"},
}

_BRANCH_CLASS_KEY = {"INF": "1", "CAV": "2", "ART": "3"}


class _LevelRow(QFrame):
    """A single row: min spinbox, max spinbox, template dropdown for one level."""

    def __init__(self, level: int, templates: list[dict], parent=None):
        super().__init__(parent)
        self.level = level
        self.setFrameShape(QFrame.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        name = LEVEL_NAMES[level - 1] if level <= len(LEVEL_NAMES) else f"Level {level}"
        label = QLabel(f"Lvl {level} {name}s:")
        label.setFixedWidth(140)
        layout.addWidget(label)

        self.min_spin = QSpinBox()
        self.min_spin.setRange(0, 99)
        self.min_spin.setValue(0)
        self.min_spin.setPrefix("Min: ")
        self.min_spin.setFixedWidth(100)
        layout.addWidget(self.min_spin)

        self.max_spin = QSpinBox()
        self.max_spin.setRange(0, 99)
        self.max_spin.setValue(0)
        self.max_spin.setPrefix("Max: ")
        self.max_spin.setFixedWidth(100)
        layout.addWidget(self.max_spin)

        self.template_combo = QComboBox()
        self.template_combo.setEditable(False)
        level_templates = [t for t in templates if t["level"] == level]
        for t in sorted(level_templates, key=lambda x: x["name"]):
            self.template_combo.addItem(t["name"], t)
        if not level_templates:
            self.template_combo.addItem("(no templates)", None)
            self.template_combo.setEnabled(False)
        layout.addWidget(self.template_combo, 1)

        # Link min/max
        self.min_spin.valueChanged.connect(self._on_min_changed)
        self.max_spin.valueChanged.connect(self._on_max_changed)

    def _on_min_changed(self, val: int):
        if val > self.max_spin.value():
            self.max_spin.setValue(val)

    def _on_max_changed(self, val: int):
        if val < self.min_spin.value():
            self.min_spin.setValue(val)

    def get_config(self) -> list[dict]:
        template = self.template_combo.currentData()
        return [{
            "level": self.level,
            "branch": None,
            "min": self.min_spin.value(),
            "max": self.max_spin.value(),
            "template": template,
        }]


class _BranchColumn(QWidget):
    """Min/max spinboxes + template dropdown for one branch within a level."""

    def __init__(self, level: int, branch_code: str, templates: list[dict],
                 parent=None):
        super().__init__(parent)
        self.level = level
        self.branch = branch_code

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Min / Max on first line
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self.min_spin = QSpinBox()
        self.min_spin.setRange(0, 99)
        self.min_spin.setValue(0)
        self.min_spin.setPrefix("Min: ")
        self.min_spin.setFixedWidth(80)
        row1.addWidget(self.min_spin)

        self.max_spin = QSpinBox()
        self.max_spin.setRange(0, 99)
        self.max_spin.setValue(0)
        self.max_spin.setPrefix("Max: ")
        self.max_spin.setFixedWidth(80)
        row1.addWidget(self.max_spin)

        layout.addLayout(row1)

        # Template dropdown on second line
        self.template_combo = QComboBox()
        self.template_combo.setEditable(False)
        class_key = _BRANCH_CLASS_KEY[branch_code]
        branch_templates = [
            t for t in templates
            if t["level"] == level
            and _detect_branch(t.get("row", {})) == class_key
        ]
        for t in sorted(branch_templates, key=lambda x: x["name"]):
            self.template_combo.addItem(t["name"], t)
        if not branch_templates:
            self.template_combo.addItem("(no templates)", None)
            self.template_combo.setEnabled(False)
            self.min_spin.setValue(0)
            self.max_spin.setValue(0)
            self.min_spin.setEnabled(False)
            self.max_spin.setEnabled(False)
        layout.addWidget(self.template_combo)

        # Link min/max
        self.min_spin.valueChanged.connect(self._on_min_changed)
        self.max_spin.valueChanged.connect(self._on_max_changed)

    def _on_min_changed(self, val: int):
        if val > self.max_spin.value():
            self.max_spin.setValue(val)

    def _on_max_changed(self, val: int):
        if val < self.min_spin.value():
            self.min_spin.setValue(val)

    def get_config(self) -> dict:
        template = self.template_combo.currentData()
        return {
            "level": self.level,
            "branch": self.branch,
            "min": self.min_spin.value(),
            "max": self.max_spin.value(),
            "template": template,
        }


def _detect_branch(row_dict: dict) -> str:
    """Return '1' (INF), '2' (CAV), '3' (ART), or '0' from a template row."""
    class_val = str(row_dict.get("CLASS", "")).upper()
    if "_INF_" in class_val:
        return "1"
    if "_CAV_" in class_val:
        return "2"
    if "_ART_" in class_val:
        return "3"
    return "0"


class _BranchLevelRow(QFrame):
    """3-column row for Level 5/6: Infantry | Cavalry | Artillery."""

    def __init__(self, level: int, templates: list[dict], parent=None):
        super().__init__(parent)
        self.level = level
        self.setFrameShape(QFrame.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Level label
        level_name = LEVEL_NAMES[level - 1] if level <= len(LEVEL_NAMES) else f"Level {level}"
        header = QLabel(f"Level {level} {level_name}s")
        header.setStyleSheet("font-weight: bold;")
        outer.addWidget(header)

        # Column headers
        self._columns: list[_BranchColumn] = []
        grid = QGridLayout()
        grid.setSpacing(12)

        for col_idx, (code, label) in enumerate(BRANCHES):
            unit_names = _BRANCH_UNIT_NAMES.get(level, {})
            unit_name = unit_names.get(code, f"{level_name}s")
            header_label = QLabel(f"{label} {unit_name}")
            header_label.setAlignment(Qt.AlignCenter)
            header_label.setStyleSheet("font-weight: bold; padding: 2px;")
            grid.addWidget(header_label, 0, col_idx)

            col = _BranchColumn(level, code, templates)
            self._columns.append(col)
            grid.addWidget(col, 1, col_idx)

        outer.addLayout(grid)

    def get_config(self) -> list[dict]:
        return [col.get_config() for col in self._columns]


class GenerateSubtreeDialog(QDialog):
    """Dialog for generating a subtree of units under the selected unit."""

    def __init__(self, selected_level: int, templates: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Subtree")
        self.setMinimumWidth(720)

        layout = QVBoxLayout(self)

        info = QLabel(
            f"Selected unit is at level {selected_level} "
            f"({LEVEL_NAMES[selected_level - 1] if selected_level <= len(LEVEL_NAMES) else '?'}). "
            f"Configure the units to generate below it."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Build one row per constructible level
        self._rows: list[_LevelRow | _BranchLevelRow] = []
        for lvl in range(selected_level + 1, 7):
            if lvl >= 5:
                row = _BranchLevelRow(lvl, templates)
            else:
                row = _LevelRow(lvl, templates)
            self._rows.append(row)
            layout.addWidget(row)

        if not self._rows:
            layout.addWidget(QLabel("No levels to generate below this unit."))

        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        generate_btn = QPushButton("Generate")
        generate_btn.setDefault(True)
        generate_btn.clicked.connect(self.accept)
        btn_layout.addWidget(generate_btn)
        layout.addLayout(btn_layout)

    def get_config(self) -> list[dict]:
        config = []
        for row in self._rows:
            config.extend(row.get_config())
        return config


class GenerateSubtreeConfirmDialog(QDialog):
    """Confirmation dialog showing the generated subtree preview."""

    def __init__(self, settings_text: str, summary_text: str,
                 preview_nodes: list[dict], parent_node: dict,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Generated Subtree")
        self.setMinimumSize(550, 500)

        layout = QVBoxLayout(self)

        # Settings summary
        settings_label = QLabel(settings_text)
        settings_label.setWordWrap(True)
        layout.addWidget(settings_label)

        layout.addSpacing(4)

        # Unit count + head count summary
        summary_label = QLabel(summary_text)
        summary_label.setWordWrap(True)
        font = summary_label.font()
        font.setBold(True)
        summary_label.setFont(font)
        layout.addWidget(summary_label)

        layout.addSpacing(4)

        # Preview tree
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Unit", "Level", "Strength", "Experience"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.tree.setSelectionMode(QTreeWidget.NoSelection)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #161616;
                alternate-background-color: #1f1f1f;
                color: #e0e0e0;
                gridline-color: #333333;
            }
            QTreeWidget::item {
                color: #e0e0e0;
            }
            QHeaderView::section {
                background-color: #1f1f1f;
                color: #e0e0e0;
                border: 1px solid #333333;
            }
        """)
        layout.addWidget(self.tree, 1)

        # Build tree items
        side = parent_node.get("side", 0)
        root_item = self._create_item(parent_node, is_parent=True)
        apply_side_colors_to_item(root_item, side)
        self.tree.addTopLevelItem(root_item)
        for child_node in preview_nodes:
            self._add_children(root_item, child_node, side)
        self.tree.expandAll()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(lambda: self.done(RESULT_BACK))
        btn_layout.addWidget(back_btn)
        regenerate_btn = QPushButton("Regenerate")
        regenerate_btn.clicked.connect(lambda: self.done(RESULT_REGENERATE))
        btn_layout.addWidget(regenerate_btn)
        confirm_btn = QPushButton("Confirm")
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(lambda: self.done(RESULT_CONFIRM))
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

    def _create_item(self, node: dict, is_parent: bool = False) -> QTreeWidgetItem:
        indicator = "\u25a3" if is_parent else "\u25a2"
        name = node.get("name", "?")
        level_info = node.get("level_info", "")
        strength = node.get("subtree_strength", node.get("head_count", 0))
        strength_str = str(int(strength)) if strength == int(strength) else f"{strength:.1f}"
        experience = node.get("subtree_experience", node.get("experience", 0.0))
        exp_str = f"{experience:.2f}"
        item = QTreeWidgetItem([
            f"{indicator} {name}", level_info, strength_str, exp_str,
        ])
        item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
        item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
        return item

    def _add_children(self, parent_item: QTreeWidgetItem, node: dict, side: int) -> None:
        item = self._create_item(node)
        apply_side_colors_to_item(item, side)
        parent_item.addChild(item)
        for child in node.get("children", []):
            self._add_children(item, child, side)
