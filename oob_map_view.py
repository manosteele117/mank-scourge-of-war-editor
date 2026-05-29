import os
import configparser
from pathlib import Path

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
)
from PySide6.QtGui import QPixmap, QFont, QPainter, QImage
from PySide6.QtCore import Qt, QPoint
from PIL import Image

from utilities import get_tga_dimensions


class OOBMapWidget(QWidget):
    """Widget for displaying map information and minimap visualization."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Map data storage
        self.map_ini_path = None
        self.lsl_path = None
        self.minimap_path = None
        self.tga_width = None
        self.tga_height = None
        self.minimap_pixmap = None
        self.minimap_display_size = None  # Size of displayed pixmap in pixels
        self.tile_scale = 512
        
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
        
        control_layout.addStretch()
        
        control_widget = QWidget()
        control_widget.setLayout(control_layout)
        main_layout.addWidget(control_widget, 0)
        
        # Status/Info panel
        self.info_label = QLabel("No map loaded")
        main_layout.addWidget(self.info_label, 0)
        
        # Minimap display area
        self.minimap_scene = QGraphicsScene()
        self.minimap_view = QGraphicsView(self.minimap_scene)
        self.minimap_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minimap_view.setRenderHints(self.minimap_view.renderHints() | QPainter.Antialiasing)
        self.minimap_view.setMouseTracking(True)
        self.minimap_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.minimap_view.setStyleSheet("border: 1px solid #333333; background-color: #1a1a1a;")
        self.minimap_view.mouseMoveEvent = self.on_minimap_mouse_move
        self.minimap_view.leaveEvent = self.on_minimap_mouse_leave
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
        
        # Clear previous scene and add scaled pixmap
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
        self.minimap_scene.addPixmap(scaled_pixmap)
        
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
        # Coordinates will be recalculated on next mouse move via on_minimap_mouse_move()
    
    def resizeEvent(self, event):
        """Handle widget resize to rescale minimap when panel expands."""
        super().resizeEvent(event)
        if self.minimap_pixmap is not None:
            self.display_minimap()

    def on_minimap_resize(self, event):
        """Handle minimap label resize to rescale the displayed pixmap."""
        if self.minimap_pixmap is not None:
            self.display_minimap()
