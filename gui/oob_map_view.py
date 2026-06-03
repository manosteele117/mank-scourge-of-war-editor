import os
import json
import configparser
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox,
    QFileDialog, QMessageBox, QSizePolicy, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsEllipseItem, QMenu,
)
from PySide6.QtGui import QPixmap, QFont, QPainter, QImage, QPen, QBrush, QColor, QPainterPath, QPolygonF, QWheelEvent
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QTimer
from PIL import Image

from core.utilities import get_tga_dimensions, plot_rectangles
from core.formation import ActualFormation, FormationArchetype
from constants import COLOR_SIDE_1, COLOR_SIDE_2


class OOBMapGraphicsView(QGraphicsView):
    """Custom graphics view for the minimap with placement mode support."""
    MIN_ZOOM = 0.1
    MAX_ZOOM = 50.0
    ZOOM_FACTOR = 1.2
    def __init__(self, scene, map_widget, parent=None):
        super().__init__(scene, parent)
        self.map_widget = map_widget
        self.selection_rect_item = None
        self.selection_start = None
        self.is_box_selecting = False

        # Right-click rotation state
        self.is_rotating = False
        self.rotation_reference_items = []  # store (item, start_angle) pairs
        self._last_mouse_angle = None

        # Middle-click pan state
        self.is_panning = False
        self._pan_start_pos = None

        self.zoom_level = 1.0

    def mouseMoveEvent(self, event):
        if self.is_panning and self._pan_start_pos is not None:
            delta = event.pos() - self._pan_start_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start_pos = event.pos()
            event.accept()
            return
        if self.is_rotating and self.rotation_reference_items:
            scene_pos = self.mapToScene(event.pos())
            if self._last_mouse_angle is not None:
                for item in self.rotation_reference_items:
                    center = item.mapToScene(item.boundingRect().center())
                    # Calculate angle delta between consecutive mouse positions
                    prev_angle = self._angle_between(self._last_mouse_angle, center)
                    current_angle = self._angle_between(scene_pos, center)
                    delta = current_angle - prev_angle
                    item.setRotation(item.rotation() + delta)
            self._last_mouse_angle = scene_pos
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
        if event.button() == Qt.MouseButton.MiddleButton:
            # Manual middle-click panning
            self.is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        elif event.button() == Qt.MouseButton.RightButton:
            # Start rotation mode
            items = self.scene().selectedItems()
            valid_items = [i for i in items if isinstance(i, MapUnitItem)]
            if valid_items:
                self.is_rotating = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                scene_pos = self.mapToScene(event.pos())
                self._last_mouse_angle = scene_pos
                self.rotation_reference_items = valid_items
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
            else:
                scene_pos = self.mapToScene(event.pos())
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.scene().clearSelection()
                self.selection_start = scene_pos
                self.is_box_selecting = True
                event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self.is_panning:
            self.is_panning = False
            self._pan_start_pos = None
            self.unsetCursor()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.RightButton and self.is_rotating:
            self.is_rotating = False
            self.rotation_reference_items.clear()
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
                    if isinstance(item, MapUnitItem):
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
            unit_data = json.loads(data.decode('utf-8'))
            scene_pos = self.mapToScene(event.pos())
            self.map_widget.place_unit_at_position(scene_pos, unit_data)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, MapUnitItem):
            self.map_widget.show_formation_context_menu(item, event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        angle = event.angleDelta().y()
        factor = self.ZOOM_FACTOR if angle > 0 else 1 / self.ZOOM_FACTOR

        new_zoom = self.zoom_level * factor
        if new_zoom < self.MIN_ZOOM or new_zoom > self.MAX_ZOOM:
            return

        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self.zoom_level = new_zoom


class MapUnitItem(QGraphicsItem):
    """
    A worldspace polygon on the minimap, rendered as either a rectangle or triangle.

    Level 6 units are rendered as rectangles sized to their formation dimensions.
    All other levels are rendered as triangles. Supports drag, rotate, selection,
    and hover highlighting.
    """

    DEFAULT_RECT_WIDTH = 2000 # if its a square, something is messed up
    DEFAULT_RECT_HEIGHT = 2000
    TRI_SIZE = 500
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

        self._scene_polygon: Optional[QPolygonF] = None
        self._label: str = ""

        # Compute level-6 rectangle dimensions from formation if available
        self.world_width = self.DEFAULT_RECT_WIDTH
        self.world_height = self.DEFAULT_RECT_HEIGHT
        if self.level == 6 and self.formation and self.formation in FormationArchetype.formations:
            try:
                af = ActualFormation(archetype_id=self.formation, strength=int(self.head_count / self.SPRITE_SCALE))
                length_yards, depth_yards = af.get_dimensions()
                upy = self.map_widget.units_per_yard if self.map_widget else 30
                self.world_width = length_yards * upy
                self.world_height = depth_yards * upy
            except Exception:
                pass  # fall back to defaults

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

    def _rebuild_scene_geometry(self):
        if self.map_widget is None:
            return
        self.prepareGeometryChange()
        item_pos = self.pos()
        poly = QPolygonF()
        if self.level == 6:
            hw = self.world_width / 2
            hh = self.world_height / 2
            corners = [
                (self.world_x - hw, self.world_y - hh),
                (self.world_x + hw, self.world_y - hh),
                (self.world_x + hw, self.world_y + hh),
                (self.world_x - hw, self.world_y + hh),
            ]
            for wx, wy in corners:
                sp = self.map_widget.world_to_scene(wx, wy)
                poly.append(sp - item_pos)
        else:
            hw = self.TRI_SIZE / 2
            hh = self.TRI_SIZE / 2
            triangle_corners = [
                (self.world_x, self.world_y - hh * 2 / 3),
                (self.world_x - hw, self.world_y + hh / 3),
                (self.world_x + hw, self.world_y + hh / 3),
            ]
            for wx, wy in triangle_corners:
                sp = self.map_widget.world_to_scene(wx, wy)
                poly.append(sp - item_pos)
        self._scene_polygon = poly

    def update_from_world(self):
        self._rebuild_scene_geometry()
        self.update()

    def boundingRect(self):
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            return self._scene_polygon.boundingRect().adjusted(-5, -5, 5, 5)
        return QRectF()

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            path.addPolygon(self._scene_polygon)
            path.closeSubpath()
        return path

    def paint(self, painter: QPainter, option, widget=None):
        if self._scene_polygon is None or self._scene_polygon.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side_color = QColor(COLOR_SIDE_1) if self.side == 1 else QColor(COLOR_SIDE_2)

        if self.isSelected():
            side_color = side_color.lighter(170)
            border_color = QColor("#ffff00")
            border_width = 0.025
        elif self.is_hovered:
            side_color = side_color.lighter(135)
            border_color = QColor("#64b5f6")
            border_width = 0.02
        else:
            border_color = QColor("#ffffff")
            border_width = 0.015

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(side_color))
        painter.drawPolygon(self._scene_polygon)

        if self._label and self._scene_polygon.size() > 0:
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

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.map_widget is not None:
            self.world_x, self.world_y = self.map_widget.scene_to_world(value.x(), value.y())
            self._rebuild_scene_geometry()
        return super().itemChange(change, value)


