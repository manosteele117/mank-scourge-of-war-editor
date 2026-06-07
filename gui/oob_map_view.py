import PySide6.QtGui
import os
import json
import configparser
import traceback
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox,
    QSlider, QFileDialog, QMessageBox, QSizePolicy, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsItemGroup, QGraphicsLineItem, QGraphicsEllipseItem, QMenu,
)
from PySide6.QtGui import QPixmap, QFont, QPainter, QImage, QPen, QBrush, QColor, QPainterPath, QPolygonF, QPainterPathStroker
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PIL import Image

from core.utilities import get_tga_dimensions
from core.formation import ActualFormation, FormationArchetype
from core.oob_model import OOBData, UnitInfo
from constants import get_side_color
from gui.zoomable_view import ZoomableGraphicsView
from gui.oob_objective_item import MapObjectiveItem


class OOBMapGraphicsView(QGraphicsView, ZoomableGraphicsView):
    """Custom graphics view for the minimap with placement mode support."""
    def __init__(self, scene, map_widget, parent=None):
        super().__init__(scene, parent)
        self.map_widget = map_widget
        self.selection_rect_item = None
        self.selection_start = None
        self.is_box_selecting = False

        # Right-click rotation state
        self.is_rotating = False
        self.rotation_reference_items = []  # (item, start_wx, start_wy, start_rot)
        self._rotation_pivot_world = None
        self._pivot_marker = None
        self._last_mouse_angle = None
        self._total_delta_so_far = 0.0

        self.init_zoom_state()

    def wheelEvent(self, event):
        ZoomableGraphicsView.wheelEvent(self, event)
        self._update_pivot_marker_size()

    def mouseMoveEvent(self, event):
        if self._handle_pan_move(event):
            return
        if self.is_rotating and self.rotation_reference_items:
            scene_pos = self.mapToScene(event.pos())
            if self._last_mouse_angle is not None:
                pivot_scene = self.map_widget.world_to_scene(
                    int(self._rotation_pivot_world.x()),
                    int(self._rotation_pivot_world.y())
                )
                current_angle = self._angle_between(scene_pos, pivot_scene)
                delta = current_angle - self._last_mouse_angle
                self._last_mouse_angle = current_angle
                self._total_delta_so_far += delta
                # Apply cumulative rotation to each item
                total_rad = math.radians(self._total_delta_so_far)
                cos_d = math.cos(total_rad)
                sin_d = math.sin(total_rad)
                px = self._rotation_pivot_world.x()
                py = self._rotation_pivot_world.y()
                for item, start_wx, start_wy, start_rot in self.rotation_reference_items:
                    dx = start_wx - px
                    dy = start_wy - py
                    item.world_x = int(px + dx * cos_d - dy * sin_d)
                    item.world_y = int(py + dx * sin_d + dy * cos_d)
                    new_scene = self.map_widget.world_to_scene(item.world_x, item.world_y)
                    item.setPos(new_scene)
                    item.setRotation(start_rot + self._total_delta_so_far)
                    item._rebuild_scene_geometry()
            event.accept()
            return

        if self.is_box_selecting and self.selection_start:
            scene_pos = self.mapToScene(event.pos())
            selection_rect = QRectF(self.selection_start, scene_pos).normalized()
            if self.selection_rect_item is None:
                self.selection_rect_item = self.scene().addRect(
                    selection_rect,
                    QPen(QColor(100, 150, 255), 1),
                    QBrush(QColor(100, 150, 255, 50)),
                )
            else:
                self.selection_rect_item.setRect(selection_rect)
            event.accept()
        else:
            self.map_widget.on_minimap_mouse_move(event)
            super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self._handle_middle_press(event):
            return
        if event.button() == Qt.MouseButton.RightButton:
            # Start rotation mode
            items = self.scene().selectedItems()
            valid_items = [i for i in items if isinstance(i, MapUnitItem)]
            if valid_items:
                # Snapshot each item's starting position and rotation
                self.rotation_reference_items = [
                    (item, item.world_x, item.world_y, item.rotation())
                    for item in valid_items
                ]
                # Compute centroid of all selected items' world positions
                avg_x = sum(wx for _, wx, _, _ in self.rotation_reference_items) / len(valid_items)
                avg_y = sum(wy for _, _, wy, _ in self.rotation_reference_items) / len(valid_items)
                self._rotation_pivot_world = QPointF(avg_x, avg_y)
                self._total_delta_so_far = 0.0
                # Draw pivot marker
                self._create_pivot_marker(self._rotation_pivot_world)
                # Disable dragging during rotation
                for item in valid_items:
                    item.setFlag(QGraphicsItem.ItemIsMovable, False)
                # Compute initial angle from cursor to pivot
                pivot_scene = self.map_widget.world_to_scene(int(avg_x), int(avg_y))
                self._last_mouse_angle = self._angle_between(
                    self.mapToScene(event.pos()), pivot_scene)
                self.is_rotating = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            else:
                super().mousePressEvent(event)
        elif event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if isinstance(item, MapUnitItem):
                if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                    item.setSelected(not item.isSelected())
                    event.accept()
                    return
                else:
                    item.setSelected(True)
                    super().mousePressEvent(event)
                    return
            elif isinstance(item, MapObjectiveItem):
                if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                    item.setSelected(not item.isSelected())
                else:
                    item.setSelected(True)
                super().mousePressEvent(event)
                return
            else:
                if self.map_widget._objective_placement_mode:
                    scene_pos = self.mapToScene(event.pos())
                    world_x, world_y = self.map_widget.scene_to_world(
                        scene_pos.x(), scene_pos.y())
                    self.map_widget.add_objective(world_x, world_y)
                    self.map_widget._finish_objective_placement()
                    event.accept()
                    return
                scene_pos = self.mapToScene(event.pos())
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.scene().clearSelection()
                self.selection_start = scene_pos
                self.is_box_selecting = True
                event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._handle_middle_release(event):
            return
        elif event.button() == Qt.MouseButton.RightButton and self.is_rotating:
            self.is_rotating = False
            self._remove_pivot_marker()
            # Restore movable flag on all rotated items
            for item, _, _, _ in self.rotation_reference_items:
                item.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.rotation_reference_items.clear()
            self._rotation_pivot_world = None
            self._last_mouse_angle = None
            self._total_delta_so_far = 0.0
            self.unsetCursor()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.LeftButton and self.is_box_selecting:
            if self.selection_rect_item:
                rect = self.selection_rect_item.rect()
                self.scene().removeItem(self.selection_rect_item)
                self.selection_rect_item = None
                items = self.scene().items(rect)
                for item in items:
                    if isinstance(item, (MapUnitItem, MapObjectiveItem)):
                        item.setSelected(True)
            self.is_box_selecting = False
            self.selection_start = None
            event.accept()
        else:
            item = self.itemAt(event.pos())
            if item is None:
                self.scene().clearSelection()
            super().mouseReleaseEvent(event)

    def _angle_between(self, point1: QPointF, point2: QPointF) -> float:
        """Calculate angle in degrees from point1 to point2."""
        dx = point2.x() - point1.x()
        dy = point2.y() - point1.y()
        return math.degrees(math.atan2(dx, -dy))  # -dy so 0° = North

    def _create_pivot_marker(self, world_pos: QPointF):
        """Draw a zoom-invariant crosshair at the pivot point."""
        scene_pos = self.map_widget.world_to_scene(int(world_pos.x()), int(world_pos.y()))
        self._pivot_marker = QGraphicsItemGroup()
        pen = QPen(QColor(255, 255, 255), 2)
        size = 15
        h_line = QGraphicsLineItem(-size, 0, size, 0)
        v_line = QGraphicsLineItem(0, -size, 0, size)
        h_line.setPen(pen)
        v_line.setPen(pen)
        h_line.setPos(scene_pos)
        v_line.setPos(scene_pos)
        h_line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        v_line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._pivot_marker.addToGroup(h_line)
        self._pivot_marker.addToGroup(v_line)
        circle = QGraphicsEllipseItem(-5, -5, 10, 10)
        circle.setPen(pen)
        circle.setBrush(QBrush(QColor(255, 255, 255, 60)))
        circle.setPos(scene_pos)
        circle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._pivot_marker.addToGroup(circle)
        self._pivot_marker.setZValue(1000)
        self.scene().addItem(self._pivot_marker)

    def _update_pivot_marker_size(self):
        """No-op: pivot marker children use ItemIgnoresTransformations so they
        render at a constant visual size automatically."""
        pass

    def _remove_pivot_marker(self):
        if self._pivot_marker is not None:
            self.scene().removeItem(self._pivot_marker)
            self._pivot_marker = None

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                   Qt.Key.Key_Up, Qt.Key.Key_Down):
            if self.map_widget.navigate_selection(key):
                event.accept()
                return
            # No selection or no valid target — still consume to prevent panning
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-unit-drop"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-unit-drop"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-unit-drop"):
            mime_data = event.mimeData()
            data = mime_data.data("application/x-unit-drop").data()
            unit_info = UnitInfo.from_drag_payload(json.loads(data.decode('utf-8')))
            scene_pos = self.mapToScene(event.pos())
            self.map_widget.place_unit_at_position(scene_pos, unit_info)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, MapUnitItem):
            self.map_widget.show_formation_context_menu(item, event.globalPos())
            event.accept()
        elif isinstance(item, MapObjectiveItem):
            self.map_widget.show_objective_context_menu(item, event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)


