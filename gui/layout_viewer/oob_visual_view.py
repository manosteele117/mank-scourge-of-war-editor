from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsLineItem
from PySide6.QtCore import Qt, Signal, QRectF, QLineF
from PySide6.QtGui import QPainter, QPen, QColor
from core.oob_model import OOBData
from gui.layout_viewer.oob_visual_shapes import get_shape_class_for_level, UnitGraphicsItem
from gui.layout_viewer.oob_visual_layout import HierarchicalLayout
from gui.zoomable_view import ZoomableGraphicsView


class OOBVisualWidget(QWidget):
    """Widget for visual representation of Order of Battle formations."""

    LAYOUT_PADDING = 2000

    unit_selected = Signal(int)

    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)
        self.data = data
        self.layout_engine = HierarchicalLayout(data)

        self.scene = QGraphicsScene()
        self.view = OOBGraphicsView(self.scene)
        self.view.unit_clicked.connect(self._on_unit_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.setLayout(layout)

        self.items_by_row_index = {}
        self._highlighted: set = set()

    def populate(self, row_index: int = None) -> None:
        self.scene.clear()
        self.items_by_row_index.clear()

        if len(self.data.df) == 0:
            return

        positions = self.layout_engine.calculate_layout(root_row_index=row_index)

        for unit_row_idx, (x, y) in positions.items():
            row = self.data.get_row(unit_row_idx)
            level = self.data.get_level(unit_row_idx)
            side = int(row.get("SIDE 1", 1))
            name = str(row.get("NAME1", "Unknown"))
            formation = str(row.get("Formation", ""))

            shape_class = get_shape_class_for_level(level, formation)
            item = shape_class(name=name, unit_row_index=unit_row_idx, side=side, level=level)
            item.setPos(x, y)

            self.scene.addItem(item)
            self.items_by_row_index[unit_row_idx] = item

        if positions:
            x_coords = [x for x, y in positions.values()]
            x_min = min(x_coords) - 100
            x_max = max(x_coords) + 100
            line = QGraphicsLineItem(x_min, 0, x_max, 0)
            pen = QPen(QColor("#a9a9a9"))
            pen.setStyle(Qt.DashLine)
            line.setPen(pen)
            self.scene.addItem(line)

            padded = self.scene.itemsBoundingRect().adjusted(
                -self.LAYOUT_PADDING, -self.LAYOUT_PADDING,
                self.LAYOUT_PADDING, self.LAYOUT_PADDING)
            self.scene.setSceneRect(padded)
            self.view.reset_view(padded)

    def highlight_unit(self, row_index: int) -> None:
        if row_index is None:
            new_set: set = set()
        else:
            try:
                subordinate_indices = self.data.get_subordinate_row_indices(row_index)
            except (ValueError, Exception):
                subordinate_indices = [row_index]
            new_set = {idx for idx in subordinate_indices if idx in self.items_by_row_index}
        # Diff: only update items whose state changed AND that still exist.
        all_current = set(self.items_by_row_index.keys())
        for idx in (self._highlighted - new_set) & all_current:
            item = self.items_by_row_index[idx]
            if isinstance(item, UnitGraphicsItem):
                item.set_highlighted(False)
        for idx in (new_set - self._highlighted) & all_current:
            item = self.items_by_row_index[idx]
            if isinstance(item, UnitGraphicsItem):
                item.set_highlighted(True)
        self._highlighted = new_set & all_current

    def _on_regenerate_view(self) -> None:
        self.populate()

    def _on_unit_clicked(self, unit_row_index: int) -> None:
        self.highlight_unit(unit_row_index)
        self.unit_selected.emit(unit_row_index)


class OOBGraphicsView(QGraphicsView, ZoomableGraphicsView):
    """Custom graphics view with zoom and selection capabilities."""

    unit_clicked = Signal(int)

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.init_zoom_state()

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background-color: #2c2c2c;")

    def wheelEvent(self, event):
        ZoomableGraphicsView.wheelEvent(self, event)

    def mousePressEvent(self, event):
        if self._handle_middle_press(event):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item and isinstance(item, UnitGraphicsItem):
                self.unit_clicked.emit(item.unit_row_index)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._handle_pan_move(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._handle_middle_release(event):
            return
        super().mouseReleaseEvent(event)
