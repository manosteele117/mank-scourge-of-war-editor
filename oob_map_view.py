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
)
from PySide6.QtGui import QPixmap, QFont, QPainter, QImage, QPen, QBrush, QColor
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PIL import Image

from utilities import get_tga_dimensions


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
        elif self.map_widget.placement_mode:
            self.map_widget.on_map_clicked(event)
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
    
    def wheelEvent(self, event):
        """Handle scroll wheel for rotation. Zoom disabled when unit is selected, which allows rotation instead. 
        Placement mode locks both currently."""
        if not self.map_widget.placement_mode:
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
        super().wheelEvent(event)


class MapUnitItem(QGraphicsItem):
    """
    A map-placed unit representation on the minimap.
    
    Stores world coordinates and handles rendering as a shape on the map.
    Supports drag, rotate, and selection.
    """
    
    # Size constants
    SHAPE_SIZE = 15
    
    # Colors
    COLOR_SIDE_1 = QColor("#2c5aa0")  # Blue
    COLOR_SIDE_2 = QColor("#a02c2c")  # Red
    COLOR_BORDER_NORMAL = QColor("#aaaaaa")
    COLOR_BORDER_SELECTED = QColor("#ffff00")
    COLOR_BORDER_HOVER = QColor("#64b5f6")
    
    def __init__(self, name: str, unit_row_index: int, side: int, level: int, formation: str, world_x: int, world_y: int, map_widget=None, parent=None):
        """
        Initialize a map unit item.
        
        Args:
            name: Unit name
            unit_row_index: Row index in OOBData
            side: 1 or 2
            level: Hierarchy level (1-6)
            formation: Formation type
            world_x: World coordinate X
            world_y: World coordinate Y
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
        
        # Store row index for selection tracking
        self.setData(Qt.UserRole, unit_row_index)
        
        # Enable interaction
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
        # Default rotation
        self.setRotation(0)
    
    def boundingRect(self):
        """Return tight bounding rectangle."""
        size = self.SHAPE_SIZE * 2
        return QRectF(-size - 5, -size - 5, size * 2 + 10, size * 2 + 10)
    
    def paint(self, painter: QPainter, option, widget=None):
        """Paint the unit shape."""
        # Determine colors
        side_color = self.COLOR_SIDE_1 if self.side == 1 else self.COLOR_SIDE_2
        if self.isSelected():
            side_color = side_color.lighter(150)
        elif self.is_hovered:
            side_color = side_color.lighter(120)
        
        border_color = self.COLOR_BORDER_SELECTED if self.isSelected() else self.COLOR_BORDER_HOVER if self.is_hovered else self.COLOR_BORDER_NORMAL
        
        # Draw a circle/shape based on level
        painter.setBrush(QBrush(side_color))
        painter.setPen(QPen(border_color, 2))
        
        # Draw circle for simplicity (can be extended to use proper shapes)
        radius = self.SHAPE_SIZE
        painter.drawEllipse(QPointF(0, 0), radius, radius)
        
        # Draw level indicator (number of stars or dots)
        num_stars = min(self.level, 3)  # Max 3 stars for readability
        star_spacing = radius * 0.6
        for i in range(num_stars):
            x = (i - (num_stars - 1) / 2) * star_spacing
            painter.drawEllipse(QPointF(x, -radius - 5), 2, 2)
    
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
            self.world_x, self.world_y = self.map_widget.scene_to_world(self.pos().x(), self.pos().y())
        return super().itemChange(change, value)


class OOBMapWidget(QWidget):
    """Widget for displaying map information and minimap visualization."""
    
    # Signals
    unit_placed = Signal(int, int, int)  # (row_index, world_x, world_y)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Map data storage
        self.map_ini_path = None
        self.lsl_path = None
        self.minimap_path = None
        self.tga_width = None
        self.tga_height = None
        self.minimap_pixmap = None
        self.minimap_pixmap_item = None
        self.minimap_display_size = None  # Size of displayed pixmap in pixels
        self.tile_scale = 512
        self.units_per_yard = 30
        
        # Placement mode data
        self.placement_mode = False
        self.pending_placement_row = None
        self.pending_placement_data = {}
        self.placed_units: List[MapUnitItem] = []
        self.placed_row_indices: set = set()  # track row indices to prevent duplicates
        self.max_units = 50
        self.placement_button = None
        self.unit_label = None
        self.unit_count_label = None
        
        self.init_ui()
    
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
        
        # Placement mode button
        self.placement_button = QPushButton("Placement Mode: OFF")
        self.placement_button.setCheckable(True)
        self.placement_button.toggled.connect(self.on_placement_mode_toggled)
        self.placement_button.setMaximumWidth(150)
        control_layout.addWidget(self.placement_button)
        
        # Unit label
        self.unit_label = QLabel("Unit: ---")
        self.unit_label.setMaximumWidth(200)
        control_layout.addWidget(self.unit_label)
        
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
        for unit in placed_units_backup:
            self.minimap_scene.addItem(unit)
        
        # Fit view to scene contents
        self.minimap_view.fitInView(self.minimap_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
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
        
        # Get the scaled pixmap from the scene
        items = self.minimap_scene.items()
        if not items:
            self.coord_label.setText("Coordinates: --")
            return
        
        # The first item should be the pixmap item
        pixmap_item = items[0]
        pixmap_width = pixmap_item.boundingRect().width()
        pixmap_height = pixmap_item.boundingRect().height()
        
        # Calculate relative position within the scaled pixmap
        pixel_x = scene_pos.x() - scene_rect.x()
        pixel_y = scene_pos.y() - scene_rect.y()
        
        # Check if within scaled pixmap bounds
        if pixel_x < 0 or pixel_y < 0 or pixel_x >= pixmap_width or pixel_y >= pixmap_height:
            self.coord_label.setText("Coordinates: --")
            return
        
        # Calculate world coordinates based on scaled pixmap dimensions
        # Formula: world_coord = (pixel_coord / scaled_pixmap_dimension) * (tile_scale * tga_dimension)
        world_x = int((pixel_x / pixmap_width) * (self.tile_scale * self.tga_width))
        world_y = int((pixel_y / pixmap_height) * (self.tile_scale * self.tga_height))
        
        self.coord_label.setText(f"Coordinates: ({world_x}, {world_y})")
    
    def on_minimap_mouse_leave(self, event):
        """Handle mouse leaving the minimap area."""
        self.coord_label.setText("Coordinates: --")
    
    def on_tile_scale_changed(self, value: int):
        """Handle tile scale spinbox value change."""
        self.tile_scale = value
        self._update_placed_unit_positions()
        # Coordinates will be recalculated on next mouse move via on_minimap_mouse_move()
    
    def on_units_per_yard_changed(self, value: int):
        """Handle units per yard spinbox value change."""
        self.units_per_yard = value
    
    # ==================== Placement Mode Methods ====================
    
    def on_placement_mode_toggled(self, enabled: bool):
        """Handle placement mode toggle."""
        self.placement_mode = enabled
        if enabled:
            self.placement_button.setText("Placement Mode: ON")
            self.placement_button.setStyleSheet("background-color: #2c5aa0;")
        else:
            self.placement_button.setText("Placement Mode: OFF")
            self.placement_button.setStyleSheet("")
            self.pending_placement_row = None
            self.unit_label.setText("Unit: ---")
    
    def set_pending_unit(self, row_index: int, unit_name: str, side: int = 1, level: int = 1, formation: str = ""):
        """Set which unit is pending placement from the tree view."""

        if not self.placement_mode:
            self.placement_mode = True
            self.placement_button.setChecked(True)
        
        self.pending_placement_row = row_index
        self.pending_placement_data = {
            "name": unit_name,
            "side": side,
            "level": level,
            "formation": formation,
        }
        self.unit_label.setText(f"Unit: {unit_name}")
    
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
    
    def on_map_clicked(self, event):
        """Handle map click in placement mode."""
        if self.pending_placement_row is None:
            return
                # Only allow levels 1-4 (Side, Army, Corps, Division) to be placed
        level = self.pending_placement_data.get("level", 1)
        if level is None or level > 4:
            QMessageBox.information(
                None,
                "Placement Restricted",
                f"Only levels 1-4 (Side, Army, Corps, Division) can be placed on the map.\n"
                f"Selected unit is level {level}: {self.pending_placement_data.get("name", f"Unit {len(self.placed_units) + 1}")}"
            )
            return
        # Check for duplicate placement
        if self.pending_placement_row in self.placed_row_indices:
            unit_name = self.pending_placement_data.get("name", "Unknown")
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
        
        scene_pos = self.minimap_view.mapToScene(event.pos())
        scene_rect = self.minimap_scene.sceneRect()
        
        if not scene_rect.contains(scene_pos):
            return
        
        world_x, world_y = self.scene_to_world(scene_pos.x(), scene_pos.y())
        self._place_unit(self.pending_placement_row, world_x, world_y)
    
    def _place_unit(self, row_index: int, world_x: int, world_y: int):
        """Create and place a unit on the map."""
        # Get unit data from pending placement data
        name = self.pending_placement_data.get("name", f"Unit {len(self.placed_units) + 1}")
        side = self.pending_placement_data.get("side", 1)
        level = self.pending_placement_data.get("level", 1)
        formation = self.pending_placement_data.get("formation", "")
        
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
    
    def resizeEvent(self, event):
        """Handle widget resize to rescale minimap when panel expands."""
        super().resizeEvent(event)
        if self.minimap_pixmap is not None:
            self.display_minimap()
            self._update_placed_unit_positions()

    def on_minimap_resize(self, event):
        """Handle minimap label resize to rescale the displayed pixmap."""
        if self.minimap_pixmap is not None:
            self.display_minimap()
