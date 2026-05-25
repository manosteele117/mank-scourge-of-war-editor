from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsView, QGraphicsScene, QGraphicsLineItem
from PySide6.QtCore import Qt, Signal, QRectF, QLineF
from PySide6.QtGui import QWheelEvent, QPainter, QPen, QColor
from oob_model import OOBData
from oob_visual_shapes import get_shape_class_for_level, UnitGraphicsItem
from oob_visual_layout import HierarchicalLayout
import time

class OOBVisualWidget(QWidget):
    """
    Widget for visual representation of Order of Battle formations.
    
    Displays units in a hierarchical tree-like structure with shape-based
    representations (circles, hexagons, pentagons, etc.). Each unit is
    selectable and syncs with the tree view.
    """
    
    # Signal emitted when a unit is selected in the visual view
    unit_selected = Signal(int)  # Emits row_index
    
    def __init__(self, data: OOBData, parent=None):
        super().__init__(parent)
        
        self.data = data

        start = time.time()
        self.layout_engine = HierarchicalLayout(data)
        print(f"Layout engine initialized in {time.time() - start:.2f} seconds")

        self.scene = QGraphicsScene()
        self.view = OOBGraphicsView(self.scene)
        self.view.unit_clicked.connect(self._on_unit_clicked)
        
        # Setup widget layout
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
        
        # Track graphics items by row_index for selection sync
        self.items_by_row_index = {}
    
    def populate(self, row_index: int = None) -> None:
        """
        Populate the visual view with the entire OOB hierarchy.
        
        Args:
            row_index: Optional, currently unused (always shows full OOB)
        """
        self.scene.clear()
        self.items_by_row_index.clear()
        
        if len(self.data.df) == 0:
            return
        
        # Calculate positions for all units
        start = time.time()
        positions = self.layout_engine.calculate_layout(root_row_index=row_index)
        print(f"Layout calculated in {time.time() - start:.2f} seconds")
        
        start = time.time()
        # Create graphics items for each unit
        for unit_row_idx, (x, y) in positions.items():
            row = self.data.get_row(unit_row_idx)
            level = self.data.get_level_from_hierarchy(row)
            side = int(row.get("SIDE 1", 1))
            name = str(row.get("NAME1", "Unknown"))
            
            # Get appropriate shape class
            shape_class = get_shape_class_for_level(level)
            
            # Create graphics item
            item = shape_class(
                name=name,
                unit_row_index=unit_row_idx,
                side=side,
                level=level
            )
            item.setPos(x, y)
            
            # Add to scene and track
            self.scene.addItem(item)
            self.items_by_row_index[unit_row_idx] = item
        print(f"Graphics items created in {time.time() - start:.2f} seconds")

        # Draw light dotted line at y=0
        if positions:
            x_coords = [x for x, y in positions.values()]
            x_min = min(x_coords) - 100
            x_max = max(x_coords) + 100
            line = QGraphicsLineItem(x_min, 0, x_max, 0)
            pen = QPen(QColor("#a9a9a9"))
            pen.setStyle(Qt.DashLine)
            line.setPen(pen)
            self.scene.addItem(line)

        # Fit scene in view
        self.view.reset_view(self.scene.itemsBoundingRect())
    
    def clear(self) -> None:
        """Clear the visual view."""
        self.scene.clear()
        self.items_by_row_index.clear()
    
    def highlight_unit(self, row_index: int) -> None:
        """
        Highlight a unit in the visual view (called when tree selection changes).
        
        Args:
            row_index: The row index of the unit to highlight
        """
        # Clear previous selections
        for item in self.items_by_row_index.values():
            if isinstance(item, UnitGraphicsItem):
                item.set_selected(False)
        
        # Select the target unit
        if row_index in self.items_by_row_index:
            item = self.items_by_row_index[row_index]
            if isinstance(item, UnitGraphicsItem):
                item.set_selected(True)

    def _on_reset_view(self) -> None:
        """Reset the visual scene to its full bounds."""
        self.view.reset_view(self.scene.itemsBoundingRect())
    
    def _on_regenerate_view(self) -> None:
        """Regenerate the visual view (called by user or when data changes)."""
        self.populate()

    def _on_unit_clicked(self, unit_row_index: int) -> None:
        """
        Handle unit click from graphics view.
        
        Args:
            unit_row_index: The row index of the clicked unit
        """
        self.highlight_unit(unit_row_index)
        self.unit_selected.emit(unit_row_index)


class OOBGraphicsView(QGraphicsView):
    """
    Custom graphics view with zoom and selection capabilities.
    """
    
    # Signal emitted when a unit is clicked
    unit_clicked = Signal(int)  # Emits row_index
    
    # Zoom constants
    MIN_ZOOM = 0.1
    MAX_ZOOM = 50.0
    ZOOM_FACTOR = 1.2
    
    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        
        self.zoom_level = 1.0
        self.last_mouse_pos = None
        self.panning = False
        self.pan_start = None
        
        # Enable antialiasing
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Styling
        self.setStyleSheet("background-color: #2c2c2c;")
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for zoom."""
        # Get the angle delta
        angle = event.angleDelta().y()
        
        if angle > 0:
            # Scroll up = zoom in
            factor = self.ZOOM_FACTOR
        else:
            # Scroll down = zoom out
            factor = 1 / self.ZOOM_FACTOR
        
        # Apply zoom limits
        new_zoom = self.zoom_level * factor
        if new_zoom < self.MIN_ZOOM or new_zoom > self.MAX_ZOOM:
            return
        
        # Zoom centered on cursor
        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self.zoom_level = new_zoom
    
    def reset_view(self, rect: QRectF) -> None:
        """Reset the view transform and fit the scene rectangle."""
        if rect.isNull() or not rect.isValid():
            return
        self.resetTransform()
        self.zoom_level = 1.0
        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
    
    def mousePressEvent(self, event):
        """Handle mouse clicks and right-button panning."""
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
        """Handle right-button drag panning."""
        if self.panning and self.pan_start is not None:
            delta = event.pos() - self.pan_start
            self.pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Stop panning when the right mouse button is released."""
        if event.button() == Qt.MouseButton.RightButton and self.panning:
            self.panning = False
            self.pan_start = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
