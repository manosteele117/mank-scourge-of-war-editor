from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QFileDialog, QSizePolicy, QScrollArea, QGroupBox, QCheckBox,
    QSplitter,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import os


class FileEntry(QWidget):
    """A single file entry with a button and path label."""

    file_loaded = Signal(str, str)  # config_key, file_path

    def __init__(self, label: str, hint: str, config_key: str, file_filter: str = "All Files (*)",
                 parent=None):
        super().__init__(parent)
        self.config_key = config_key
        self.file_filter = file_filter
        self.hint = hint
        self._current_path = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.button = QPushButton(f"Load {label}")
        self.button.clicked.connect(self._open_dialog)
        layout.addWidget(self.button)

        self.path_label = QLabel("—")
        self.path_label.setStyleSheet("color: #888888;")
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.path_label)

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Open - {self.hint}", "", self.file_filter)
        if path:
            self.set_path(path)
            self.file_loaded.emit(self.config_key, path)

    def set_path(self, path: str):
        self._current_path = path
        if path:
            self.path_label.setText(path)
            self.path_label.setStyleSheet("color: #ffffff;")
        else:
            self.path_label.setText("—")
            self.path_label.setStyleSheet("color: #888888;")

    def get_path(self) -> str:
        return self._current_path


class TemplateFileEntry(QWidget):
    """A single template file entry with a toggle checkbox and file name label."""

    toggled = Signal(str, bool)  # file_path, enabled

    def __init__(self, file_path: str, file_name: str, enabled: bool = True, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._enabled = enabled

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(enabled)
        self.checkbox.stateChanged.connect(self._on_state_changed)
        layout.addWidget(self.checkbox)

        self.name_label = QLabel(file_name)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.name_label)

    def _on_state_changed(self, state):
        self._enabled = (state == Qt.Checked.value)
        self.toggled.emit(self.file_path, self._enabled)

    def is_enabled(self) -> bool:
        return self._enabled


