from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QGroupBox,
    QCheckBox, QLabel, QSpinBox, QSlider,
)
from PySide6.QtCore import Qt, Signal


class SettingsTab(QWidget):
    """Settings tab for application preferences."""

    setting_changed = Signal(str, str)  # key, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes = {}
        self._spinboxes = {}
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
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        debug_plot_cb = QCheckBox("Plot Formations When Placed (debug)")
        debug_plot_cb.toggled.connect(
            lambda checked: self.setting_changed.emit(
                "debug_formation_plot", "true" if checked else "false"))
        layout.addWidget(debug_plot_cb)
        self._checkboxes["debug_formation_plot"] = debug_plot_cb

        pf_row = QHBoxLayout()
        pf_level_label = QLabel("Plot Formations Level:")
        pf_row.addWidget(pf_level_label)
        self.formation_level_slider = QSlider(Qt.Orientation.Horizontal)
        self.formation_level_slider.setRange(3, 6)
        self.formation_level_slider.setValue(3)
        self.formation_level_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.formation_level_slider.setTickInterval(1)
        self.formation_level_slider.setFixedWidth(120)
        self.formation_level_slider.setToolTip("Plot formations for units at this level and above (3+=Lvl 1-3, 6+=All)")
        self.formation_level_slider.valueChanged.connect(
            lambda val: self.setting_changed.emit("formation_plot_level", str(val)))
        pf_row.addWidget(self.formation_level_slider)
        self.formation_level_label = QLabel("5+")
        self.formation_level_label.setFixedWidth(24)
        pf_row.addWidget(self.formation_level_label)
        self.formation_level_slider.valueChanged.connect(
            lambda val: self.formation_level_label.setText(f"{val}+"))
        layout.addLayout(pf_row)

        # Sync slider enabled state with checkbox
        def _sync_formation_slider_enabled(checked):
            self.formation_level_slider.setEnabled(checked)
            self.formation_level_label.setEnabled(checked)
        debug_plot_cb.toggled.connect(_sync_formation_slider_enabled)
        _sync_formation_slider_enabled(debug_plot_cb.isChecked())

        debug_logging_cb = QCheckBox("Debug Logging")
        debug_logging_cb.setToolTip("Enable verbose debug logging to console.")
        debug_logging_cb.toggled.connect(
            lambda checked: self.setting_changed.emit(
                "debug_logging", "true" if checked else "false"))
        layout.addWidget(debug_logging_cb)
        self._checkboxes["debug_logging"] = debug_logging_cb

        ts_row = QHBoxLayout()
        ts_label = QLabel("Tile Scale:")
        ts_row.addWidget(ts_label)
        tile_scale_spinbox = QSpinBox()
        tile_scale_spinbox.setMinimum(1)
        tile_scale_spinbox.setMaximum(4096)
        tile_scale_spinbox.setValue(512)
        tile_scale_spinbox.setToolTip("Default: 512. Controls coordinate scaling.")
        tile_scale_spinbox.valueChanged.connect(
            lambda val: self.setting_changed.emit("tile_scale", str(val)))
        ts_row.addWidget(tile_scale_spinbox)
        layout.addLayout(ts_row)
        self._spinboxes["tile_scale"] = tile_scale_spinbox

        upy_row = QHBoxLayout()
        upy_label = QLabel("Units Per Yard:")
        upy_row.addWidget(upy_label)
        units_per_yard_spinbox = QSpinBox()
        units_per_yard_spinbox.setMinimum(1)
        units_per_yard_spinbox.setMaximum(256)
        units_per_yard_spinbox.setValue(30)
        units_per_yard_spinbox.setToolTip("Default: 30. Units displayed per yard on the map.")
        units_per_yard_spinbox.valueChanged.connect(
            lambda val: self.setting_changed.emit("units_per_yard", str(val)))
        upy_row.addWidget(units_per_yard_spinbox)
        layout.addLayout(upy_row)
        self._spinboxes["units_per_yard"] = units_per_yard_spinbox

        auto_fill_cb = QCheckBox("Auto-Fill Unplaced Supply/Couriers On Save")
        auto_fill_cb.setToolTip(
            "When saving a scenario, automatically include unplaced courier/wagon "
            "direct children of placed commanders at the commander's position.")
        auto_fill_cb.toggled.connect(
            lambda checked: self.setting_changed.emit(
                "auto_fill_supply_on_save", "true" if checked else "false"))
        layout.addWidget(auto_fill_cb)
        self._checkboxes["auto_fill_supply_on_save"] = auto_fill_cb

        return group

    def apply_settings(self, config: dict):
        """Restore checkbox and spinbox states from a config dict."""
        debug_val = config.get("debug_formation_plot", "false")
        cb = self._checkboxes.get("debug_formation_plot")
        if cb is not None:
            cb.setChecked(debug_val == "true")

        log_val = config.get("debug_logging", "false")
        cb = self._checkboxes.get("debug_logging")
        if cb is not None:
            cb.setChecked(log_val == "true")

        ts_val = config.get("tile_scale", "512")
        sb = self._spinboxes.get("tile_scale")
        if sb is not None:
            sb.setValue(int(ts_val))

        upy_val = config.get("units_per_yard", "30")
        sb = self._spinboxes.get("units_per_yard")
        if sb is not None:
            sb.setValue(int(upy_val))

        pf_val = config.get("formation_plot_level", "5")
        self.formation_level_slider.setValue(int(pf_val))

        auto_fill_val = config.get("auto_fill_supply_on_save", "true")
        cb = self._checkboxes.get("auto_fill_supply_on_save")
        if cb is not None:
            cb.setChecked(auto_fill_val == "true")

    def get_settings(self) -> dict:
        """Return current settings as a dict."""
        result = {
            key: "true" if cb.isChecked() else "false"
            for key, cb in self._checkboxes.items()
        }
        for key, sb in self._spinboxes.items():
            result[key] = str(sb.value())
        result["formation_plot_level"] = str(self.formation_level_slider.value())
        return result
