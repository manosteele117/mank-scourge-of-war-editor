from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame, QSizePolicy,
)
from PySide6.QtCore import Signal


class OOBSharedToolbar(QWidget):
    """Shared toolbar for the tree + visual layout split.

    Left side: placement filter (controls tree) + Regen Indices (controls tree data)
    Right side: Regenerate Layout + Reset View (controls visual layout)
    """

    placement_filter_changed = Signal(str)
    regen_indices_requested = Signal()
    regenerate_layout_requested = Signal()
    toggle_layout_view_requested = Signal(bool)

    _FILTER_MODES = ["all", "placed", "unplaced"]
    _FILTER_LABELS = {
        "all": "Showing All Units",
        "placed": "Showing Placed Units",
        "unplaced": "Showing Unplaced Units",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        self.filter_button = QPushButton("Showing All Units")
        self.filter_button.clicked.connect(self._cycle_filter)
        layout.addWidget(self.filter_button)


        # Moved from top toolbar — controls tree data
        self.regen_indices_button = QPushButton("Regen Indices")
        self.regen_indices_button.setToolTip(
            "Regenerate hierarchy indices sequentially under each parent"
        )
        self.regen_indices_button.clicked.connect(self.regen_indices_requested.emit)
        layout.addWidget(self.regen_indices_button)

        # Separator
        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(vsep)
        
        # Stretch pushes the rest to the right
        layout.addStretch()

        # Right side — visual layout controls
        self.regenerate_layout_button = QPushButton("Regenerate Layout")
        self.regenerate_layout_button.clicked.connect(
            self.regenerate_layout_requested.emit
        )
        layout.addWidget(self.regenerate_layout_button)

        self.toggle_layout_view_button = QPushButton("Show Layout")
        self.toggle_layout_view_button.setCheckable(True)
        self.toggle_layout_view_button.clicked.connect(
            lambda checked: self.toggle_layout_view_requested.emit(checked)
        )
        layout.addWidget(self.toggle_layout_view_button)

        # Internal filter state
        self._current_mode = "all"

    def _cycle_filter(self):
        idx = self._FILTER_MODES.index(self._current_mode)
        new_mode = self._FILTER_MODES[(idx + 1) % 3]
        self.set_filter_mode(new_mode)
        self.placement_filter_changed.emit(new_mode)

    def set_filter_mode(self, mode):
        if mode not in self._FILTER_LABELS:
            return
        self._current_mode = mode
        self.filter_button.setText(self._FILTER_LABELS[mode])
        if mode == "all":
            self.filter_button.setStyleSheet("")
        else:
            self.filter_button.setStyleSheet(
                "QPushButton { color: #b388ff; font-weight: bold; }"
            )