class FilesTab(QWidget):
    """Files/Settings tab for loading and managing file paths."""

    file_changed = Signal(str, str)  # config_key, file_path
    template_toggled = Signal(str, bool)  # file_path, enabled
    reload_templates = Signal()
    load_defaults_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = {}
        self._template_entries = {}  # file_path -> TemplateFileEntry
        self._init_ui()

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

        # ── Files section ──────────────────────────────────────────
        files_group = self._create_files_section()
        scroll_layout.addWidget(files_group)

        # ── Template Files section ─────────────────────────────────
        templates_group = self._create_templates_section()
        scroll_layout.addWidget(templates_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _create_files_section(self) -> QGroupBox:
        group = QGroupBox("Files")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        load_defaults_btn = QPushButton("Load Game Defaults")
        load_defaults_btn.clicked.connect(self.load_defaults_requested.emit)
        layout.addWidget(load_defaults_btn)

        self._add_entry("OOB", "oob", layout,
                        "CSV Files (*.csv)", "order of battle")
        self._add_separator(layout)
        self._add_entry("drills.csv", "drills", layout,
                        "CSV Files (*.csv)", "Formation Definitions (drills.csv)")
        self._add_entry("rifles.csv", "rifles", layout,
                        "CSV Files (*.csv)", "Weapon Options (rifles.csv)")
        self._add_entry("artillery.csv", "artillery", layout,
                        "CSV Files (*.csv)", "Artillery Options (artillery.csv)")
        self._add_separator(layout)
        self._add_entry("gfx.csv", "gfx", layout,
                        "CSV Files (*.csv)", "Defines Sprite IDs - used to set objective icons (gfx.csv)")
        self._add_entry("gfxpack.csv", "gfxpack", layout,
                        "CSV Files (*.csv)", "Defines Sprite IDs - mostly for flags (gfxpack.csv)")
        self._add_entry("unitglobal.csv", "unitglobal", layout,
                        "CSV Files (*.csv)", "Defines unit classes (unitglobal.csv)")
        self._add_separator(layout)
        self._add_entry("OOBNames.xml", "oobnames", layout,
                        "XML Files (*.xml)", "OOB unit name overrides (OOBNames.xml)")

        return group

    def _create_templates_section(self) -> QGroupBox:
        group = QGroupBox("Template Files")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left panel: template entries
        left_panel = QWidget()
        self._templates_layout = QVBoxLayout(left_panel)
        self._templates_layout.setContentsMargins(0, 0, 4, 0)
        self._templates_layout.setSpacing(4)

        self._templates_placeholder = QLabel("No template files found.")
        self._templates_placeholder.setStyleSheet("color: #666666; font-style: italic;")
        self._templates_layout.addWidget(self._templates_placeholder)

        self._templates_layout.addSpacing(8)

        self.reload_button = QPushButton("Reload Templates")
        self.reload_button.clicked.connect(self.reload_templates.emit)
        self._templates_layout.addWidget(self.reload_button)

        self._templates_layout.addStretch()

        # Right panel: help text
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)

        help_label = QLabel(self._get_template_help_text())
        help_label.setWordWrap(True)
        help_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        help_label.setStyleSheet("""
            QLabel {
                border: 1px solid #444444;
                border-radius: 4px;
                background-color: #2a2a2a;
                color: #cccccc;
                padding: 8px;
                font-family: monospace;
                font-size: 11px;
            }
        """)
        right_layout.addWidget(help_label)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 300])

        group_layout.addWidget(splitter)

        return group

    def _get_template_help_text(self) -> str:
        return """
Template Files Help
====================

Toggle
------
Check/uncheck templates to include or exclude
them when generating units/formations.

Adding Files
------------
Place new CSV files in templates/units/ and
click Reload Templates.

Creating Your Own
-----------------
You can create your own template files using
any CSV editor. Use the column headers from
templates/headers/oob_headers.csv as a
reference.

Share Your Templates
--------------------
If you create useful templates, share them on 
GitHub and they can be added to the tool.

Ideally would have templates available for specific
mods, eras, campaigns.
"""

    def scan_template_files(self, templates_dir: str, enabled_state: dict = None):
        """Scan templates_dir for CSV files and create toggle entries.

        Args:
            templates_dir: Path to the templates/units directory.
            enabled_state: Dict mapping filename -> bool (enabled state).
                           Missing files default to True.
        """
        # Clear existing entries
        for entry in self._template_entries.values():
            entry.setParent(None)
            entry.deleteLater()
        self._template_entries.clear()

        if enabled_state is None:
            enabled_state = {}

        if not os.path.isdir(templates_dir):
            return

        csv_files = sorted(f for f in os.listdir(templates_dir) if f.endswith(".csv"))

        # Remove placeholder if files found
        if csv_files:
            self._templates_placeholder.hide()

        for fname in csv_files:
            fpath = os.path.join(templates_dir, fname)
            enabled = enabled_state.get(fname, True)
            entry = TemplateFileEntry(fpath, fname, enabled)
            entry.toggled.connect(self._on_template_toggled)
            self._template_entries[fpath] = entry
            # Insert before the reload button
            self._templates_layout.insertWidget(self._templates_layout.count() - 2, entry)

    def _on_template_toggled(self, file_path: str, enabled: bool):
        self.template_toggled.emit(file_path, enabled)

    def get_enabled_template_files(self) -> set:
        """Return set of file paths that are currently enabled."""
        return {path for path, entry in self._template_entries.items()
                if entry.is_enabled()}

    def get_template_enabled_state(self) -> dict:
        """Return dict mapping filename -> bool for config persistence."""
        state = {}
        for path, entry in self._template_entries.items():
            fname = os.path.basename(path)
            state[fname] = entry.is_enabled()
        return state

    def _add_entry(self, label: str, config_key: str, layout: QVBoxLayout,
                   file_filter: str, hint: str):
        entry = FileEntry(label, hint, config_key, file_filter)
        entry.file_loaded.connect(self._on_file_loaded)
        self._entries[config_key] = entry
        layout.addWidget(entry)

    def _add_separator(self, layout: QVBoxLayout):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #444444;")
        layout.addWidget(sep)

    def _on_file_loaded(self, config_key: str, file_path: str):
        self.file_changed.emit(config_key, file_path)

    def set_entry_path(self, config_key: str, path: str):
        if config_key in self._entries:
            self._entries[config_key].set_path(path)

    def apply_game_defaults(self, base_dir: str):
        """Auto-load all logistics files from the given game base directory."""
        FILE_MAP = [
            ("drills", "Logistics/drills.csv"),
            ("rifles", "Logistics/rifles.csv"),
            ("artillery", "Logistics/artillery.csv"),
            ("gfx", "Logistics/gfx.csv"),
            ("gfxpack", "Logistics/gfxpack.csv"),
            ("unitglobal", "Logistics/unitglobal.csv"),
            ("oobnames", "Layout/Media/Language/OOBNames.xml"),
        ]
        for key, rel_path in FILE_MAP:
            full_path = os.path.join(base_dir, rel_path)
            if os.path.isfile(full_path):
                self.set_entry_path(key, full_path)
                self.file_changed.emit(key, full_path)
