import math
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF


STAR_COLOR = QColor("#FFD700")
STAR_BORDER = QColor("#ffffff")


class MapObjectiveItem(QGraphicsItem):
    """
    A world-space star marker on the minimap representing a scenario objective.

    Rendered as a 5-pointed star in bright yellow. Supports drag, selection,
    and hover highlighting. Tracks world coordinates and objective fields
    matching the maplocations.csv schema.
    """

    OUTER_RADIUS = 1000
    INNER_RADIUS = 400
    NUM_POINTS = 5

    def __init__(self, objective_id: int, name: str, world_x: int, world_y: int,
                 fields: Dict[str, Any], map_widget=None, parent=None):
        super().__init__(parent)
        self.objective_id = objective_id
        self.name = name
        self.world_x = world_x
        self.world_y = world_y
        self.fields = fields
        self.map_widget = map_widget
        self.is_hovered = False

        self._scene_path: Optional[QPainterPath] = None

        self.setData(Qt.UserRole, self.objective_id)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self._rebuild_scene_geometry()

    # ── Geometry ─────────────────────────────────────────────────

    def _build_star_path(self, center_x: float, center_y: float,
                         outer_r: float, inner_r: float, points: int) -> QPainterPath:
        path = QPainterPath()
        angle_step = math.pi / points
        for i in range(points * 2):
            r = outer_r if i % 2 == 0 else inner_r
            angle = -math.pi / 2 + i * angle_step
            x = center_x + r * math.cos(angle)
            y = center_y + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        return path

    def _rebuild_scene_geometry(self):
        if self.map_widget is None:
            return
        self.prepareGeometryChange()
        center = self.map_widget.world_to_scene(self.world_x, self.world_y)
        item_pos = self.pos()
        local_center = center - item_pos

        scale = self.map_widget.get_scene_scale()
        outer = self.OUTER_RADIUS * scale
        inner = self.INNER_RADIUS * scale

        self._scene_path = self._build_star_path(
            local_center.x(), local_center.y(), outer, inner, self.NUM_POINTS)

    def update_from_world(self):
        self._rebuild_scene_geometry()
        self.update()

    def boundingRect(self) -> QRectF:
        if self._scene_path is not None and not self._scene_path.isEmpty():
            return self._scene_path.boundingRect().adjusted(-5, -5, 5, 5)
        return QRectF()

    def shape(self) -> QPainterPath:
        if self._scene_path is not None:
            return self._scene_path
        return QPainterPath()

    # ── Paint ────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None):
        if self._scene_path is None or self._scene_path.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isSelected():
            border_color = QColor("#ffff00")
            border_width = 3.0
        else:
            border_color = STAR_BORDER
            border_width = 1.5

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(STAR_COLOR))
        painter.drawPath(self._scene_path)

        if self._scene_path:
            center = self._scene_path.boundingRect().center()
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.setFont(QFont("Arial", 7))
            painter.drawText(center, self.name)

    # ── Hover ────────────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()

    # ── Drag ─────────────────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.map_widget is not None:
            self.world_x, self.world_y = self.map_widget.scene_to_world(
                value.x(), value.y())
            self.fields["loc x"] = self.world_x
            self.fields["loc z"] = self.world_y
            self._rebuild_scene_geometry()
            if hasattr(self.map_widget, '_on_objective_moved_from_item'):
                self.map_widget._on_objective_moved_from_item(
                    self.objective_id, self.world_x, self.world_y)
        return super().itemChange(change, value)
