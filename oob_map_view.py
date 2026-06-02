import os
import configparser
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import math

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSpinBox,
    QFileDialog,
    QMessageBox,
    QSizePolicy,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QMenu,
)
from PySide6.QtGui import QPixmap, QFont, QPainter, QImage, QPen, QBrush, QColor, QPainterPath, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PIL import Image

from utilities import get_tga_dimensions
from formation_layout import calculate_road_formation, calculate_line_formation
from formation import ActualFormation


class OOBMapGraphicsView(QGraphicsView):
    """Custom graphics view for the minimap with placement mode support."""
    
    def __init__(self, scene, map_widget, parent=None):
        super().__init__(scene, parent)
        self.map_widget = map_widget
        self.selection_rect_item = None
        self.selection_start = None
        self.is_box_selecting = False
    
    def mouseMoveEvent(self, event):
        """Handle mouse movement."""
        if self.is_box_selecting and self.selection_start:
            scene_pos = self.mapToScene(event.pos())
            
            # Draw selection rectangle
            selection_rect = QRectF(self.selection_start, scene_pos).normalized()
            
            if self.selection_rect_item is None:
                self.selection_rect_item = self.scene().addRect(
                    selection_rect,
                    QPen(QColor(100, 150, 255), 1),
                    QBrush(QColor(100, 150, 255, 50))
                )
            else:
                self.selection_rect_item.setRect(selection_rect)
            
            event.accept()
        else:
            self.map_widget.on_minimap_mouse_move(event)
            super().mouseMoveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            super().mousePressEvent(event)
        elif event.button() == Qt.MouseButton.LeftButton:
            # Check if clicked on an item
            item = self.itemAt(event.pos())
            
            if isinstance(item, MapUnitItem):
                # Clicked on a unit
                if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                    # Shift-click: toggle selection
                    item.setSelected(not item.isSelected())
                    event.accept()
                    return
                else:
                    # Regular click on unit: select it and allow dragging
                    #self.scene().clearSelection()
                    item.setSelected(True)
                    super().mousePressEvent(event)  # Let default behavior handle dragging
                    return
            else:
                # Clicked on empty space: start box selection
                scene_pos = self.mapToScene(event.pos())
                
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    # If not Shift-clicking, clear previous selection
                    self.scene().clearSelection()
                
                # Start box selection
                self.selection_start = scene_pos
                self.is_box_selecting = True
                event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.NoDrag)
            super().mouseReleaseEvent(event)
        elif event.button() == Qt.MouseButton.LeftButton and self.is_box_selecting:
            # Finish box selection
            if self.selection_rect_item:
                rect = self.selection_rect_item.rect()
                self.scene().removeItem(self.selection_rect_item)
                self.selection_rect_item = None
                
                # Select all items in the rectangle
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
    
    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasFormat("application/x-unit-drop"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    
    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasFormat("application/x-unit-drop"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    
    def dropEvent(self, event):
        """Handle drop event to place units from tree view."""
        if event.mimeData().hasFormat("application/x-unit-drop"):
            mime_data = event.mimeData()
            data = mime_data.data("application/x-unit-drop").data()
            unit_data = eval(data.decode('utf-8'))  # Parse the unit data
            
            scene_pos = self.mapToScene(event.pos())
            self.map_widget.place_unit_at_position(scene_pos, unit_data)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
    
    def contextMenuEvent(self, event):
        """Handle right-click context menu for formations."""
        item = self.itemAt(event.pos())
        
        if isinstance(item, MapUnitItem):
            # Right-click on a unit: show formation menu
            self.map_widget.show_formation_context_menu(item, event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)
    
    def wheelEvent(self, event):
        """Handle scroll wheel for rotation or zoom."""
        items = self.scene().selectedItems()
        if items:
            # Rotate all selected items
            angle_delta = event.angleDelta().y() / 8
            for item in items:
                if isinstance(item, MapUnitItem):
                    item.setRotation(item.rotation() + angle_delta)
            event.accept()
            return
        else:
            # Zoom in/out based on scroll wheel
            zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(zoom_factor, zoom_factor)
            event.accept()
            return


class MapUnitItem(QGraphicsItem):
    """
    A worldspace polygon on the minimap, rendered as either a rectangle or triangle.

    Level 6 units are rendered as 2000x300 rectangles. All other levels are rendered
    as 100x100 triangles. The polygon is defined by world_x/world_y (center) and
    scales with the map. Supports drag, rotate, selection, and hover highlighting.
    """

    # Level 6 rectangle dimensions in world units
    RECT_WIDTH = 2000
    RECT_HEIGHT = 300
    # Triangle dimensions in world units
    TRI_SIZE = 500

    def __init__(self, name: str, unit_row_index: int, side: int, level: int, formation: str, world_x: int, world_y: int, map_widget=None, parent=None):
        """
        Initialize a map unit item.

        Args:
            name: Unit name
            unit_row_index: Row index in OOBData
            side: 1 or 2
            level: Hierarchy level (1-6)
            formation: Formation type
            world_x: World coordinate X (center of rectangle)
            world_y: World coordinate Y (center of rectangle)
            map_widget: Owning map widget for coordinate sync
            parent: Parent QGraphicsItem
        """
        super().__init__(parent)

        self.name = name
        self.unit_row_index = unit_row_index
        self.side = side
        self.level = level
        self.formation = formation
        self.world_x = world_x
        self.world_y = world_y
        self.map_widget = map_widget
        self.is_hovered = False

        # Generate default rectangle centered on (world_x, world_y)
        self._scene_polygon: Optional[QPolygonF] = None
        self._label: str = ""


        # Store row index for selection tracking
        self.setData(Qt.UserRole, unit_row_index)

        # Enable interaction
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        # Default rotation
        self.setRotation(0)

        # Build scene geometry
        self._rebuild_scene_geometry()

    def set_label(self, label: str):
        self._label = label
        self.update()

    def _rebuild_scene_geometry(self):
        """Recalculate local-space polygon from current world_x/world_y center.
        
        Level 6 units: 2000x300 rectangle centered on (world_x, world_y).
        All other levels: 100x100 isosceles triangle centered on (world_x, world_y).
        """
        if self.map_widget is None:
            return
        self.prepareGeometryChange()
        item_pos = self.pos()
        poly = QPolygonF()
        print(self.level)
        if self.level == 6:
            # Rectangle: 2000 wide x 300 tall, centered on world_x/world_y
            hw = self.RECT_WIDTH / 2
            hh = self.RECT_HEIGHT / 2
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
            # Triangle: 100x100 isosceles, centered on world_x/world_y
            # Apex at top, base at bottom, centroid at center
            hw = self.TRI_SIZE / 2
            hh = self.TRI_SIZE / 2
            # Triangle vertices with centroid at (0,0) in local coords
            # Apex (top), bottom-left, bottom-right
            triangle_corners = [
                (self.world_x, self.world_y - hh * 2 / 3),       # apex
                (self.world_x - hw, self.world_y + hh / 3),      # bottom-left
                (self.world_x + hw, self.world_y + hh / 3),      # bottom-right
            ]
            for wx, wy in triangle_corners:
                sp = self.map_widget.world_to_scene(wx, wy)
                poly.append(sp - item_pos)
        
        self._scene_polygon = poly

    def update_from_world(self):
        """Rebuild scene geometry from world coords. Call after map resize/scale."""
        self._rebuild_scene_geometry()
        self.update()

    def boundingRect(self):
        """Return tight bounding rectangle."""
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            return self._scene_polygon.boundingRect().adjusted(-5, -5, 5, 5)
        return QRectF()

    def shape(self) -> QPainterPath:
        """Return the item's shape for hit testing."""
        path = QPainterPath()
        if self._scene_polygon is not None and not self._scene_polygon.isEmpty():
            path.addPolygon(self._scene_polygon)
            path.closeSubpath()
        return path

    def paint(self, painter: QPainter, option, widget=None):
        """Paint the polygon with borders and hover/selection highlighting."""
        if self._scene_polygon is None or self._scene_polygon.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Base side color
        side_color = QColor("#2c5aa0") if self.side == 1 else QColor("#a02c2c")
        
        # Apply highlighting based on selection/hover state
        if self.isSelected():
            side_color = side_color.lighter(170)
            border_color = QColor("#ffff00")
            border_width = 0.025
        elif self.is_hovered:
            side_color = side_color.lighter(135)
            border_color = QColor("#64b5f6")
            border_width = 0.02
        else:
            border_color = QColor("#888888")
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
        """Handle hover enter."""
        self.is_hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        """Handle hover leave."""
        self.is_hovered = False
        self.update()

    def itemChange(self, change, value):
        """Handle item position changes."""
        if change == QGraphicsItem.ItemPositionHasChanged and self.map_widget is not None:
            self.world_x, self.world_y = self.map_widget.scene_to_world(value.x(), value.y())
            self._rebuild_scene_geometry()
        return super().itemChange(change, value)


class OOBMapWidget(QWidget):
    """Widget for displaying map information and minimap visualization."""
    
    # Signals
    unit_placed = Signal(int, int, int)  # (row_index, world_x, world_y)
    
    def __init__(self, oob_data=None, parent=None, map_ini: str = "", drills: str = ""):
        super().__init__(parent)
        
        # OOB data model (for retrieving unit hierarchy)
        self.oob_data = oob_data
        
        # Configuration paths

        self.map_ini_path = map_ini
        self.drills_path = drills
        
        # Map data storage
        self.lsl_path = None
        self.minimap_path = None
        self.tga_width = None
        self.tga_height = None
        self.minimap_pixmap = None
        self.minimap_pixmap_item = None
        self.minimap_display_size = None  # Size of displayed pixmap in pixels
        self.tile_scale = 512
        self.units_per_yard = 30
        
        # Unit placement data
        self.placed_units: List[MapUnitItem] = []
        self.placed_row_indices: set = set()  # track row indices to prevent duplicates
        self.max_units = 50
        self.unit_count_label = None

        # Worldspace shape overlay data
        self.placed_shapes: List[MapUnitItem] = []
        
        self.init_ui()
        if map_ini:
            self.load_map_from_ini(map_ini)
        if drills:
            self.load_formations(drills)

    
    def init_ui(self):
        """Initialize the user interface."""
        main_layout = QVBoxLayout()
        
        # Control panel (top)
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(8)
        
        self.load_button = QPushButton("Load Map")
        self.load_button.clicked.connect(self.load_map)
        control_layout.addWidget(self.load_button)
        
        self.load_formations_button = QPushButton("Load Formations")
        self.load_formations_button.clicked.connect(self.load_formations)
        control_layout.addWidget(self.load_formations_button)
        
        # Tile Scale control
        tile_scale_label = QLabel("Tile Scale:")
        control_layout.addWidget(tile_scale_label)
        
        self.tile_scale_spinbox = QSpinBox()
        self.tile_scale_spinbox.setMinimum(1)
        self.tile_scale_spinbox.setMaximum(4096)
        self.tile_scale_spinbox.setValue(512)
        self.tile_scale_spinbox.setToolTip("Default: 512. Controls coordinate scaling.")
        self.tile_scale_spinbox.valueChanged.connect(self.on_tile_scale_changed)
        control_layout.addWidget(self.tile_scale_spinbox)
        
        # Units Per Yard control
        upy_label = QLabel("Units Per Yard:")
        control_layout.addWidget(upy_label)
        
        self.units_per_yard_spinbox = QSpinBox()
        self.units_per_yard_spinbox.setMinimum(1)
        self.units_per_yard_spinbox.setMaximum(256)
        self.units_per_yard_spinbox.setValue(30)
        self.units_per_yard_spinbox.setToolTip("Default: 30. Units displayed per yard on the map.")
        self.units_per_yard_spinbox.valueChanged.connect(self.on_units_per_yard_changed)
        control_layout.addWidget(self.units_per_yard_spinbox)
        
        
        # Unit count label
        self.unit_count_label = QLabel("Units: 0/50")
        self.unit_count_label.setMaximumWidth(100)
        control_layout.addWidget(self.unit_count_label)
        
        # Clear all button
        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_all_units)
        clear_button.setMaximumWidth(100)
        control_layout.addWidget(clear_button)
        
        control_layout.addStretch()
        
        control_widget = QWidget()
        control_widget.setLayout(control_layout)
        main_layout.addWidget(control_widget, 0)
        
        # Status/Info panel
        self.info_label = QLabel("No map loaded")
        main_layout.addWidget(self.info_label, 0)
        
        # Minimap display area
        self.minimap_scene = QGraphicsScene()
        self.minimap_view = OOBMapGraphicsView(self.minimap_scene, self)
        self.minimap_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minimap_view.setRenderHints(self.minimap_view.renderHints() | QPainter.Antialiasing)
        self.minimap_view.setMouseTracking(True)
        self.minimap_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.minimap_view.setStyleSheet("border: 1px solid #333333; background-color: #1a1a1a;")
        self.minimap_view.setAcceptDrops(True)  # Enable drag-and-drop
        main_layout.addWidget(self.minimap_view, 1)
        
        # Coordinates display
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
        """Open file dialog to load a map .ini file."""
        home_dir = os.path.expanduser("~")
        ini_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Map Configuration",
            home_dir,
            "INI Files (*.ini)"
        )
        
        if not ini_path:
            return
        
        try:
            self.load_map_from_ini(ini_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Map Load Error",
                f"Failed to load map:\n{str(e)}"
            )
    
    def load_formations(self, csv_path=None):
        """Open file dialog to load a drills.csv file and populate formation archetypes."""
        if csv_path is None:
            home_dir = os.path.expanduser("~")
            csv_path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Formations CSV",
            home_dir,
            "CSV Files (*.csv)"
        )
        
        if not csv_path:
            return
        
        try:
            from formation import populate_formation_archetypes_from_csv
            populate_formation_archetypes_from_csv(csv_path)
            QMessageBox.information(
                self,
                "Formations Loaded",
                f"Formation archetypes loaded from:\n{csv_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Formations Load Error",
                f"Failed to load formations:\n{str(e)}"
            )
    
    def load_map_from_ini(self, ini_path: str):
        """Load map configuration from an INI file.
        
        Args:
            ini_path: Path to the .ini file
            
        Raises:
            FileNotFoundError: If INI file or referenced files don't exist
            KeyError: If required fields are missing from INI
            Exception: If image loading or dimension extraction fails
        """
        ini_path = Path(ini_path)
        
        if not ini_path.exists():
            raise FileNotFoundError(f"INI file not found: {ini_path}")
        
        # Parse INI file
        config = configparser.ConfigParser()
        config.read(str(ini_path))
        
        if "Files" not in config:
            raise KeyError("Missing [Files] section in INI file")
        
        files_section = config["Files"]
        
        if "LSLFile" not in files_section:
            raise KeyError("Missing LSLFile field in [Files] section")
        
        if "Minimap" not in files_section:
            raise KeyError("Missing Minimap field in [Files] section")
        
        # Construct full paths (files should be in same directory as INI)
        base_dir = ini_path.parent
        lsl_filename = files_section["LSLFile"]
        minimap_filename = files_section["Minimap"]
        
        lsl_path = base_dir / lsl_filename
        minimap_path = base_dir / minimap_filename
        
        # Validate files exist
        if not lsl_path.exists():
            raise FileNotFoundError(f"LSL file not found: {lsl_path}")
        
        if not minimap_path.exists():
            raise FileNotFoundError(f"Minimap file not found: {minimap_path}")
        
        # Extract TGA dimensions from LSL file
        self.tga_width, self.tga_height = get_tga_dimensions(str(lsl_path))
        
        # Load minimap image
        if minimap_path.suffix.lower() == ".dds":
            img = Image.open(str(minimap_path)).convert("RGBA")
            width, height = img.size
            data = img.tobytes("raw", "BGRA")
            self.minimap_pixmap = QPixmap.fromImage(QImage(data, width, height, QImage.Format.Format_RGBA8888))
        else:
            self.minimap_pixmap = QPixmap(str(minimap_path))
        
        if self.minimap_pixmap.isNull():
            raise ValueError(f"Failed to load minimap image: {minimap_path}")
        
        # Display minimap
        self.display_minimap()
        
        # Store paths
        self.map_ini_path = ini_path
        self.lsl_path = lsl_path
        self.minimap_path = minimap_path
        
        # Update info label
        map_name = ini_path.stem
        self.info_label.setText(
            f"Loaded: {map_name} | LSL: {lsl_filename} | Minimap: {minimap_filename} | "
            f"TGA Dimensions: {self.tga_width}x{self.tga_height}"
        )
    
    def display_minimap(self):
        """Display the loaded minimap in the minimap view, scaled to fit while preserving aspect ratio.
        
        The image will be centered within the view, with letterboxing/pillarboxing
        if the view and image aspect ratios differ.
        """
        if self.minimap_pixmap is None:
            return
        
        # Store original pixmap dimensions for coordinate calculation
        self.minimap_display_size = (self.minimap_pixmap.width(), self.minimap_pixmap.height())
        
        # Clear previous scene but preserve placed units temporarily
        placed_units_backup = list(self.placed_units)
        placed_indices_backup = set(self.placed_row_indices)
        for unit in placed_units_backup:
            self.minimap_scene.removeItem(unit)
        
        self.minimap_scene.clear()
        
        # Scale pixmap to fit within the view while preserving aspect ratio
        view_size = self.minimap_view.size()
        if view_size.width() <= 0 or view_size.height() <= 0:
            view_size.setWidth(400)
            view_size.setHeight(400)
        
        scaled_pixmap = self.minimap_pixmap.scaled(
            view_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Add scaled pixmap to scene, centered
        self.minimap_pixmap_item = self.minimap_scene.addPixmap(scaled_pixmap)
        self.minimap_pixmap_item.setPos(0, 0)
        
        # Restore placed units with updated positions
        self._update_placed_unit_positions()
        self.update_all_shapes()
        for unit in placed_units_backup:
            self.minimap_scene.addItem(unit)
        
        # Fit view to pixmap only, ignoring placed items that may extend beyond it
        self.minimap_view.fitInView(self.minimap_pixmap_item.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
    def on_minimap_mouse_move(self, event):
        """Handle mouse movement over minimap to display coordinates."""
        if self.minimap_pixmap is None or self.tga_width is None:
            return
        
        # Convert view coordinates to scene coordinates
        scene_pos = self.minimap_view.mapToScene(event.pos())
        scene_rect = self.minimap_scene.sceneRect()
        
        # Check if mouse is within the scene bounds
        if not scene_rect.contains(scene_pos):
            self.coord_label.setText("Coordinates: --")
            return
        
        # Get the scaled pixmap item (use stored reference, not items[0] which is unreliable)
        pixmap_item = self.minimap_pixmap_item
        if pixmap_item is None:
            self.coord_label.setText("Coordinates: --")
            return
        
        pixmap_width = pixmap_item.boundingRect().width()
        pixmap_height = pixmap_item.boundingRect().height()
        
        # Check if mouse is within the scaled pixmap bounds
        pixmap_pos = pixmap_item.pos()
        adjusted_pixel_x = scene_pos.x() - pixmap_pos.x()
        adjusted_pixel_y = scene_pos.y() - pixmap_pos.y()
        
        if adjusted_pixel_x < 0 or adjusted_pixel_y < 0 or adjusted_pixel_x >= pixmap_width or adjusted_pixel_y >= pixmap_height:
            self.coord_label.setText("Coordinates: --")
            return
        
        # Clamp to pixmap bounds to avoid division issues at edges
        adjusted_pixel_x = max(0, min(adjusted_pixel_x, pixmap_width - 1))
        adjusted_pixel_y = max(0, min(adjusted_pixel_y, pixmap_height - 1))
        
        # Formula: world_coord = (adjusted_pixel_coord / scaled_pixmap_dimension) * (tile_scale * tga_dimension)
        world_x = int((adjusted_pixel_x / pixmap_width) * (self.tile_scale * self.tga_width))
        world_y = int((adjusted_pixel_y / pixmap_height) * (self.tile_scale * self.tga_height))
        
        self.coord_label.setText(f"Coordinates: ({world_x}, {world_y})")
    
    def on_minimap_mouse_leave(self, event):
        """Handle mouse leaving the minimap area."""
        self.coord_label.setText("Coordinates: --")
    
    def on_tile_scale_changed(self, value: int):
        """Handle tile scale spinbox value change."""
        self.tile_scale = value
        self._update_placed_unit_positions()
        self.update_all_shapes()
        # Coordinates will be recalculated on next mouse move via on_minimap_mouse_move()
    
    def on_units_per_yard_changed(self, value: int):
        """Handle units per yard spinbox value change."""
        self.units_per_yard = value
    
    # ==================== Unit Placement Methods ====================
    
    def place_unit_at_position(self, scene_pos: QPointF, unit_data: Dict):
        """Place a unit at the given scene position from drag-and-drop."""
        scene_rect = self.minimap_scene.sceneRect()
        
        if not scene_rect.contains(scene_pos):
            return
        
        row_index = unit_data.get("row_index")
        
        # Check for duplicate placement
        if row_index in self.placed_row_indices:
            unit_name = unit_data.get("name", "Unknown")
            QMessageBox.information(
                self,
                "Duplicate Unit",
                f"{unit_name} has already been placed on the map.\n"
                f"Each unit can only be placed once."
            )
            return
        
        if len(self.placed_units) >= self.max_units:
            QMessageBox.warning(self, "Limit Reached", f"Maximum {self.max_units} units can be placed.")
            return
        
        world_x, world_y = self.scene_to_world(scene_pos.x(), scene_pos.y())
        self._place_unit(row_index, world_x, world_y, unit_data)
    
    def world_to_scene(self, world_x: int, world_y: int) -> QPointF:
        """Convert world coordinates to scene coordinates."""
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
        """Convert scene coordinates back to world coordinates."""
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
        """Create and place a unit on the map."""
        if unit_data is None:
            unit_data = {}
        # Get unit data from the provided dictionary
        name = unit_data.get("name", f"Unit {len(self.placed_units) + 1}")
        side = unit_data.get("side", 1)
        level = unit_data.get("level", 1)
        formation = unit_data.get("formation", "")
        
        # Create map unit item
        unit_item = MapUnitItem(
            name=name,
            unit_row_index=row_index,
            side=side,
            level=level,
            formation=formation,
            world_x=world_x,
            world_y=world_y,
            map_widget=self,
        )
        
        # Position on scene
        scene_pos = self.world_to_scene(world_x, world_y)
        unit_item.setPos(scene_pos)
        unit_item._rebuild_scene_geometry()
        
        # Add to scene and tracking list
        self.minimap_scene.addItem(unit_item)
        self.placed_units.append(unit_item)
        self.placed_row_indices.add(row_index)
        
        # Update UI
        self._update_unit_count()
        self.unit_placed.emit(row_index, world_x, world_y)
    
    def _update_placed_unit_positions(self):
        """Reposition all placed units based on current map transform."""
        for unit_item in self.placed_units:
            scene_pos = self.world_to_scene(unit_item.world_x, unit_item.world_y)
            unit_item.setPos(scene_pos)
    
    def _update_unit_count(self):
        """Update the unit count label."""
        count = len(self.placed_units)
        self.unit_count_label.setText(f"Units: {count}/{self.max_units}")
    
    def clear_all_units(self):
        """Remove all placed units."""
        reply = QMessageBox.question(
            self,
            "Clear All",
            "Remove all placed units?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for unit_item in self.placed_units:
                self.minimap_scene.removeItem(unit_item)
            self.placed_units.clear()
            self.placed_row_indices.clear()
            self._update_unit_count()
    
    def get_placed_units_data(self) -> List[Dict]:
        """Export placed units for scenario generation."""
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
    
    # ==================== End Placement Mode Methods ====================

    # ==================== Worldspace Shape Methods ====================

    # def remove_shape(self, shape_item: MapUnitItem):
    #     """Remove a shape from the scene."""
    #     if shape_item in self.placed_shapes:
    #         self.minimap_scene.removeItem(shape_item)
    #         self.placed_shapes.remove(shape_item)

    def update_all_shapes(self):
        """Rebuild scene geometry for all shapes. Call after map resize/scale change."""
        for shape in self.placed_shapes:
            shape.update_from_world()

    def clear_all_shapes(self):
        """Remove all worldspace shapes from the scene."""
        for shape in self.placed_shapes:
            self.minimap_scene.removeItem(shape)
        self.placed_shapes.clear()

    def get_placed_shapes_data(self) -> List[Dict]:
        """Export shape data for serialization."""
        return [
            {
                "world_x": s.world_x,
                "world_y": s.world_y,
                "label": s._label,
            }
            for s in self.placed_shapes
        ]

    # ==================== End Worldspace Shape Methods ====================
    
    def show_formation_context_menu(self, unit_item: MapUnitItem, global_pos):
        """Show right-click context menu for formation options."""
        if self.oob_data is None:
            QMessageBox.warning(self, "Error", "OOB data not loaded. Cannot apply formations.")
            return
        
        # Deselect all other units and select only this one
        self.minimap_scene.clearSelection()
        unit_item.setSelected(True)
        
        # Create context menu
        menu = QMenu(self)
        action = menu.addAction(unit_item.formation) # Intially just fill with OOB formation, can add all possible ones later.
        menu.addSeparator()
        cancel_action = menu.addAction("Cancel")
        
        # Connect actions
        action.triggered.connect(
            lambda: self.apply_formation(unit_item, unit_item.formation)
        )
        
        # Show menu
        menu.exec(global_pos)

    def apply_formation(self, parent_unit_item: MapUnitItem, formation_type: str):
        """Apply a formation (road or line) to a unit and all its children."""
        if self.oob_data is None:
            QMessageBox.warning(self, "Error", "OOB data not loaded.")
            return
        try:
            # Get the parent unit's row data
            parent_row_index = parent_unit_item.unit_row_index
            parent_row = self.oob_data.get_row(parent_row_index)
            parent_key = self.oob_data.get_hierarchy_key(parent_row, parent_row_index)
            parent_pos = (parent_unit_item.world_x, parent_unit_item.world_y)
            parent_rotation = parent_unit_item.rotation()
            
            # Get all subordinate row indices (children + self)
            subordinate_indices = self.oob_data.get_subordinate_row_indices(parent_row_index)
            
            # Build hierarchy keys and unit data dict for all subordinates
            all_units_by_key = {}
            children_keys = []
            
            for sub_row_index in subordinate_indices:
                if sub_row_index == parent_row_index:
                    continue  # Skip the parent itself
                
                sub_row = self.oob_data.get_row(sub_row_index)
                sub_key = self.oob_data.get_hierarchy_key(sub_row, sub_row_index)
                children_keys.append(sub_key)
                all_units_by_key[sub_key] = {
                    "row_index": sub_row_index,
                    "row": sub_row,
                }
            
            # Build ActualFormation strength recursively from children
            def build_strength(row_index: int) -> 'ActualFormation':
                sub_row = self.oob_data.get_row(row_index)
                archetype_id = sub_row.get("Formation", "")
                level = self.oob_data.get_level_from_hierarchy(sub_row)
                if level is None:
                    raise ValueError(f"Cannot determine level for row {row_index}")
                if level >= 6:
                    # Fighting formation: strength is Head Count (int)
                    head_count = sub_row.get("Head Count", 0)
                    return ActualFormation(archetype_id=archetype_id, strength=int(head_count))
                else:
                    # Command formation: strength is a list of direct sub-formations
                    all_sub_indices = self.oob_data.get_subordinate_row_indices(row_index)
                    # Only recurse into direct children (level = parent level + 1)
                    direct_children = [
                        idx for idx in all_sub_indices
                        if self.oob_data.get_level_from_hierarchy(self.oob_data.get_row(idx)) == level + 1
                    ]
                    sub_formations = [build_strength(idx) for idx in direct_children]
                    return ActualFormation(archetype_id=archetype_id, strength=sub_formations)
            
            parent_formation = build_strength(parent_row_index)
            positions = parent_formation.get_positions()
            
            if not positions:
                QMessageBox.information(self, "No Positions", "Formation has no valid positions to apply.")
                return
            
            # Build mapping from seq number to subordinate row data
            # seq 1 = parent, seq 2+ = children in OOB order
            seq_to_sub = {1: (parent_row_index, parent_row)}
            for i, sub_row_index in enumerate(subordinate_indices):
                sub_row = self.oob_data.get_row(sub_row_index)
                seq_to_sub[i + 2] = (sub_row_index, sub_row)
            
            # Calculate world positions for each unit from relative yard offsets
            units_to_select = [parent_unit_item]
            
            for seq_str, (rel_x_yards, rel_y_yards, length, depth) in positions.items():
                seq = int(seq_str)
                if seq == 1:
                    # Parent stays where it is
                    continue
                
                sub_row_index, sub_row = seq_to_sub.get(seq, (None, None))
                if sub_row_index is None:
                    continue
                
                # Convert relative yard positions to world coordinates
                world_x = parent_unit_item.world_x + int(rel_x_yards * self.units_per_yard)
                world_y = parent_unit_item.world_y + int(rel_y_yards * self.units_per_yard)
                # Find existing placed unit or place new one
                unit_item = None
                for placed_unit in self.placed_units:
                    if placed_unit.unit_row_index == sub_row_index:
                        unit_item = placed_unit
                        break
                
                if unit_item is not None:
                    # Unit already placed - update its position
                    unit_item.world_x = world_x
                    unit_item.world_y = world_y
                    scene_pos = self.world_to_scene(world_x, world_y)
                    unit_item.setPos(scene_pos)
                    unit_item._rebuild_scene_geometry()
                    units_to_select.append(unit_item)
                else:
                    # Unit not yet placed - place it at the formation position
                    unit_data = {
                        "name": sub_row.get("NAME1", f"Unit {sub_row_index}"),
                        "side": int(sub_row.get("SIDE 1", 1)),
                        "level": self.oob_data.get_level_from_hierarchy(sub_row),
                        "formation": sub_row.get("Formation", ""),
                    }
                    self._place_unit(sub_row_index, world_x, world_y, unit_data)
                    
                    # Find the newly created unit and add to selection
                    for placed_unit in self.placed_units:
                        if placed_unit.unit_row_index == sub_row_index:
                            units_to_select.append(placed_unit)
                            break
            
            # Select all units in the formation
            for unit in units_to_select:
                unit.setSelected(True)
            
    #         if not children_keys:
    #             QMessageBox.information(self, "No Children", "This unit has no subordinates to arrange.")
    #             return
            
    #         # Calculate formation positions
    #         if formation_type == "road":
    #             positions = calculate_road_formation(
    #                 parent_pos,
    #                 parent_rotation,
    #                 children_keys,
    #                 all_units_by_key,
    #                 spacing=100.0
    #             )
    #         elif formation_type == "line":
    #             positions = calculate_line_formation(
    #                 parent_pos,
    #                 parent_rotation,
    #                 children_keys,
    #                 all_units_by_key,
    #                 spacing=100.0
    #             )
    #         else:
    #             QMessageBox.warning(self, "Error", f"Unknown formation type: {formation_type}")
    #             return
            
    #         # Apply positions to placed units and place any not yet on the map
    #         units_to_select = [parent_unit_item]
    #         for unit_key, (world_x, world_y) in list(positions.items())[1:]: # Skip the parent unit which is at index 0
    #             row_index = all_units_by_key[unit_key]["row_index"]
    #             row = all_units_by_key[unit_key]["row"]
                
    #             # Find the corresponding MapUnitItem
    #             unit_item = None
    #             for placed_unit in self.placed_units:
    #                 if placed_unit.unit_row_index == row_index:
    #                     unit_item = placed_unit
    #                     break
                
    #             if unit_item is not None:
    #                 # Unit is already placed - update its position
    #                 unit_item.world_x = world_x
    #                 unit_item.world_y = world_y
                    
    #                 # Update scene position
    #                 scene_pos = self.world_to_scene(world_x, world_y)
    #                 unit_item.setPos(scene_pos)
    #                 units_to_select.append(unit_item)
    #             else:
    #                 # Unit is not yet placed - place it at the formation position
    #                 unit_data = {
    #                     "row_index": row_index,
    #                     "name": row.get("NAME1", f"Unit {row_index}"),
    #                     "side": int(row.get("SIDE 1", 1)),
    #                     "level": self.oob_data.get_level_from_hierarchy(row),
    #                     "formation": row.get("Formation", ""),
    #                 }
    #                 self._place_unit(row_index, world_x, world_y, unit_data)
                    
    #                 # Find the newly created unit item and add to selection
    #                 for placed_unit in self.placed_units:
    #                     if placed_unit.unit_row_index == row_index:
    #                         units_to_select.append(placed_unit)
    #                         break
            
    #         # Select all units in the formation
    #         for unit in units_to_select:
    #             unit.setSelected(True)
            
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            QMessageBox.critical(
                self,
                "Formation Error",
                f"Failed to apply formation:\n{str(e)}\n\n{tb_str}"
            )
    
    def resizeEvent(self, event):
        """Handle widget resize to rescale minimap when panel expands."""
        super().resizeEvent(event)
        if self.minimap_pixmap is not None:
            self.display_minimap()
            self._update_placed_unit_positions()
            self.update_all_shapes()

    def on_minimap_resize(self, event):
        """Handle minimap label resize to rescale the displayed pixmap."""
        if self.minimap_pixmap is not None:
            self.display_minimap()