class MapUnitItem(QGraphicsItem):
    """
    A worldspace polygon on the minimap, rendered as either a rectangle or
    a hexagonal command shape.

    Level 6 units are rendered as rectangles sized to their formation dimensions.
    Levels 1-5 are rendered as partial or complete hexagons with dot indicators.
    Supports drag, rotate, selection, and hover highlighting.
    """

    DEFAULT_RECT_WIDTH = 2000 # if its a square, something is messed up
    DEFAULT_RECT_HEIGHT = 2000
    CMD_SIZE = 1000
    DOT_RADIUS = 0.1
    SPRITE_SCALE = 6 # usually 1:6 as far as I know. TODO: Expose in gui

    def __init__(self, name: str, unit_row_index: int, side: int, level: int,
                 formation: str, world_x: int, world_y: int, head_count: int = 0,
                 map_widget=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.unit_row_index = unit_row_index
        self.side = side
        self.level = level
        self.formation = formation
        self.world_x = world_x
        self.world_y = world_y
        self.head_count = head_count
        self.map_widget = map_widget
        self.is_hovered = False
        self.is_highlighted = False

        self._scene_polygon: Optional[QPolygonF] = None
        self._scene_path: Optional[QPainterPath] = None
        self._cmd_world_verts: list = []
        self._command_dots: list = []
        self._scene_dots: list = []
        self._label: str = ""

        # Compute rectangle dimensions from formation if available
        self.world_width = self.DEFAULT_RECT_WIDTH
        self.world_height = self.DEFAULT_RECT_HEIGHT
        self.origin_offset_x = self.DEFAULT_RECT_WIDTH / 2
        self.origin_offset_y = self.DEFAULT_RECT_HEIGHT / 2

        self.refresh_dimensions()
        
        self.setData(Qt.UserRole, unit_row_index)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setRotation(0)
        self._rebuild_scene_geometry()

    def set_label(self, label: str):
        self._label = label
        self.update()

    def refresh_dimensions(self, archetype_id: str = None):
        formation_id = archetype_id if archetype_id is not None else self.formation
        if not formation_id or formation_id not in FormationArchetype.formations:
            return
        try:
            if self.map_widget and self.map_widget.oob_data:
                af = self.map_widget.build_strength(self.unit_row_index, archetype_id=formation_id)
            else:
                af = ActualFormation(archetype_id=formation_id, strength=int(self.head_count / self.SPRITE_SCALE))
            length_yards, depth_yards = af.get_dimensions()
            upy = self.map_widget.units_per_yard if self.map_widget else 30
            self.world_width = length_yards * upy
            self.world_height = depth_yards * upy
            self.origin_offset_x = af.origin_offset_x * upy
            self.origin_offset_y = af.origin_offset_y * upy
        except Exception:
            pass

    def _build_command_shape(self, level, cx, cy, size):
        """Return (QPainterPath, list[(wx, wy)]) for a command-level shape.

        All shapes use the same radius r = size / 2. Flat-top hexagon for levels
        with flat top (1, 2, 4); pointy-top for levels with pointy top (3, 5).
        Shapes are OPEN paths (no fill) with gaps where sides are missing.
        """
        import math
        r = size / 2.0
        h = r * math.sqrt(3) / 2.0  # height of equilateral triangle side r

        # Flat-top hexagon vertices (y-up coordinate system for math, then flip for Qt)
        # V0=right, V1=top-right, V2=top-left, V3=left, V4=bottom-left, V5=bottom-right
        V0_f = (cx + r, cy)
        V1_f = (cx + r / 2, cy - h)
        V2_f = (cx - r / 2, cy - h)
        V3_f = (cx - r, cy)
        V4_f = (cx - r / 2, cy + h)
        V5_f = (cx + r / 2, cy + h)

        # Pointy-top hexagon vertices (V0=top, V1=top-right, V2=bottom-right, V3=bottom, V4=bottom-left, V5=top-left)
        V0_p = (cx, cy - r)
        V1_p = (cx + h, cy - r / 2)
        V2_p = (cx + h, cy + r / 2)
        V3_p = (cx, cy + r)
        V4_p = (cx - h, cy + r / 2)
        V5_p = (cx - h, cy - r / 2)

        # Dot distance from center (fraction of radius)
        d = r * 0.35

        path = QPainterPath()
        dots = []

        if level == 5:
            # ^ shape: pointy-top, top two edges meeting at top vertex
            path.moveTo(V5_p[0], V5_p[1])
            path.lineTo(V0_p[0], V0_p[1])
            path.lineTo(V1_p[0], V1_p[1])
            dots = [(cx, cy)]

        elif level == 4:
            # Flat top + two angled upper edges (top half of flat-top hex)
            path.moveTo(V3_f[0], V3_f[1])  # left vert
            path.lineTo(V2_f[0], V2_f[1])  # upper left line
            path.lineTo(V1_f[0], V1_f[1])  # top flat (left to right)
            path.lineTo(V0_f[0], V0_f[1])  # upper right line
            dots = [(cx - d, cy), (cx + d, cy)]

        elif level == 3:
            # Pointed-top, 4 edges: Symmetric shape with a vertex (point) above the origin
            path.moveTo(V4_p[0], V4_p[1])
            path.lineTo(V5_p[0], V5_p[1])  # left edge
            path.lineTo(V0_p[0], V0_p[1])  # top-left edge
            path.lineTo(V1_p[0], V1_p[1])  # top-right edge
            path.lineTo(V2_p[0], V2_p[1])  # right edge
            dots = [
                (cx, cy - d),
                (cx - d * math.cos(math.radians(30)), cy + d * math.sin(math.radians(30))),
                (cx + d * math.cos(math.radians(30)), cy + d * math.sin(math.radians(30))),
            ]

        elif level == 2:
            # Flat-top, all edges except bottom flat (5 edges)
            path.moveTo(V4_f[0], V4_f[1])  # bottom left vert
            path.lineTo(V3_f[0], V3_f[1])  # lower left line
            path.lineTo(V2_f[0], V2_f[1])  # upper left line
            path.lineTo(V1_f[0], V1_f[1])  # top line
            path.lineTo(V0_f[0], V0_f[1])  # upper right line
            path.lineTo(V5_f[0], V5_f[1])  # bottom right line
            bx = d * 0.75
            by = d * 0.6
            dots = [
                (cx - bx, cy - by),
                (cx + bx, cy - by),
                (cx - bx, cy + by),
                (cx + bx, cy + by),
            ]

        elif level == 1:
            # Complete flat-top hexagon (6 edges)
            path.moveTo(V1_f[0], V1_f[1])
            path.lineTo(V2_f[0], V2_f[1])  # top flat
            path.lineTo(V3_f[0], V3_f[1])  # upper left
            path.lineTo(V4_f[0], V4_f[1])  # lower left
            path.lineTo(V5_f[0], V5_f[1])  # bottom flat
            path.lineTo(V0_f[0], V0_f[1])  # lower right
            path.lineTo(V1_f[0], V1_f[1])  # upper right (closes)
            dots = [
                (cx, cy - d),
                (cx - d * math.sin(math.radians(72)), cy - d * math.cos(math.radians(72))),
                (cx + d * math.sin(math.radians(72)), cy - d * math.cos(math.radians(72))),
                (cx - d * math.sin(math.radians(36)), cy + d * math.cos(math.radians(36))),
                (cx + d * math.sin(math.radians(36)), cy + d * math.cos(math.radians(36))),
            ]

        else:
            path.moveTo(V5_p[0], V5_p[1])
            path.lineTo(V0_p[0], V0_p[1])
            path.lineTo(V1_p[0], V1_p[1])

        return path, dots

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
        else:
            path, dots_world = self._build_command_shape(
                self.level, self.world_x, self.world_y, self.CMD_SIZE)
            self._cmd_world_path = path
            self._cmd_world_verts = None
            self._command_dots = list(dots_world)
        self._refresh_scene_coords()

    def _refresh_scene_coords(self):
        """Rebuild _scene_polygon, _scene_path, and _scene_dots from stored world coords."""
        if self.map_widget is None:
            return
        item_pos = self.pos()
        poly = QPolygonF()
        path = QPainterPath()

        if self.level == 6:
            # Level 6: rectangle from world verts
            if hasattr(self, '_cmd_world_verts') and self._cmd_world_verts:
                for wx, wy in self._cmd_world_verts:
                    sp = self.map_widget.world_to_scene(wx, wy)
                    p = sp - item_pos
                    poly.append(p)
                # Build closed path for hit testing
                if poly.size() >= 2:
                    path.moveTo(poly[0])
                    for i in range(1, poly.size()):
                        path.lineTo(poly[i])
                    path.closeSubpath()
        else:
            # Levels 1-5: path from world path
            if hasattr(self, '_cmd_world_path') and self._cmd_world_path is not None:
                path_world = self._cmd_world_path
                scene_path = QPainterPath()
                first = True
                for i in range(path_world.elementCount()):
                    elem = path_world.elementAt(i)
                    sp = self.map_widget.world_to_scene(elem.x, elem.y)
                    p = sp - item_pos
                    if first:
                        scene_path.moveTo(p.x(), p.y())
                        first = False
                    else:
                        scene_path.lineTo(p.x(), p.y())
                path = scene_path

        self._scene_polygon = poly
        self._scene_path = path if not path.isEmpty() else None

        # Scene-space stroke width for hex lines (levels 1-5).
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

        # Convert dot world coords to scene coords
        self._scene_dots = []
        for wx, wy in self._command_dots:
            sp = self.map_widget.world_to_scene(wx, wy)
            p = sp - item_pos
            self._scene_dots.append((p.x(), p.y()))

    def update_from_world(self):
        self._rebuild_scene_geometry()
        self.update()

    def boundingRect(self):
        if self.level < 6:
            if self.map_widget:
                center = self.map_widget.world_to_scene(self.world_x, self.world_y)
                corner = self.map_widget.world_to_scene(
                    self.world_x + self.CMD_SIZE / 2, self.world_y + self.CMD_SIZE / 2)
                half = max(abs(corner.x() - center.x()),
                           abs(corner.y() - center.y()))
            else:
                half = self.CMD_SIZE / 2
            return QRectF(-half, -half, half * 2, half * 2)
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            rect = self._scene_polygon.boundingRect()
            for dx, dy in self._scene_dots:
                rect = rect.united(QRectF(dx - self.DOT_RADIUS, dy - self.DOT_RADIUS,
                                          self.DOT_RADIUS * 2, self.DOT_RADIUS * 2))
            return rect.adjusted(-5, -5, 5, 5)
        return QRectF()

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self.level < 6:
            path.addRect(self.boundingRect())
            return path
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            path.addPolygon(self._scene_polygon)
            path.closeSubpath()
        return path

    def paint(self, painter: QPainter, option, widget=None):
        if (self._scene_polygon is None or self._scene_polygon.isEmpty()) and \
           (self._scene_path is None or self._scene_path.isEmpty()):
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

        path = self._scene_path
        
        if self.level !=6:  # use path around the stroked (enthickened) path
            stroker = QPainterPathStroker()
            stroker.setWidth(self._scene_stroke_width)
            path = stroker.createStroke(self._scene_path)

        # two-pass rendering.
        # Pass 1: thin border along the open path (no brush).
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        # Pass 2: fill the stroked body (no pen — hides vertex artifacts).
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(side_color))
        painter.drawPath(path)


        # Draw command dots (levels 1-5).
        if self._scene_dots:
            painter.setPen(QPen(QColor("#ffffff"), 0.02))
            painter.setBrush(QBrush(QColor("#ffffff")))
            for dx, dy in self._scene_dots:
                painter.drawEllipse(QPointF(dx, dy), self.DOT_RADIUS, self.DOT_RADIUS)

        if self._label and self._scene_polygon is not None and self._scene_polygon.size() > 0:
            center = self._scene_polygon.boundingRect().center()
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(center, self._label)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def set_highlighted(self, highlighted: bool):
        self.is_highlighted = highlighted
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.map_widget is not None:
            self.world_x, self.world_y = self.map_widget.scene_to_world(value.x(), value.y())
            self._rebuild_scene_geometry()
        return super().itemChange(change, value)


