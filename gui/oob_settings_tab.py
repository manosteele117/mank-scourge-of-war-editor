from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QGroupBox, QCheckBox,
)
from PySide6.QtCore import Signal


class SettingsTab(QWidget):
    """Settings tab for application preferences."""

    setting_changed = Signal(str, str)  # key, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes = {}
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

        settings_group = self._create_settings_section()
        scroll_layout.addWidget(settings_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _create_settings_section(self) -> QGroupBox:
        group = QGroupBox("Mank OOB Viewer Settings")
        group.setStyleSheet("""
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
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        debug_plot_cb = QCheckBox("Plot Formations When Placed (debug)")
        debug_plot_cb.toggled.connect(
            lambda checked: self.setting_changed.emit(
                "debug_formation_plot", "true" if checked else "false"))
        layout.addWidget(debug_plot_cb)
        self._checkboxes["debug_formation_plot"] = debug_plot_cb

        return group

    def apply_settings(self, config: dict):
        """Restore checkbox states from a config dict."""
        debug_val = config.get("debug_formation_plot", "true")
        cb = self._checkboxes.get("debug_formation_plot")
        if cb is not None:
            cb.setChecked(debug_val == "true")

    def get_settings(self) -> dict:
        """Return current settings as a dict."""
        return {
            key: "true" if cb.isChecked() else "false"
            for key, cb in self._checkboxes.items()
        }