class OOBMapWidget(QWidget):
    """Widget for displaying map information and minimap visualization."""

    unit_placed = Signal(int, int, int)

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
        self.minimap_pixmap_item = None
        self.minimap_display_size = None
        self.tile_scale = 512
        self.units_per_yard = 30

        self.placed_units: List[MapUnitItem] = []
        self.placed_row_indices: set = set()
        self.max_units = 50
        self.unit_count_label = None
        self.placed_shapes: List[MapUnitItem] = []

        self.init_ui()
        if map_ini:
            self.load_map_from_ini(map_ini)
        if drills:
            self.load_formations(drills)

    def init_ui(self):
        main_layout = QVBoxLayout()

        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(8)

        self.load_button = QPushButton("Load Map")
        self.load_button.clicked.connect(self.load_map)
        control_layout.addWidget(self.load_button)

        self.load_formations_button = QPushButton("Load Formations")
        self.load_formations_button.clicked.connect(self.load_formations)
        control_layout.addWidget(self.load_formations_button)

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

        self.unit_count_label = QLabel("Units: 0/50")
        self.unit_count_label.setMaximumWidth(100)
        control_layout.addWidget(self.unit_count_label)

        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_all_units)
        clear_button.setMaximumWidth(100)
        control_layout.addWidget(clear_button)

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
        self.coord_label = QLabel("Coordinates: --")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.coord_label.setFont(font)
        coord_layout.addWidget(self.coord_label)
        coord_layout.addStretch()

        coord_widget = QWidget()
        coord_widget.setLayout(coord_layout)
        main_layout.addWidget(coord_widget, 0)

        self.setLayout(main_layout)

    def load_map(self):
        home_dir = os.path.expanduser("~")
        ini_path, _ = QFileDialog.getOpenFileName(
            self, "Open Map Configuration", home_dir, "INI Files (*.ini)")
        if not ini_path:
            return
        try:
            self.load_map_from_ini(ini_path)
        except Exception as e:
            QMessageBox.critical(self, "Map Load Error", f"Failed to load map:\n{str(e)}")

    def load_formations(self, csv_path=None):
        if csv_path is None:
            home_dir = os.path.expanduser("~")
            csv_path, _ = QFileDialog.getOpenFileName(
                self, "Open Formations CSV", home_dir, "CSV Files (*.csv)")
        if not csv_path:
            return
        try:
            from core.formation import populate_formation_archetypes_from_csv
            populate_formation_archetypes_from_csv(csv_path)
            QMessageBox.information(self, "Formations Loaded",
                                    f"Formation archetypes loaded from:\n{csv_path}")
        except Exception as e:
            QMessageBox.critical(self, "Formations Load Error",
                                 f"Failed to load formations:\n{str(e)}")

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
            data = img.tobytes("raw", "BGRA")
            self.minimap_pixmap = QPixmap.fromImage(
                QImage(data, width, height, QImage.Format.Format_RGBA8888))
        else:
            self.minimap_pixmap = QPixmap(str(minimap_path))

        if self.minimap_pixmap.isNull():
            raise ValueError(f"Failed to load minimap image: {minimap_path}")

        self.display_minimap()

        self.map_ini_path = ini_path
        self.lsl_path = lsl_path
        self.minimap_path = minimap_path

        map_name = ini_path.stem
        self.info_label.setText(
            f"Loaded: {map_name} | LSL: {files_section['LSLFile']} | "
            f"Minimap: {files_section['Minimap']} | "
            f"TGA Dimensions: {self.tga_width}x{self.tga_height}")

    def display_minimap(self):
        if self.minimap_pixmap is None:
            return

        self.minimap_display_size = (self.minimap_pixmap.width(), self.minimap_pixmap.height())

        placed_units_backup = list(self.placed_units)
        placed_indices_backup = set(self.placed_row_indices)
        for unit in placed_units_backup:
            self.minimap_scene.removeItem(unit)

        self.minimap_scene.clear()

        view_size = self.minimap_view.size()
        if view_size.width() <= 0 or view_size.height() <= 0:
            view_size.setWidth(400)
            view_size.setHeight(400)

        scaled_pixmap = self.minimap_pixmap.scaled(
            view_size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

        self.minimap_pixmap_item = self.minimap_scene.addPixmap(scaled_pixmap)
        self.minimap_pixmap_item.setPos(0, 0)

        self._update_placed_unit_positions()
        self.update_all_shapes()
        for unit in placed_units_backup:
            self.minimap_scene.addItem(unit)

        #self.minimap_view.fitInView(
        #    self.minimap_pixmap_item.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

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

    def on_minimap_mouse_leave(self, event):
        self.coord_label.setText("Coordinates: --")

    def on_tile_scale_changed(self, value: int):
        self.tile_scale = value
        self._update_placed_unit_positions()
        self.update_all_shapes()

    def on_units_per_yard_changed(self, value: int):
        self.units_per_yard = value

    # ==================== Unit Placement Methods ====================

    def place_unit_at_position(self, scene_pos: QPointF, unit_data: Dict):
        scene_rect = self.minimap_scene.sceneRect()
        if not scene_rect.contains(scene_pos):
            return

        row_index = unit_data.get("row_index")

        if row_index in self.placed_row_indices:
            unit_name = unit_data.get("name", "Unknown")
            QMessageBox.information(
                self, "Duplicate Unit",
                f"{unit_name} has already been placed on the map.\n"
                f"Each unit can only be placed once.")
            return

        if len(self.placed_units) >= self.max_units:
            QMessageBox.warning(self, "Limit Reached",
                                f"Maximum {self.max_units} units can be placed.")
            return

        world_x, world_y = self.scene_to_world(scene_pos.x(), scene_pos.y())
        self._place_unit(row_index, world_x, world_y, unit_data)

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

    def _place_unit(self, row_index: int, world_x: int, world_y: int, unit_data: Optional[Dict] = None):
        if unit_data is None:
            unit_data = {}
        name = unit_data.get("name", f"Unit {len(self.placed_units) + 1}")
        side = unit_data.get("side", 1)
        level = unit_data.get("level", 1)
        formation = unit_data.get("formation", "")
        head_count = unit_data.get("head_count", 0)

        unit_item = MapUnitItem(
            name=name, unit_row_index=row_index, side=side, level=level,
            formation=formation, world_x=world_x, world_y=world_y,
            head_count=head_count, map_widget=self)

        scene_pos = self.world_to_scene(world_x, world_y)
        unit_item.setPos(scene_pos)
        unit_item._rebuild_scene_geometry()

        self.minimap_scene.addItem(unit_item)
        self.placed_units.append(unit_item)
        self.placed_row_indices.add(row_index)

        self._update_unit_count()
        self.unit_placed.emit(row_index, world_x, world_y)

    def _update_placed_unit_positions(self):
        for unit_item in self.placed_units:
            scene_pos = self.world_to_scene(unit_item.world_x, unit_item.world_y)
            unit_item.setPos(scene_pos)

    def _update_unit_count(self):
        count = len(self.placed_units)
        self.unit_count_label.setText(f"Units: {count}/{self.max_units}")

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
        self._update_unit_count()

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

    # ==================== Worldspace Shape Methods ====================

    def update_all_shapes(self):
        for shape in self.placed_shapes:
            shape.update_from_world()

    def clear_all_shapes(self):
        for shape in self.placed_shapes:
            self.minimap_scene.removeItem(shape)
        self.placed_shapes.clear()

    def get_placed_shapes_data(self) -> List[Dict]:
        return [
            {"world_x": s.world_x, "world_y": s.world_y, "label": s._label}
            for s in self.placed_shapes
        ]

    # ==================== End Worldspace Shape Methods ====================

    def show_formation_context_menu(self, unit_item: MapUnitItem, global_pos):
        if self.oob_data is None:
            QMessageBox.warning(self, "Error", "OOB data not loaded. Cannot apply formations.")
            return

        self.minimap_scene.clearSelection()
        unit_item.setSelected(True)

        menu = QMenu(self)
        action = menu.addAction(unit_item.formation)
        menu.addSeparator()
        cancel_action = menu.addAction("Cancel")

        action.triggered.connect(
            lambda: self.apply_formation(unit_item, unit_item.formation))

        menu.exec(global_pos)

    def apply_formation(self, parent_unit_item: MapUnitItem, formation_type: str):
        if self.oob_data is None:
            QMessageBox.warning(self, "Error", "OOB data not loaded.")
            return
        try:
            parent_row_index = parent_unit_item.unit_row_index
            parent_row = self.oob_data.get_row(parent_row_index)

            subordinate_indices = self.oob_data.get_subordinate_row_indices(parent_row_index)

            def build_strength(row_index: int) -> ActualFormation:
                sub_row = self.oob_data.get_row(row_index)
                archetype_id = sub_row.get("Formation", "")  # TODO: switch this to use the actual input formation, currently only one loads.
                level = self.oob_data.get_level_from_hierarchy(sub_row)
                if level is None:
                    raise ValueError(f"Cannot determine level for row {row_index}")
                if level >= 6:
                    head_count = sub_row.get("Head Count", 0)
                    return ActualFormation(archetype_id=archetype_id, strength=int(head_count))
                else:
                    all_sub_indices = self.oob_data.get_subordinate_row_indices(row_index)
                    # Filter to direct children that are one level down and not supply wagons
                    direct_children = [
                        idx for idx in all_sub_indices
                        if self.oob_data.get_level_from_hierarchy(self.oob_data.get_row(idx)) == level + 1 and "SupplyWagon" not in self.oob_data.get_row(idx).get("Formation", "")
                    ]
                    sub_formations = [None, None] + [build_strength(idx) for idx in direct_children]  # None values represent 1 and 2, which are flag bearer and commander(?) of the unit and don't need to get placed.
                    return ActualFormation(archetype_id=archetype_id, strength=sub_formations)

            parent_formation = build_strength(parent_row_index)
            positions = parent_formation.get_positions()
            #plot_rectangles(positions, title=f"Formation: {formation_type}")  # Debug visualization

            if not positions:
                QMessageBox.information(self, "No Positions",
                                        "Formation has no valid positions to apply.")
                return

            seq_to_sub = {1: (parent_row_index, parent_row)}

            # Filter to direct children only (one level down from parent),
            # excluding supply wagons which don't get placed on the map.
            level = self.oob_data.get_level_from_hierarchy(parent_row)
            direct_children = [
                idx for idx in subordinate_indices
                if self.oob_data.get_level_from_hierarchy(self.oob_data.get_row(idx)) == level + 1
                and "SupplyWagon" not in self.oob_data.get_row(idx).get("Formation", "")
            ]

            for i, sub_row_index in enumerate(direct_children):
                sub_row = self.oob_data.get_row(sub_row_index)
                seq_to_sub[i + 2] = (sub_row_index, sub_row)

            units_to_select = [parent_unit_item]

            angle_rad = math.radians(parent_unit_item.rotation())
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)

            for seq_str, (rel_x_yards, rel_y_yards, length, depth) in positions.items():
                seq = int(seq_str)
                if seq == 1:
                    continue

                sub_row_index, sub_row = seq_to_sub.get(seq, (None, None))
                if sub_row_index is None:
                    continue

                rot_x = rel_x_yards * cos_a - rel_y_yards * sin_a
                rot_y = rel_x_yards * sin_a + rel_y_yards * cos_a
                world_x = parent_unit_item.world_x + int(rot_x * self.units_per_yard)
                world_y = parent_unit_item.world_y + int(rot_y * self.units_per_yard)

                unit_item = None
                for placed_unit in self.placed_units:
                    if placed_unit.unit_row_index == sub_row_index:
                        unit_item = placed_unit
                        break

                if unit_item is not None:
                    unit_item.world_x = world_x
                    unit_item.world_y = world_y
                    unit_item.setRotation(parent_unit_item.rotation())
                    scene_pos = self.world_to_scene(world_x, world_y)
                    unit_item.setPos(scene_pos)
                    unit_item._rebuild_scene_geometry()
                    units_to_select.append(unit_item)

                    sub_level = self.oob_data.get_level_from_hierarchy(sub_row)
                    if sub_level is not None and sub_level < 6:
                        self.apply_formation(unit_item, formation_type)
                else:
                    unit_data = {
                        "name": sub_row.get("NAME1", f"Unit {sub_row_index}"),
                        "side": int(sub_row.get("SIDE 1", 1)),
                        "level": self.oob_data.get_level_from_hierarchy(sub_row),
                        "formation": sub_row.get("Formation", ""),
                        "head_count": int(sub_row.get("Head Count", 0) or 0),
                    }
                    print(unit_data)
                    self._place_unit(sub_row_index, world_x, world_y, unit_data)
                    for placed_unit in self.placed_units:
                        if placed_unit.unit_row_index == sub_row_index:
                            unit_item = placed_unit
                            unit_item.setRotation(parent_unit_item.rotation())
                            units_to_select.append(placed_unit)
                            break

                    sub_level = self.oob_data.get_level_from_hierarchy(sub_row)
                    if sub_level is not None and sub_level < 6:
                        self.apply_formation(unit_item, formation_type)

            for unit in units_to_select:
                unit.setSelected(True)

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            QMessageBox.critical(
                self, "Formation Error",
                f"Failed to apply formation:\n{str(e)}\n\n{tb_str}")

    def on_unit_double_clicked(self, row_index: int):
        unit_item = None
        for placed_unit in self.placed_units:
            if placed_unit.unit_row_index == row_index:
                unit_item = placed_unit
                break

        if unit_item is None:
            return

        scene_pos = self.world_to_scene(unit_item.world_x, unit_item.world_y)

        zoom_rect = self._compute_zoom_bounds(unit_item)
        if zoom_rect is not None:
            self.minimap_view.fitInView(zoom_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.minimap_view.centerOn(zoom_rect.center())
            self.minimap_view.zoom_level = self.minimap_view.transform().m11()

        self._ping_position(scene_pos)

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
                for placed_unit in self.placed_units:
                    if placed_unit.unit_row_index == sub_idx:
                        all_x.append(placed_unit.world_x)
                        all_y.append(placed_unit.world_y)
                        break

        collect_subordinates(unit_item.unit_row_index)

        min_x = min(all_x) - BUFFER
        max_x = max(all_x) + BUFFER
        min_y = min(all_y) - BUFFER
        max_y = max(all_y) + BUFFER

        p1 = self.world_to_scene(int(min_x), int(min_y))
        p2 = self.world_to_scene(int(max_x), int(max_y))

        return QRectF(p1, p2).normalized()

    def _ping_position(self, scene_pos: QPointF):
        existing = [
            item for item in self.minimap_scene.items()
            if isinstance(item, QGraphicsEllipseItem) and item.data(0) == "ping"
        ]
        for item in existing:
            self.minimap_scene.removeItem(item)

        ping_item = QGraphicsEllipseItem(QRectF(-3, -3, 6, 6))
        self.minimap_scene.addItem(ping_item)
        ping_item.setPos(scene_pos)
        ping_item.setPen(QPen(QColor(255, 255, 255, 200), 3))
        ping_item.setBrush(QBrush(QColor(255, 255, 255, 60)))
        ping_item.setData(0, "ping")
        ping_item.setZValue(100)

        outer_ping = QGraphicsEllipseItem(QRectF(-60, -60, 120, 120))
        self.minimap_scene.addItem(outer_ping)
        outer_ping.setPos(scene_pos)
        outer_ping.setPen(QPen(QColor(200, 230, 255, 150), 2))
        outer_ping.setBrush(QBrush(QColor(200, 230, 255, 30)))
        outer_ping.setData(0, "ping")
        outer_ping.setZValue(99)

        timer = QTimer()
        timer.setInterval(50)
        timer.setSingleShot(False)

        radius = 3.0
        opacity = 0.8
        outer_radius = 60.0
        outer_opacity = 0.6

        def animate():
            nonlocal radius, opacity, outer_radius, outer_opacity
            radius += 1.5
            opacity -= 0.025
            outer_radius += 1.0
            outer_opacity -= 0.015

            if opacity <= 0:
                opacity = 0
            if outer_opacity <= 0:
                outer_opacity = 0

            ping_item.setRect(-radius, -radius, radius * 2, radius * 2)
            ping_item.setPen(QPen(QColor(255, 255, 255, int(opacity * 255)), 3))
            ping_item.setBrush(QBrush(QColor(255, 255, 255, int(opacity * 60))))

            outer_ping.setRect(-outer_radius, -outer_radius, outer_radius * 2, outer_radius * 2)
            outer_ping.setPen(QPen(QColor(200, 230, 255, int(outer_opacity * 255)), 2))
            outer_ping.setBrush(QBrush(QColor(200, 230, 255, int(outer_opacity * 30))))

            if opacity <= 0 or outer_opacity <= 0:
                self.minimap_scene.removeItem(ping_item)
                self.minimap_scene.removeItem(outer_ping)
                timer.stop()
                timer.deleteLater()

        timer.timeout.connect(animate)
        timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.minimap_pixmap is not None:
            self.display_minimap()
            self._update_placed_unit_positions()
            self.update_all_shapes()

    def on_minimap_resize(self, event):
        if self.minimap_pixmap is not None:
            self.display_minimap()