class OOBMapWidget(QWidget):
    """Widget for displaying map information and minimap visualization."""

    unit_placed = Signal(int, int, int)
    unit_selected = Signal(int)
    drills_loaded = Signal(str)
    objective_placed = Signal(int)
    objective_removed = Signal(int)
    objective_moved = Signal(int, int, int)
    map_loaded = Signal(str)

    def __init__(self, oob_data=None, parent=None, map_ini: str = "", drills: str = ""):
        super().__init__(parent)
        self.oob_data = oob_data
        self.map_ini_path = map_ini
        self.drills_path = drills

        self.lsl_path = None
        self.minimap_path = None
        self.tga_width = None
        self.tga_height = None
        self.minimap_pixmap = None
        self.grayscale_pixmap = None
        self.showing_grayscale = False
        self.minimap_pixmap_item = None
        self.minimap_display_size = None
        self._scaled_pixmap_cache = None
        self._scaled_pixmap_cache_key: Optional[Tuple[int, int, int]] = None
        self.tile_scale = 512
        self.units_per_yard = 30

        self.placed_units: List[MapUnitItem] = []
        self.placed_row_indices: set = set()
        self.placed_by_row: Dict[int, MapUnitItem] = {}
        self._highlighted: set = set()
        self.unit_count_label = None

        self.placed_objectives: List[MapObjectiveItem] = []
        self.placed_objective_ids: set = set()
        self.objectives_by_id: Dict[int, MapObjectiveItem] = {}
        self._next_objective_id: int = 1
        self._objective_placement_mode: bool = False

        self.init_ui()
        if map_ini:
            self.load_map_from_ini(map_ini)
        if drills:
            self._load_formations(drills)

    def init_ui(self):
        main_layout = QVBoxLayout()

        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(8)

        self.load_button = QPushButton("Load Map")
        self.load_button.clicked.connect(self.load_map)
        control_layout.addWidget(self.load_button)

        tile_scale_label = QLabel("Tile Scale:")
        control_layout.addWidget(tile_scale_label)

        self.tile_scale_spinbox = QSpinBox()
        self.tile_scale_spinbox.setMinimum(1)
        self.tile_scale_spinbox.setMaximum(4096)
        self.tile_scale_spinbox.setValue(512)
        self.tile_scale_spinbox.setToolTip("Default: 512. Controls coordinate scaling.")
        self.tile_scale_spinbox.valueChanged.connect(self.on_tile_scale_changed)
        control_layout.addWidget(self.tile_scale_spinbox)

        upy_label = QLabel("Units Per Yard:")
        control_layout.addWidget(upy_label)

        self.units_per_yard_spinbox = QSpinBox()
        self.units_per_yard_spinbox.setMinimum(1)
        self.units_per_yard_spinbox.setMaximum(256)
        self.units_per_yard_spinbox.setValue(30)
        self.units_per_yard_spinbox.setToolTip("Default: 30. Units displayed per yard on the map.")
        self.units_per_yard_spinbox.valueChanged.connect(self.on_units_per_yard_changed)
        control_layout.addWidget(self.units_per_yard_spinbox)

        self.unit_count_label = QLabel("Units: 0")
        self.unit_count_label.setMaximumWidth(100)
        control_layout.addWidget(self.unit_count_label)

        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_all_units)
        clear_button.setMaximumWidth(100)
        control_layout.addWidget(clear_button)

        self.swap_button = QPushButton("Swap to Grayscale")
        self.swap_button.clicked.connect(self.on_swap_graphics)
        self.swap_button.setEnabled(False)
        self.swap_button.setMaximumWidth(140)
        control_layout.addWidget(self.swap_button)

        self.place_objective_button = QPushButton("Place Objective")
        self.place_objective_button.clicked.connect(self.start_objective_placement)
        self.place_objective_button.setMaximumWidth(120)
        control_layout.addWidget(self.place_objective_button)

        opacity_label = QLabel("Opacity:")
        control_layout.addWidget(opacity_label)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setMaximumWidth(120)
        self.opacity_slider.setToolTip("Loaded minimap opacity")
        self.opacity_slider.valueChanged.connect(self.on_minimap_opacity_changed)
        control_layout.addWidget(self.opacity_slider)

        control_layout.addStretch()

        control_widget = QWidget()
        control_widget.setLayout(control_layout)
        main_layout.addWidget(control_widget, 0)

        self.info_label = QLabel("No map loaded")
        main_layout.addWidget(self.info_label, 0)

        self.minimap_scene = QGraphicsScene()
        self.minimap_view = OOBMapGraphicsView(self.minimap_scene, self)
        self.minimap_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minimap_view.setRenderHints(self.minimap_view.renderHints() | QPainter.Antialiasing)
        self.minimap_view.setMouseTracking(True)
        self.minimap_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.minimap_view.setStyleSheet("border: 1px solid #333333; background-color: #1a1a1a;")
        self.minimap_view.setAcceptDrops(True)
        main_layout.addWidget(self.minimap_view, 1)

        coord_layout = QHBoxLayout()
        coord_layout.setContentsMargins(0, 0, 0, 0)
        coord_layout.setSpacing(8)

        self.coord_label = QLabel("Coordinates: --")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.coord_label.setFont(font)
        self.coord_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        coord_layout.addWidget(self.coord_label)

        self.zoom_selected_button = QPushButton("Zoom To Selected")
        self.zoom_selected_button.setMaximumWidth(120)
        self.zoom_selected_button.clicked.connect(self._on_zoom_to_selected)
        coord_layout.addWidget(self.zoom_selected_button)

        self.name_label = QLabel("Selected: --")
        name_label_font = QFont()
        name_label_font.setPointSize(10)
        name_label_font.setBold(True)
        self.name_label.setFont(name_label_font)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        coord_layout.addWidget(self.name_label, 1)

        coord_widget = QWidget()
        coord_widget.setLayout(coord_layout)
        main_layout.addWidget(coord_widget, 0)

        self.minimap_scene.selectionChanged.connect(self._on_scene_selection_changed)

        self.setLayout(main_layout)

    def load_map(self):
        # current_dir = os.path.curdir
        ini_path, _ = QFileDialog.getOpenFileName(
            self, "Open Map Configuration", "", "INI Files (*.ini)")
        if not ini_path:
            return
        try:
            self.load_map_from_ini(ini_path)
        except Exception as e:
            QMessageBox.critical(self, "Map Load Error",
                                 f"Failed to load map configuration:\n{ini_path}\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def load_formations_dialog(self, csv_path=None):
        # current_dir = os.path.curdir
        csv_path, _ = QFileDialog.getOpenFileName(
            self, "Open Formations CSV", "", "CSV Files (*.csv)")
        self._load_formations(csv_path)

    def _load_formations(self, csv_path):
        if not csv_path:
            return
        try:
            from core.formation import populate_formation_archetypes_from_csv
            populate_formation_archetypes_from_csv(csv_path)
            self.drills_path = csv_path
            self.drills_loaded.emit(csv_path)
        except Exception as e:
            QMessageBox.critical(self, "Formations Load Error",
                                 f"Failed to load formations from:\n{csv_path}\n\n"
                                 f"Error: {type(e).__name__}: {str(e)}\n\n"
                                 f"Stack trace:\n{traceback.format_exc()}")

    def load_map_from_ini(self, ini_path: str):
        ini_path = Path(ini_path)
        if not ini_path.exists():
            raise FileNotFoundError(f"INI file not found: {ini_path}")

        config = configparser.ConfigParser()
        config.read(str(ini_path))

        if "Files" not in config:
            raise KeyError("Missing [Files] section in INI file")
        files_section = config["Files"]
        if "LSLFile" not in files_section:
            raise KeyError("Missing LSLFile field in [Files] section")
        if "Minimap" not in files_section:
            raise KeyError("Missing Minimap field in [Files] section")

        base_dir = ini_path.parent
        lsl_path = base_dir / files_section["LSLFile"]
        minimap_path = base_dir / files_section["Minimap"]

        if not lsl_path.exists():
            raise FileNotFoundError(f"LSL file not found: {lsl_path}")
        if not minimap_path.exists():
            raise FileNotFoundError(f"Minimap file not found: {minimap_path}")

        self.tga_width, self.tga_height = get_tga_dimensions(str(lsl_path))

        if minimap_path.suffix.lower() == ".dds":
            img = Image.open(str(minimap_path)).convert("RGBA")
            width, height = img.size
            data = img.tobytes("raw", "RGBA")
            self.minimap_pixmap = QPixmap.fromImage(
                QImage(data, width, height, QImage.Format.Format_RGBA8888))
        else:
            self.minimap_pixmap = QPixmap(str(minimap_path))

        if self.minimap_pixmap.isNull():
            raise ValueError(f"Failed to load minimap image: {minimap_path}")

        # Invalidate the scaled-pixmap cache whenever the source changes.
        self._scaled_pixmap_cache = None
        self._scaled_pixmap_cache_key = None

        grayscale_file = files_section.get("Grayscale", "")
        if grayscale_file:
            grayscale_path = base_dir / grayscale_file
            if grayscale_path.exists():
                self.grayscale_pixmap = QPixmap(str(grayscale_path))
                if self.grayscale_pixmap.isNull():
                    self.grayscale_pixmap = None
            else:
                self.grayscale_pixmap = None
        else:
            self.grayscale_pixmap = None

        self.showing_grayscale = False
        self.swap_button.setEnabled(self.grayscale_pixmap is not None)
        self.swap_button.setText("Swap to Grayscale")

        self.display_minimap()

        self.map_ini_path = ini_path
        self.lsl_path = lsl_path
        self.minimap_path = minimap_path

        map_name = ini_path.stem
        self.info_label.setText(
            f"Loaded: {map_name} | LSL: {files_section['LSLFile']} | "
            f"Minimap: {files_section['Minimap']} | "
            f"TGA Dimensions: {self.tga_width}x{self.tga_height}")

        self.map_loaded.emit(str(ini_path))

    def display_minimap(self):
        if self.minimap_pixmap is None:
            return

        pixmap = self.grayscale_pixmap if self.showing_grayscale else self.minimap_pixmap
        self.minimap_display_size = (pixmap.width(), pixmap.height())

        view_size = self.minimap_view.size()
        if view_size.width() <= 0 or view_size.height() <= 0:
            view_size.setWidth(400)
            view_size.setHeight(400)

        cache_key = (id(pixmap), view_size.width(), view_size.height())
        if cache_key != self._scaled_pixmap_cache_key:
            scaled_pixmap = pixmap.scaled(
                view_size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._scaled_pixmap_cache = scaled_pixmap
            self._scaled_pixmap_cache_key = cache_key

        # Swap the pixmap item only if the cache changed (or none exists yet).
        if (self.minimap_pixmap_item is None
                or self.minimap_pixmap_item.pixmap().cacheKey() != self._scaled_pixmap_cache.cacheKey()):
            if self.minimap_pixmap_item is not None:
                self.minimap_scene.removeItem(self.minimap_pixmap_item)
            self.minimap_pixmap_item = self.minimap_scene.addPixmap(self._scaled_pixmap_cache)
            self.minimap_pixmap_item.setPos(0, 0)
            self.minimap_pixmap_item.setOpacity(self.opacity_slider.value() / 100.0)
            self.minimap_pixmap_item.setZValue(-10)

        self._update_placed_unit_positions()

    def on_minimap_mouse_move(self, event):
        if self.minimap_pixmap is None or self.tga_width is None:
            return

        scene_pos = self.minimap_view.mapToScene(event.pos())
        scene_rect = self.minimap_scene.sceneRect()

        if not scene_rect.contains(scene_pos):
            self.coord_label.setText("Coordinates: --")
            return

        pixmap_item = self.minimap_pixmap_item
        if pixmap_item is None:
            self.coord_label.setText("Coordinates: --")
            return

        pixmap_width = pixmap_item.boundingRect().width()
        pixmap_height = pixmap_item.boundingRect().height()

        pixmap_pos = pixmap_item.pos()
        adjusted_pixel_x = scene_pos.x() - pixmap_pos.x()
        adjusted_pixel_y = scene_pos.y() - pixmap_pos.y()

        if adjusted_pixel_x < 0 or adjusted_pixel_y < 0 or adjusted_pixel_x >= pixmap_width or adjusted_pixel_y >= pixmap_height:
            self.coord_label.setText("Coordinates: --")
            return

        adjusted_pixel_x = max(0, min(adjusted_pixel_x, pixmap_width - 1))
        adjusted_pixel_y = max(0, min(adjusted_pixel_y, pixmap_height - 1))

        world_x = int((adjusted_pixel_x / pixmap_width) * (self.tile_scale * self.tga_width))
        world_y = int((adjusted_pixel_y / pixmap_height) * (self.tile_scale * self.tga_height))

        self.coord_label.setText(f"Coordinates: ({world_x}, {world_y})")

    def on_tile_scale_changed(self, value: int):
        self.tile_scale = value
        self._update_placed_unit_positions()

    def on_units_per_yard_changed(self, value: int):
        self.units_per_yard = value

    def on_minimap_opacity_changed(self, value: int):
        if self.minimap_pixmap_item is not None:
            self.minimap_pixmap_item.setOpacity(value / 100.0)

    def on_swap_graphics(self):
        if self.grayscale_pixmap is None:
            return
        self.showing_grayscale = not self.showing_grayscale
        self.swap_button.setText(
            "Swap to Minimap" if self.showing_grayscale else "Swap to Grayscale")
        self.display_minimap()

    # ==================== Unit Placement Methods ====================

    def place_unit_at_position(self, scene_pos: QPointF, unit_info: UnitInfo):
        scene_rect = self.minimap_scene.sceneRect()
        if not scene_rect.contains(scene_pos):
            return

        row_index = unit_info.row_index

        if row_index in self.placed_row_indices:
            QMessageBox.information(
                self, "Duplicate Unit",
                f"{unit_info.name} has already been placed on the map.\n"
                f"Each unit can only be placed once.")
            return

        world_x, world_y = self.scene_to_world(scene_pos.x(), scene_pos.y())
        self._place_unit(unit_info, world_x, world_y)

    def world_to_scene(self, world_x: int, world_y: int) -> QPointF:
        if self.tga_width is None or self.tga_height is None or self.minimap_pixmap_item is None:
            return QPointF(0, 0)
        pixmap_rect = self.minimap_pixmap_item.boundingRect()
        pixmap_pos = self.minimap_pixmap_item.pos()
        world_width = self.tile_scale * self.tga_width
        world_height = self.tile_scale * self.tga_height
        scene_x = pixmap_pos.x() + (world_x / world_width) * pixmap_rect.width()
        scene_y = pixmap_pos.y() + (world_y / world_height) * pixmap_rect.height()
        return QPointF(scene_x, scene_y)

    def scene_to_world(self, scene_x: float, scene_y: float) -> Tuple[int, int]:
        if self.tga_width is None or self.tga_height is None or self.minimap_pixmap_item is None:
            return 0, 0
        pixmap_rect = self.minimap_pixmap_item.boundingRect()
        pixmap_pos = self.minimap_pixmap_item.pos()
        world_width = self.tile_scale * self.tga_width
        world_height = self.tile_scale * self.tga_height
        scene_offset_x = scene_x - pixmap_pos.x()
        scene_offset_y = scene_y - pixmap_pos.y()
        world_x = int((scene_offset_x / pixmap_rect.width()) * world_width)
        world_y = int((scene_offset_y / pixmap_rect.height()) * world_height)
        return world_x, world_y

    def _place_unit(self, unit_info: UnitInfo, world_x: int, world_y: int):
        row_index = unit_info.row_index
        level = unit_info.level if unit_info.level is not None else 1

        unit_item = MapUnitItem(
            name=unit_info.name, unit_row_index=row_index, side=unit_info.side,
            level=level, formation=unit_info.formation, world_x=world_x,
            world_y=world_y, head_count=unit_info.head_count, map_widget=self)

        scene_pos = self.world_to_scene(world_x, world_y)
        unit_item.setPos(scene_pos)
        unit_item.setZValue(7 - level)  # level 1 = top (z6), level 6 = bottom (z1)
        unit_item._rebuild_scene_geometry()

        self.minimap_scene.addItem(unit_item)
        self.placed_units.append(unit_item)
        self.placed_row_indices.add(row_index)
        self.placed_by_row[row_index] = unit_item

        self._update_unit_count()
        self.unit_placed.emit(row_index, world_x, world_y)

    def build_strength(self, row_index: int, archetype_id: str = None) -> ActualFormation:
        return self.oob_data.build_strength(row_index, archetype_id=archetype_id)

    def _update_placed_unit_positions(self):
        for unit_item in self.placed_units:
            scene_pos = self.world_to_scene(unit_item.world_x, unit_item.world_y)
            unit_item.setPos(scene_pos)

    def _update_unit_count(self):
        count = len(self.placed_units)
        self.unit_count_label.setText(f"Units: {count}")

    def _on_scene_selection_changed(self):
        items = self.minimap_scene.selectedItems()
        map_items = [i for i in items if isinstance(i, MapUnitItem)]
        if not map_items:
            self.name_label.setText("Selected: --")
            self.highlight_unit(None)
            return
        if len(map_items) == 1:
            unit = map_items[0]
            formation_text = f" | Formation: {unit.formation}" if unit.formation else " | Formation: (none)"
            self.name_label.setText(f"Selected: {unit.name}{formation_text}")
            self.highlight_unit(unit.unit_row_index)
            self.unit_selected.emit(unit.unit_row_index)
            return
        self.name_label.setText(f"Selected: {len(map_items)} units")
        self.highlight_unit(None)

    def select_unit(self, row_index: int) -> None:
        selected_map_items = [i for i in self.minimap_scene.selectedItems() if isinstance(i, MapUnitItem)]
        if len(selected_map_items) == 1 and selected_map_items[0].unit_row_index == row_index:
            return
        placed_unit = self.placed_by_row.get(row_index)
        if placed_unit is not None:
            self.minimap_scene.clearSelection()
            placed_unit.setSelected(True)

    # ── Arrow-key navigation ──────────────────────────────────────

    def navigate_selection(self, key) -> bool:
        """Move selection up/down/left/right through the placed-unit hierarchy.
        Returns True if selection changed, False otherwise.
        """
        current = [i for i in self.minimap_scene.selectedItems()
                   if isinstance(i, MapUnitItem)]
        if not current:
            return False
        current_idx = self._highest_ranked([i.unit_row_index for i in current])

        if key == Qt.Key.Key_Up:
            new_idx = self._find_parent(current_idx)
        elif key == Qt.Key.Key_Down:
            new_idx = self._find_first_child(current_idx)
        elif key == Qt.Key.Key_Right:
            new_idx = self._find_next_peer(current_idx)
        elif key == Qt.Key.Key_Left:
            new_idx = self._find_prev_peer(current_idx)
        else:
            return False

        if new_idx is None or new_idx == current_idx:
            return False
        self.select_unit(new_idx)
        # Center the view on the newly selected unit
        unit_item = self.placed_by_row.get(new_idx)
        if unit_item is not None:
            self.minimap_view.centerOn(unit_item)
        return True

    def _find_parent(self, row_index: int) -> Optional[int]:
        hk = self.oob_data.get_hierarchy_key_by_index(row_index)
        parent_key = self.oob_data.get_parent_key(hk)
        parent_idx = self.oob_data.get_row_index_by_key(parent_key)
        if parent_idx is None:
            return None
        return parent_idx if parent_idx in self.placed_by_row else None

    def _find_first_child(self, row_index: int) -> Optional[int]:
        children = self.oob_data._parent_to_children.get(row_index, [])
        for child_idx in children:
            if child_idx in self.placed_by_row:
                return child_idx
        return None

    def _find_next_peer(self, row_index: int) -> Optional[int]:
        peers = self._get_peer_indices(row_index)
        return self._next_placed_peer(peers, row_index, forward=True)

    def _find_prev_peer(self, row_index: int) -> Optional[int]:
        peers = self._get_peer_indices(row_index)
        return self._next_placed_peer(peers, row_index, forward=False)

    def _get_peer_indices(self, row_index: int) -> List[int]:
        hk = self.oob_data.get_hierarchy_key_by_index(row_index)
        parent_key = self.oob_data.get_parent_key(hk)
        parent_idx = self.oob_data.get_row_index_by_key(parent_key)
        if parent_idx is None:
            return [idx for idx in range(len(self.oob_data.df))
                    if self.oob_data.get_level(idx) is not None
                    and idx not in self.oob_data._children_set]
        return self.oob_data._parent_to_children.get(parent_idx, [])

    def _next_placed_peer(self, peers: List[int], current_idx: int,
                          forward: bool) -> Optional[int]:
        placed_peers = [p for p in peers if p in self.placed_by_row]
        if not placed_peers:
            return None
        if current_idx not in placed_peers:
            return placed_peers[0] if forward else placed_peers[-1]
        pos = placed_peers.index(current_idx)
        if forward:
            return placed_peers[(pos + 1) % len(placed_peers)]
        else:
            return placed_peers[(pos - 1) % len(placed_peers)]

    def _highest_ranked(self, row_indices: List[int]) -> int:
        """Return the row_index with the lowest hierarchy level (most senior).
        Among units at the same level, the one with the lowest row index wins.
        """
        def _rank(idx):
            level = self.oob_data.get_level(idx)
            return (level if level is not None else 999, idx)
        return min(row_indices, key=_rank)

    def highlight_unit(self, row_index):
        if row_index is None or self.oob_data is None:
            new_set: set = set()
        else:
            try:
                subordinate_indices = self.oob_data.get_subordinate_row_indices(row_index)
            except Exception:
                subordinate_indices = [row_index]
            new_set = {idx for idx in subordinate_indices if idx in self.placed_by_row}
        # Diff: only touch items whose state actually changed AND that still exist.
        all_current = set(self.placed_by_row.keys())
        for idx in (self._highlighted - new_set) & all_current:
            self.placed_by_row[idx].set_highlighted(False)
        for idx in (new_set - self._highlighted) & all_current:
            self.placed_by_row[idx].set_highlighted(True)
        self._highlighted = new_set & all_current

    def clear_all_units(self):
        reply = QMessageBox.question(
            self, "Clear All", "Remove all placed units?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._clear_all_units()

    def _clear_all_units(self):
        for unit_item in self.placed_units:
            self.minimap_scene.removeItem(unit_item)
        self.placed_units.clear()
        self.placed_row_indices.clear()
        self.placed_by_row.clear()
        self._highlighted.clear()
        self._update_unit_count()

    def remove_units_by_row_indices(self, row_indices):
        """Remove placed units whose row_index is in *row_indices*."""
        to_remove = {idx for idx in row_indices if idx in self.placed_by_row}
        if not to_remove:
            return
        # Remove from scene and discard from dicts.
        for idx in to_remove:
            item = self.placed_by_row.pop(idx)
            self.placed_row_indices.discard(idx)
            self.minimap_scene.removeItem(item)
        # Filter placed_units once — O(P) instead of O(k*P).
        self.placed_units = [u for u in self.placed_units if u.unit_row_index not in to_remove]
        self._highlighted -= to_remove
        self._update_unit_count()

    def shift_placed_unit_indices(self, deleted_row_indices):
        """Recompute row indices of remaining placed units after rows were deleted.

        When rows are removed from the DataFrame, all row indices above the
        deleted rows shift down.  This method adjusts the ``unit_row_index``
        of every remaining placed unit and rebuilds the lookup dicts.
        """
        deleted_set = set(deleted_row_indices)
        self.placed_by_row.clear()
        self.placed_row_indices.clear()
        for unit in self.placed_units:
            idx = unit.unit_row_index
            shift = sum(1 for d in deleted_set if d < idx)
            unit.unit_row_index -= shift
            self.placed_by_row[unit.unit_row_index] = unit
            self.placed_row_indices.add(unit.unit_row_index)

    def get_placed_units_data(self) -> List[Dict]:
        return [
            {
                "row_index": u.unit_row_index,
                "name": u.name,
                "side": u.side,
                "level": u.level,
                "world_x": u.world_x,
                "world_y": u.world_y,
                "rotation": u.rotation(),
                "formation": u.formation,
            }
            for u in self.placed_units
        ]

    def show_formation_context_menu(self, unit_item: MapUnitItem, global_pos):
        if self.oob_data is None:
            QMessageBox.warning(self, "Error", "OOB data not loaded. Cannot apply formations.")
            return

        self.minimap_scene.clearSelection()
        unit_item.setSelected(True)

        target_level = max(unit_item.level, 3)
        available = [a for a in FormationArchetype.formations.values()
                     if f"DRIL_Lvl{target_level}" in a.drill_id]
        available.sort(key=lambda a: a.name)

        current_arch = next((a for a in available if a.drill_id == unit_item.formation), None)
        oob_default = self.oob_data.get_row(unit_item.unit_row_index).get("Formation", "")
        default_arch = next((a for a in available if a.drill_id == oob_default), None)

        def category_for(arch):
            did = arch.drill_id
            if "Inf" in did:
                return "Inf"
            if "Cav" in did:
                return "Cav"
            if "Art" in did:
                return "Art"
            return "Misc"

        categories = {"Inf": [], "Cav": [], "Art": [], "Misc": []}
        for arch in available:
            categories[category_for(arch)].append(arch)

        menu = QMenu(self)
        if current_arch is not None:
            current_action = menu.addAction(f"{current_arch.drill_id} (current)")
            current_action.triggered.connect(
                lambda _checked=False, did=current_arch.drill_id: self.apply_formation(unit_item, did))
        if default_arch is not None:
            default_action = menu.addAction(f"{default_arch.drill_id} (default)")
            default_action.triggered.connect(
                lambda _checked=False, did=default_arch.drill_id: self.apply_formation(unit_item, did))
        if current_arch is not None or default_arch is not None:
            menu.addSeparator()
        for cat_key, cat_label in [("Inf", "Infantry"),
                                    ("Cav", "Cavalry"),
                                    ("Art", "Artillery"),
                                    ("Misc", "Miscellaneous")]:
            count = len(categories[cat_key])
            submenu = menu.addMenu(f"{cat_label} ({count})")
            if not categories[cat_key]:
                submenu.setEnabled(False)
            else:
                for arch in categories[cat_key]:
                    action = submenu.addAction(arch.drill_id)
                    action.triggered.connect(
                        lambda _checked=False, did=arch.drill_id: self.apply_formation(unit_item, did))
        menu.addSeparator()
        menu.addAction("Cancel")

        menu.exec(global_pos)

    def apply_formation(self, parent_unit_item: MapUnitItem, formation_type: str):
        if self.oob_data is None:
            QMessageBox.warning(self, "Error", "OOB data not loaded.")
            return
        try:
            parent_row_index = parent_unit_item.unit_row_index
            parent_row = self.oob_data.get_row(parent_row_index)

            parent_formation = self.build_strength(parent_row_index, archetype_id=formation_type)
            positions = parent_formation.get_positions()

            parent_unit_item.formation = formation_type
            parent_unit_item.refresh_dimensions(archetype_id=formation_type)
            parent_unit_item._rebuild_scene_geometry()

            parent_archetype = FormationArchetype.formations.get(formation_type)
            parent_level = self.oob_data.get_level(parent_row_index)
            if parent_level is not None and parent_level < 3: # Hack to allow lvl3 formations to be used on lvl1 or lvl2 units.
                child_formation_type = formation_type
            else:
                child_formation_type = parent_archetype.sub_form if parent_archetype and parent_archetype.sub_form else None

            if not positions:
                QMessageBox.information(self, "No Positions",
                                        "Formation has no valid positions to apply.")
                return

            seq_to_sub = {1: (parent_row_index, parent_row)}

            # Direct children only, excluding supply wagons.
            direct_children = self.oob_data.get_direct_children(
                parent_row_index, exclude_supply=True)

            for i, sub_row_index in enumerate(direct_children):
                sub_row = self.oob_data.get_row(sub_row_index)
                seq_to_sub[i + 2] = (sub_row_index, sub_row)

            units_to_select = [parent_unit_item]

            angle_rad = math.radians(parent_unit_item.rotation())
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)

            for seq_str, (rel_x_yards, rel_y_yards, length, depth) in positions.items():
                seq = int(seq_str)
                if seq == 1 or seq == 2: # Skip the first two positions which represent the commander and standard bearer and don't have units associated with them in the OOB data
                    continue

                sub_row_index, sub_row = seq_to_sub.get(seq-1, (None, None))
                if sub_row_index is None:
                    continue

                # Use child formation's origin offset to place origin (not center)
                if isinstance(parent_formation.strength, list) and seq - 1 < len(parent_formation.strength):
                    child_fm = parent_formation.strength[seq - 1]
                    if child_fm is not None and hasattr(child_fm, 'origin_offset_x'):
                        origin_x = rel_x_yards + child_fm.origin_offset_x
                        origin_y = rel_y_yards + child_fm.origin_offset_y
                    else:
                        origin_x = rel_x_yards + length / 2
                        origin_y = rel_y_yards + depth / 2
                else:
                    origin_x = rel_x_yards + length / 2
                    origin_y = rel_y_yards + depth / 2
                rot_x = origin_x * cos_a - origin_y * sin_a
                rot_y = origin_x * sin_a + origin_y * cos_a
                world_x = parent_unit_item.world_x + int(rot_x * self.units_per_yard)
                world_y = parent_unit_item.world_y + int(rot_y * self.units_per_yard)

                unit_item = self.placed_by_row.get(sub_row_index)

                if unit_item is not None:
                    unit_item.world_x = world_x
                    unit_item.world_y = world_y
                    unit_item.setRotation(parent_unit_item.rotation())
                    scene_pos = self.world_to_scene(world_x, world_y)
                    unit_item.setPos(scene_pos)
                    unit_item.setZValue(7 - (self.oob_data.get_level(sub_row_index) or 1))
                    if child_formation_type:
                        unit_item.formation = child_formation_type
                    unit_item.refresh_dimensions()
                    unit_item._rebuild_scene_geometry()
                    units_to_select.append(unit_item)

                    sub_level = self.oob_data.get_level(sub_row_index)
                    if sub_level is not None and sub_level < 6 and child_formation_type:
                        self.apply_formation(unit_item, child_formation_type)
                else:
                    sub_info = self.oob_data.unit_info(sub_row_index)
                    sub_info = sub_info._replace(
                        name=str(sub_row.get("NAME1", f"Unit {sub_row_index}")),
                        side=int(sub_row.get("SIDE 1", 1)),
                        formation=child_formation_type or sub_row.get("Formation", ""),
                        head_count=int(sub_row.get("Head Count", 0) or 0),
                    )
                    self._place_unit(sub_info, world_x, world_y)
                    unit_item = self.placed_by_row.get(sub_row_index)
                    if unit_item is not None:
                        unit_item.setRotation(parent_unit_item.rotation())
                        units_to_select.append(unit_item)

                    sub_level = self.oob_data.get_level(sub_row_index)
                    if sub_level is not None and sub_level < 6 and child_formation_type:
                        self.apply_formation(unit_item, child_formation_type)

            for unit in units_to_select:
                unit.setSelected(True)

        except Exception as e:
            QMessageBox.critical(
                self, "Formation Error",
                f"Failed to apply formation '{formation_type}':\n\n"
                f"Error: {type(e).__name__}: {str(e)}\n\n"
                f"Stack trace:\n{traceback.format_exc()}")

    def _on_zoom_to_selected(self):
        items = self.minimap_scene.selectedItems()
        map_items = [i for i in items if isinstance(i, MapUnitItem)]
        if map_items:
            self.on_unit_double_clicked(map_items[0].unit_row_index)

    def on_unit_double_clicked(self, row_index: int):
        unit_item = self.placed_by_row.get(row_index)
        if unit_item is None:
            return

        zoom_rect = self._compute_zoom_bounds(unit_item)
        if zoom_rect is not None:
            self.minimap_view.fitInView(zoom_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.minimap_view.centerOn(zoom_rect.center())
            self.minimap_view.zoom_level = self.minimap_view.transform().m11()

    def _compute_zoom_bounds(self, unit_item: 'MapUnitItem') -> Optional[QRectF]:
        BUFFER = 5000

        cx = unit_item.world_x
        cy = unit_item.world_y

        all_x = [cx]
        all_y = [cy]
        visited = set()

        def collect_subordinates(row_idx: int):
            if row_idx in visited:
                return
            visited.add(row_idx)
            sub_indices = self.oob_data.get_subordinate_row_indices(row_idx)
            for sub_idx in sub_indices:
                sub_row = self.oob_data.get_row(sub_idx)
                if "SupplyWagon" in str(sub_row.get("Formation", "")):
                    continue
                placed = self.placed_by_row.get(sub_idx)
                if placed is not None:
                    all_x.append(placed.world_x)
                    all_y.append(placed.world_y)

        collect_subordinates(unit_item.unit_row_index)

        min_x = min(all_x) - BUFFER
        max_x = max(all_x) + BUFFER
        min_y = min(all_y) - BUFFER
        max_y = max(all_y) + BUFFER

        p1 = self.world_to_scene(int(min_x), int(min_y))
        p2 = self.world_to_scene(int(max_x), int(max_y))

        return QRectF(p1, p2).normalized()

    # ── Objective methods ────────────────────────────────────────

    def get_scene_scale(self) -> float:
        if self.tga_width is None or self.minimap_pixmap_item is None:
            return 1.0
        pixmap_rect = self.minimap_pixmap_item.boundingRect()
        world_width = self.tile_scale * self.tga_width
        if world_width == 0:
            return 1.0
        return pixmap_rect.width() / world_width

    def add_objective(self, world_x: int, world_y: int,
                      name: str = None, fields: dict = None) -> int:
        obj_id = self._next_objective_id
        self._next_objective_id += 1

        if name is None:
            name = f"Objective {obj_id}"

        if fields is None:
            obj_id_str = f"OBJ{obj_id}"
            fields = {
                "Name": name,
                "ID": obj_id_str,
                "Priority": "major",
                "Type": "hold",
                "AI": "100",
                "loc x": world_x,
                "loc z": world_y,
                "radius": "100",
                "Men": "100",
                "Points": "100",
                "Fatigue": "0",
                "Morale": "0",
                "Ammo": "0",
                "OccMod": "1",
                "Beg": "06:00:00",
                "End": "99:99:99",
                "Interval": "0:01",
                "Sprite": "GFX_Obj_Major",
                "Army1": "GFX_Obj_UMajor",
                "Army2": "GFX_Obj_CMajor",
                "Army3": "",
            }

        item = MapObjectiveItem(
            objective_id=obj_id, name=name,
            world_x=world_x, world_y=world_y,
            fields=fields, map_widget=self)

        scene_pos = self.world_to_scene(world_x, world_y)
        item.setPos(scene_pos)
        self.minimap_scene.addItem(item)
        self.placed_objectives.append(item)
        self.placed_objective_ids.add(obj_id)
        self.objectives_by_id[obj_id] = item

        self.objective_placed.emit(obj_id)
        return obj_id

    def remove_objective(self, objective_id: int):
        item = self.objectives_by_id.get(objective_id)
        if item is None:
            return
        self.minimap_scene.removeItem(item)
        self.placed_objectives.remove(item)
        self.placed_objective_ids.discard(objective_id)
        del self.objectives_by_id[objective_id]
        self.objective_removed.emit(objective_id)

    def move_objective(self, objective_id: int, new_world_x: int, new_world_z: int):
        item = self.objectives_by_id.get(objective_id)
        if item is None:
            return
        item.world_x = new_world_x
        item.world_y = new_world_z
        item.fields["loc x"] = new_world_x
        item.fields["loc z"] = new_world_z
        new_scene_pos = self.world_to_scene(new_world_x, new_world_z)
        item.setPos(new_scene_pos)
        item._rebuild_scene_geometry()
        item.update()
        self.objective_moved.emit(objective_id, new_world_x, new_world_z)

    def get_objective_data(self, objective_id: int):
        item = self.objectives_by_id.get(objective_id)
        if item is None:
            return None
        return {
            "id": item.objective_id,
            "name": item.name,
            "world_x": item.world_x,
            "world_z": item.world_y,
            "fields": item.fields,
        }

    def get_all_objectives_data(self):
        return [self.get_objective_data(oid) for oid in self.placed_objective_ids]

    def start_objective_placement(self):
        self._objective_placement_mode = True
        self.minimap_view.setCursor(Qt.CursorShape.CrossCursor)
        self.place_objective_button.setEnabled(False)

    def _finish_objective_placement(self):
        self._objective_placement_mode = False
        self.minimap_view.setCursor(Qt.CursorShape.ArrowCursor)
        self.place_objective_button.setEnabled(True)

    def show_objective_context_menu(self, item: MapObjectiveItem, global_pos):
        self.minimap_scene.clearSelection()
        item.setSelected(True)

        menu = QMenu(self)
        menu.addAction("Delete Objective",
                       lambda: self.remove_objective(item.objective_id))
        menu.addAction("Cancel")
        menu.exec(global_pos)

    def _on_objective_moved_from_item(self, objective_id: int, world_x: int, world_y: int):
        self.objective_moved.emit(objective_id, world_x, world_y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.minimap_pixmap is not None:
            self.display_minimap()
            self._update_placed_unit_positions()
