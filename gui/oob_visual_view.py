from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsView, QGraphicsScene, QGraphicsLineItem
from PySide6.QtCore import Qt, Signal, QRectF, QLineF
from PySide6.QtGui import QWheelEvent, QPainter, QPen, QColor
from core.oob_model import OOBData
from gui.oob_visual_shapes import get_shape_class_for_level, UnitGraphicsItem
from gui.oob_visual_layout import HierarchicalLayout


class OOBVisualWidget(QWidget):
    """Widget for visual representation of Order of Battle formations."""

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

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addStretch()
        self.regenerate_view_button = QPushButton("Regenerate Layout")
        self.regenerate_view_button.clicked.connect(self._on_regenerate_view)
        controls_layout.addWidget(self.regenerate_view_button)
        self.reset_view_button = QPushButton("Reset View")
        self.reset_view_button.clicked.connect(self._on_reset_view)
        controls_layout.addWidget(self.reset_view_button)

        layout.addLayout(controls_layout)
        layout.addWidget(self.view)
        self.setLayout(layout)

        self.items_by_row_index = {}

    def populate(self, row_index: int = None) -> None:
        self.scene.clear()
        self.items_by_row_index.clear()

        if len(self.data.df) == 0:
            return

        positions = self.layout_engine.calculate_layout(root_row_index=row_index)

        for unit_row_idx, (x, y) in positions.items():
            row = self.data.get_row(unit_row_idx)
            level = self.data.get_level_from_hierarchy(row)
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

        self.view.reset_view(self.scene.itemsBoundingRect())

    def clear(self) -> None:
        self.scene.clear()
        self.items_by_row_index.clear()

    def highlight_unit(self, row_index: int) -> None:
        for item in self.items_by_row_index.values():
            if isinstance(item, UnitGraphicsItem):
                item.set_selected(False)
                item.set_highlighted(False)

        try:
            subordinate_indices = self.data.get_subordinate_row_indices(row_index)
        except (ValueError, Exception):
            subordinate_indices = [row_index]

        for idx in subordinate_indices:
            if idx in self.items_by_row_index:
                item = self.items_by_row_index[idx]
                if isinstance(item, UnitGraphicsItem):
                    item.set_highlighted(True)

    def _on_reset_view(self) -> None:
        self.view.reset_view(self.scene.itemsBoundingRect())

    def _on_regenerate_view(self) -> None:
        self.populate()

    def _on_unit_clicked(self, unit_row_index: int) -> None:
        self.highlight_unit(unit_row_index)
        self.unit_selected.emit(unit_row_index)


class OOBGraphicsView(QGraphicsView):
    """Custom graphics view with zoom and selection capabilities."""

    unit_clicked = Signal(int)

    MIN_ZOOM = 0.1
    MAX_ZOOM = 50.0
    ZOOM_FACTOR = 1.2

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.zoom_level = 1.0
        self.last_mouse_pos = None
        self.panning = False
        self.pan_start = None

        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background-color: #2c2c2c;")

    def wheelEvent(self, event: QWheelEvent) -> None:
        angle = event.angleDelta().y()
        factor = self.ZOOM_FACTOR if angle > 0 else 1 / self.ZOOM_FACTOR

        new_zoom = self.zoom_level * factor
        if new_zoom < self.MIN_ZOOM or new_zoom > self.MAX_ZOOM:
            return

        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self.zoom_level = new_zoom

    def reset_view(self, rect: QRectF) -> None:
        if rect.isNull() or not rect.isValid():
            return
        self.resetTransform()
        self.zoom_level = 1.0
        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = True
            self.pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item and isinstance(item, UnitGraphicsItem):
                self.unit_clicked.emit(item.unit_row_index)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.panning and self.pan_start is not None:
            delta = event.pos() - self.pan_start
            self.pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton and self.panning:
            self.panning = False
            self.pan_start = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
