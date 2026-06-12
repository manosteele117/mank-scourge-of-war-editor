"""MapUnitItem — a worldspace polygon on the minimap.

Rendered as either a rectangle (level 6) or a branch-specific commander shape
(levels 1-5). Supports drag, rotate, selection, and hover highlighting.

Extracted from gui/oob_map_view.py to keep the map widget focused on map I/O.
"""

import math
from typing import Optional

from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QFont, QPen, QBrush, QColor, QPainterPath,
    QPolygonF, QPainterPathStroker, QFontMetrics,
)

from core.constants import (
    get_side_color,
    CMD_CONCENTRIC_GAP, CMD_FACING_ARROW_LEN, CMD_FACING_ARROW_HEAD,
    ART_CANNON_TOTAL_W, ART_CANNON_TOTAL_H,
    WAGON_HATCH_SPACING, WAGON_HATCH_WIDTH,
)
from core.formation import ActualFormation, FormationArchetype


class MapUnitItem(QGraphicsItem):
    """
    A worldspace polygon on the minimap, rendered as either a rectangle or
    a branch-specific command shape.

    Level 6 units are rendered as rectangles with type-specific accents
    (wagons: hatching, cavalry: chevron, artillery: barrel extension).
    Levels 1-5 are rendered as concentric shapes (hex/diamond/square by branch)
    with branch-specific inner markers and a facing arrow.
    Supports drag, rotate, selection, and hover highlighting.
    """

    DEFAULT_RECT_WIDTH = 2000
    DEFAULT_RECT_HEIGHT = 2000
    CMD_SIZE = 1000
    DOT_RADIUS = 0.1
    SPRITE_SCALE = 6

    def __init__(self, name: str, unit_row_index: int, side: int, level: int,
                 formation: str, world_x: int, world_y: int, head_count: int = 0,
                 class_value: str = "", map_widget=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.unit_row_index = unit_row_index
        self.side = side
        self.level = level
        self.formation = formation
        self.world_x = world_x
        self.world_y = world_y
        self.head_count = head_count
        self.class_value = class_value
        self.map_widget = map_widget
        self.is_hovered = False
        self.is_highlighted = False

        self._scene_polygon: Optional[QPolygonF] = None
        self._scene_path: Optional[QPainterPath] = None
        self._cmd_world_verts: list = []
        self._command_dots: list = []
        self._scene_dots: list = []
        self._label: str = ""

        # Commander shape data (levels 1-5)
        self._cmd_concentric_world_paths: list[QPainterPath] = []
        self._cmd_markers_world: list[tuple] = []
        self._cmd_facing_world_path: Optional[QPainterPath] = None
        self._scene_concentric_paths: list[QPainterPath] = []
        self._scene_markers: list[tuple] = []
        self._scene_facing_path: Optional[QPainterPath] = None

        # Artillery cannon scene rects
        self._scene_cannon_rects: list[QRectF] = []

        self.world_width = self.DEFAULT_RECT_WIDTH
        self.world_height = self.DEFAULT_RECT_HEIGHT
        self.origin_offset_x = self.DEFAULT_RECT_WIDTH / 2
        self.origin_offset_y = self.DEFAULT_RECT_HEIGHT / 2

        self.setData(Qt.UserRole, unit_row_index)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setRotation(0)

    def refresh_dimensions(self, archetype_id: str = None):
        """Recompute world dimensions from the unit's formation archetype."""
        class_upper = self.class_value.upper() if self.class_value else ""
        if self.level == 6 and "_ART_" in class_upper:
            self.world_width = ART_CANNON_TOTAL_W
            self.world_height = ART_CANNON_TOTAL_H
            self.origin_offset_x = ART_CANNON_TOTAL_W / 2
            self.origin_offset_y = ART_CANNON_TOTAL_H / 2
            return
        formation_id = archetype_id if archetype_id is not None else self.formation
        if not formation_id or formation_id not in FormationArchetype.formations:
            return
        try:
            if self.map_widget and self.map_widget.oob_data:
                af = self.map_widget.build_strength(self.unit_row_index, archetype_id=formation_id)
            else:
                af = ActualFormation(
                    archetype_id=formation_id,
                    strength=int(self.head_count / self.SPRITE_SCALE))
            length_yards, depth_yards = af.get_dimensions()
            upy = self.map_widget.units_per_yard if self.map_widget else 30
            self.world_width = length_yards * upy
            self.world_height = depth_yards * upy
            self.origin_offset_x = af.origin_offset_x * upy
            self.origin_offset_y = af.origin_offset_y * upy
        except Exception:
            pass

    # ── Commander shapes (levels 1-5) ────────────────────────────────

    def _build_command_shape(self, level, cx, cy, size):
        class_upper = self.class_value.upper() if self.class_value else ""
        if "_CAV_" in class_upper:
            branch = "cavalry"
        elif "_ART_" in class_upper:
            branch = "artillery"
        else:
            branch = "infantry"

        r = size / 2.0
        num_layers = max(1, 6 - level) if level <= 5 else 1

        if branch == "infantry":
            marker_type = "x"
        elif branch == "cavalry":
            marker_type = "diamond"
        else:
            marker_type = "dot"
        marker_count = num_layers

        concentric_paths = []
        for i in range(num_layers):
            layer_r = r + i * CMD_CONCENTRIC_GAP
            path = self._make_branch_shape(branch, cx, cy, layer_r)
            concentric_paths.append(path)

        markers = self._distribute_markers(branch, marker_type, marker_count, cx, cy, r * 0.35)

        facing_path = QPainterPath()
        arrow_len = CMD_FACING_ARROW_LEN
        arrow_head = CMD_FACING_ARROW_HEAD
        base_y = cy - r
        tip_y = cy - r - arrow_len
        facing_path.moveTo(cx, tip_y)
        facing_path.lineTo(cx - arrow_head / 2, base_y)
        facing_path.moveTo(cx, tip_y)
        facing_path.lineTo(cx + arrow_head / 2, base_y)

        return concentric_paths, markers, facing_path

    def _make_branch_shape(self, branch, cx, cy, r):
        path = QPainterPath()
        if branch == "cavalry":
            r = r * 1.25
        elif branch == "artillery":
            r = r * 0.75
        if branch == "infantry":
            h = r * math.sqrt(3) / 2.0
            verts = [
                (cx + r, cy), (cx + r / 2, cy - h), (cx - r / 2, cy - h),
                (cx - r, cy), (cx - r / 2, cy + h), (cx + r / 2, cy + h),
            ]
            path.moveTo(verts[0][0], verts[0][1])
            for v in verts[1:]:
                path.lineTo(v[0], v[1])
            path.closeSubpath()
        elif branch == "cavalry":
            verts = [
                (cx, cy - r), (cx + r / 2, cy), (cx, cy + r), (cx - r / 2, cy),
            ]
            path.moveTo(verts[0][0], verts[0][1])
            for v in verts[1:]:
                path.lineTo(v[0], v[1])
            path.closeSubpath()
        else:
            path.addRect(cx - r, cy - r, r * 2, r * 2)
        return path

    def _distribute_markers(self, branch, marker_type, count, cx, cy, radius):
        markers = []
        if count <= 0:
            return markers
        if count == 1:
            markers.append((cx, cy, marker_type))
            return markers
        for i in range(count):
            angle = -math.pi / 2 + i * 2 * math.pi / count
            mx = cx + radius * math.cos(angle)
            my = cy + radius * math.sin(angle)
            markers.append((mx, my, marker_type))
        return markers

    # ── Geometry rebuild ─────────────────────────────────────────────

    def _rebuild_scene_geometry(self):
        if self.map_widget is None:
            return
        self.prepareGeometryChange()
        if self.level == 6:
            ox = self.origin_offset_x
            oy = self.origin_offset_y
            self._cmd_world_verts = [
                (self.world_x - ox, self.world_y - oy),
                (self.world_x - ox + self.world_width, self.world_y - oy),
                (self.world_x - ox + self.world_width, self.world_y - oy + self.world_height),
                (self.world_x - ox, self.world_y - oy + self.world_height),
            ]
            self._cmd_world_path = None
            self._cmd_concentric_world_paths = []
            self._cmd_markers_world = []
            self._cmd_facing_world_path = None
        else:
            concentric, markers, facing = self._build_command_shape(
                self.level, self.world_x, self.world_y, self.CMD_SIZE)
            self._cmd_concentric_world_paths = concentric
            self._cmd_markers_world = markers
            self._cmd_facing_world_path = facing
            self._cmd_world_path = concentric[0] if concentric else None
            self._cmd_world_verts = None
            self._command_dots = [(mx, my) for mx, my, _ in markers]
        self._refresh_scene_coords()

    def _refresh_scene_coords(self):
        if self.map_widget is None:
            return
        item_pos = self.pos()
        poly = QPolygonF()
        path = QPainterPath()

        if self.level == 6:
            if hasattr(self, '_cmd_world_verts') and self._cmd_world_verts:
                for wx, wy in self._cmd_world_verts:
                    sp = self.map_widget.world_to_scene(wx, wy)
                    p = sp - item_pos
                    poly.append(p)
                if poly.size() >= 2:
                    path.moveTo(poly[0])
                    for i in range(1, poly.size()):
                        path.lineTo(poly[i])
                    path.closeSubpath()
        else:
            self._scene_concentric_paths = []
            for world_path in self._cmd_concentric_world_paths:
                scene_path = QPainterPath()
                first = True
                for i in range(world_path.elementCount()):
                    elem = world_path.elementAt(i)
                    sp = self.map_widget.world_to_scene(elem.x, elem.y)
                    p = sp - item_pos
                    if first:
                        scene_path.moveTo(p.x(), p.y())
                        first = False
                    else:
                        scene_path.lineTo(p.x(), p.y())
                self._scene_concentric_paths.append(scene_path)

            if self._scene_concentric_paths:
                path = self._scene_concentric_paths[0]

            self._scene_markers = []
            for wx, wy, mtype in self._cmd_markers_world:
                sp = self.map_widget.world_to_scene(wx, wy)
                p = sp - item_pos
                self._scene_markers.append((p.x(), p.y(), mtype))

            if self._cmd_facing_world_path is not None:
                facing_scene = QPainterPath()
                first = True
                for i in range(self._cmd_facing_world_path.elementCount()):
                    elem = self._cmd_facing_world_path.elementAt(i)
                    sp = self.map_widget.world_to_scene(elem.x, elem.y)
                    p = sp - item_pos
                    if first:
                        facing_scene.moveTo(p.x(), p.y())
                        first = False
                    else:
                        facing_scene.lineTo(p.x(), p.y())
                self._scene_facing_path = facing_scene
            else:
                self._scene_facing_path = None

        self._scene_polygon = poly
        self._scene_path = path if not path.isEmpty() else None

        if self.level < 6:
            if self.map_widget:
                stroke_world = self.CMD_SIZE * 0.06
                c = self.map_widget.world_to_scene(self.world_x, self.world_y)
                e = self.map_widget.world_to_scene(self.world_x + stroke_world, self.world_y)
                self._scene_stroke_width = abs(e.x() - c.x())
            else:
                self._scene_stroke_width = self.CMD_SIZE * 0.06
        else:
            self._scene_stroke_width = 0

        self._scene_dots = (
            [(mx, my) for mx, my, _ in self._scene_markers]
            if hasattr(self, '_scene_markers') else []
        )

    # ── Qt Graphics item interface ───────────────────────────────────

    def boundingRect(self):
        if self.level < 6:
            if self._scene_concentric_paths:
                outermost = self._scene_concentric_paths[-1]
                rect = outermost.boundingRect()
                if self._scene_facing_path is not None:
                    rect = rect.united(self._scene_facing_path.boundingRect())
                return rect.adjusted(-2, -2, 2, 2)
            half = self.CMD_SIZE / 2
            return QRectF(-half, -half, half * 2, half * 2)
        if self._scene_cannon_rects:
            rect = QRectF()
            for r in self._scene_cannon_rects:
                rect = rect.united(r) if not rect.isNull() else QRectF(r)
            return rect.adjusted(-5, -5, 5, 5)
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            rect = self._scene_polygon.boundingRect()
            for dx, dy in self._scene_dots:
                rect = rect.united(QRectF(
                    dx - self.DOT_RADIUS, dy - self.DOT_RADIUS,
                    self.DOT_RADIUS * 2, self.DOT_RADIUS * 2))
            return rect.adjusted(-5, -5, 5, 5)
        return QRectF()

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self.level < 6:
            if self._scene_concentric_paths:
                path.addPath(self._scene_concentric_paths[-1])
                if self._scene_facing_path is not None:
                    path.addPath(self._scene_facing_path)
            return path
        if self._scene_cannon_rects:
            for r in self._scene_cannon_rects:
                path.addRect(r)
            return path
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            path.addPolygon(self._scene_polygon)
            path.closeSubpath()
        return path

    def paint(self, painter: QPainter, option, widget=None):
        if self.level < 6:
            self._paint_commander(painter)
        else:
            self._paint_level6(painter)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.map_widget is not None:
            self.world_x, self.world_y = self.map_widget.scene_to_world(
                value.x(), value.y())
            self._rebuild_scene_geometry()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def set_highlighted(self, highlighted: bool):
        self.is_highlighted = highlighted
        self.update()

    # ── Level-6 painting ─────────────────────────────────────────────

    def _paint_level6(self, painter: QPainter):
        if self._scene_polygon is None or self._scene_polygon.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side_color = get_side_color(
            self.side,
            is_selected=self.isSelected(),
            is_hovered=self.is_hovered,
            is_highlighted=self.is_highlighted,
        )

        if self.isSelected():
            border_color = QColor("#ffff00")
            border_width = 0.25
        else:
            border_color = QColor("#ffffff")
            border_width = 0.02

        class_upper = self.class_value.upper() if self.class_value else ""
        formation_upper = self.formation.upper() if self.formation else ""

        if "_ART_" in class_upper:
            self._scene_cannon_rects = []
            self._paint_artillery_cannon(painter, side_color, border_color, border_width)
        else:
            self._scene_cannon_rects = []
            painter.setPen(QPen(border_color, border_width))
            painter.setBrush(QBrush(side_color))
            painter.drawPolygon(self._scene_polygon)

            if "SUPPLYWAGON" in formation_upper:
                self._paint_wagon_hatching(painter, side_color)
            elif "_CAV_" in class_upper:
                self._paint_cavalry_slash(painter, side_color)

    def _paint_wagon_hatching(self, painter, base_color):
        if self._scene_polygon is None or self._scene_polygon.isEmpty():
            return
        rect = self._scene_polygon.boundingRect()
        hatch_color = base_color.darker(130)
        painter.setPen(QPen(hatch_color, WAGON_HATCH_WIDTH * 0.02))
        y = rect.top() + WAGON_HATCH_SPACING * 0.02
        while y < rect.bottom():
            painter.drawLine(
                QPointF(rect.left() + 2, y), QPointF(rect.right() - 2, y))
            y += WAGON_HATCH_SPACING * 0.02

    def _paint_cavalry_slash(self, painter, base_color):
        if self._scene_polygon is None or self._scene_polygon.isEmpty():
            return
        rect = self._scene_polygon.boundingRect()
        thickness = min(rect.width(), rect.height()) * 0.10
        inset = thickness / 2
        painter.setPen(QPen(QColor("#ffffff"), thickness))
        painter.drawLine(
            QPointF(rect.left() + inset, rect.top() + inset),
            QPointF(rect.right() - inset, rect.bottom() - inset))

    def _paint_artillery_cannon(self, painter, base_color, border_color, border_width):
        if self._scene_polygon is None or self._scene_polygon.isEmpty():
            return
        rect = self._scene_polygon.boundingRect()
        cx = rect.center().x()
        cy = rect.center().y()

        s = min(rect.width() / 45, rect.height() / 60)
        cannon_color = base_color.lighter(140)

        # Barrel
        bw = 15 * s
        bh = 60 * s
        barrel = QRectF(cx - bw / 2, cy - bh / 2, bw, bh)
        painter.fillRect(barrel, QBrush(cannon_color))
        painter.setPen(QPen(border_color, border_width))
        painter.drawRect(barrel)

        # Wheels
        ww = 10 * s
        wh = 25 * s
        gap = 5 * s
        accessory_cy = cy + bh / 6
        left_wheel = QRectF(cx - bw / 2 - gap - ww, accessory_cy - wh / 2, ww, wh)
        right_wheel = QRectF(cx + bw / 2 + gap, accessory_cy - wh / 2, ww, wh)
        painter.fillRect(left_wheel, QBrush(cannon_color))
        painter.drawRect(left_wheel)
        painter.fillRect(right_wheel, QBrush(cannon_color))
        painter.drawRect(right_wheel)

        # Connectors
        cw = 5 * s
        ch = 16 * s
        left_conn = QRectF(cx - bw / 2 - cw, accessory_cy - ch / 2, cw, ch)
        right_conn = QRectF(cx + bw / 2, accessory_cy - ch / 2, cw, ch)
        painter.fillRect(left_conn, QBrush(cannon_color))
        painter.drawRect(left_conn)
        painter.fillRect(right_conn, QBrush(cannon_color))
        painter.drawRect(right_conn)

        self._scene_cannon_rects = [barrel, left_wheel, right_wheel, left_conn, right_conn]

    # ── Commander painting (levels 1-5) ──────────────────────────────

    def _paint_commander(self, painter: QPainter):
        if not self._scene_concentric_paths:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side_color = get_side_color(
            self.side,
            is_selected=self.isSelected(),
            is_hovered=self.is_hovered,
            is_highlighted=self.is_highlighted,
        )

        if self.isSelected():
            border_color = QColor("#ffff00")
            border_width = 0.25
        else:
            border_color = QColor("#ffffff")
            border_width = 0.02

        stroke_width = self._scene_stroke_width
        num_paths = len(self._scene_concentric_paths)

        for i, scene_path in enumerate(self._scene_concentric_paths):
            is_innermost = (i == 0)
            if is_innermost:
                stroker = QPainterPathStroker()
                stroker.setWidth(stroke_width)
                stroked = stroker.createStroke(scene_path)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(side_color))
                painter.drawPath(scene_path)
                painter.setPen(QPen(border_color, border_width))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(stroked)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(side_color))
                painter.drawPath(stroked)
            else:
                outer_ratio = 1.0 - (i / max(num_paths, 1)) * 0.4
                ring_width = stroke_width * 0.6 * outer_ratio
                painter.setPen(QPen(side_color, ring_width))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(scene_path)

        # Branch markers
        if self._scene_markers and self._scene_concentric_paths:
            inner_rect = self._scene_concentric_paths[0].boundingRect()
            marker_r = min(inner_rect.width(), inner_rect.height()) / 2 * 0.10
            for mx, my, mtype in self._scene_markers:
                if mtype == "x":
                    painter.setPen(QPen(QColor("#ffffff"), marker_r * 0.9))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawLine(QPointF(mx - marker_r, my - marker_r),
                                     QPointF(mx + marker_r, my + marker_r))
                    painter.drawLine(QPointF(mx - marker_r, my + marker_r),
                                     QPointF(mx + marker_r, my - marker_r))
                elif mtype == "diamond":
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor("#ffffff")))
                    diamond = QPainterPath()
                    diamond.moveTo(mx, my - marker_r * 2)
                    diamond.lineTo(mx + marker_r, my)
                    diamond.lineTo(mx, my + marker_r * 2)
                    diamond.lineTo(mx - marker_r, my)
                    diamond.closeSubpath()
                    painter.drawPath(diamond)
                elif mtype == "dot":
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor("#ffffff")))
                    painter.drawEllipse(QPointF(mx, my), marker_r, marker_r)

        # Facing arrow
        if self._scene_facing_path is not None:
            arrow_pen = QPen(QColor("#ffffff"), 0.04)
            painter.setPen(arrow_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self._scene_facing_path)

        # Name label
        if (self.map_widget is not None
                and self.map_widget._show_names
                and self.map_widget._name_field
                and self.level <= 5 - self.map_widget._name_level):
            text = self.map_widget.get_unit_field_value(
                self.unit_row_index, self.map_widget._name_field)
            if text:
                scale = self.map_widget.world_to_scene_scale()
                text_y = self.CMD_SIZE * 0.6 * scale

                font_size = max(3, 8 - self.level)
                font = QFont("Arial", font_size)
                font.setWeight(QFont.Weight.Bold)
                fm = QFontMetrics(font)
                text_width = fm.horizontalAdvance(text)
                x = -text_width / 2
                y = text_y + fm.ascent()

                side_color = get_side_color(self.side)
                stroker = QPainterPathStroker()
                stroker.setWidth(0.5)

                text_path = QPainterPath()
                text_path.addText(QPointF(x, y), font, text)

                border_path = stroker.createStroke(text_path)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#ffffff"))
                painter.drawPath(border_path)

                painter.setBrush(side_color)
                painter.drawPath(text_path)
