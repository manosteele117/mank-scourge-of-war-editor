from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtCore import Qt, QRect, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
import math


class UnitGraphicsItem(QGraphicsItem):
    """
    Base class for visual unit representations.
    
    Each unit is rendered as a shape with a text label. Supports selection,
    hovering, and stores the row index for selection tracking.
    """
    
    # Shape size constants (in logical units)
    BASE_SIZE = 60
    
    # Color constants
    COLOR_SIDE_1 = QColor("#2c5aa0")  # Blue for French
    COLOR_SIDE_2 = QColor("#a02c2c")  # Red for Allied
    COLOR_BORDER_NORMAL = QColor("#ffffff")
    COLOR_BORDER_SELECTED = QColor("#ffff00")  # Yellow highlight
    COLOR_BORDER_HOVER = QColor("#64b5f6")     # Light blue hover
    COLOR_TEXT = QColor("#ffffff")
    
    def __init__(self, name: str, unit_row_index: int, side: int, level: int, parent=None):
        """
        Initialize a unit graphics item.
        
        Args:
            name: Display name of the unit
            unit_row_index: Index in the dataframe (for selection tracking)
            side: 1 or 2 (French or Allied)
            level: Hierarchy level (1-6)
            parent: Parent QGraphicsItem
        """
        super().__init__(parent)
        
        self.name = name
        self.unit_row_index = unit_row_index
        self.side = side
        self.level = level
        self.is_selected = False
        self.is_hovered = False
        
        # Store row index as item data for easy retrieval
        self.setData(Qt.UserRole, unit_row_index)
        
        # Make item selectable
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        
        # Set bounding rect for hit detection
        size = self.BASE_SIZE
        self.setPos(0, 0)
    
    def get_side_color(self) -> QColor:
        """Return the color for this unit's side."""
        return self.COLOR_SIDE_1 if self.side == 1 else self.COLOR_SIDE_2
    
    def get_border_color(self) -> QColor:
        """Return the border color based on selection/hover state."""
        if self.is_selected:
            return self.COLOR_BORDER_SELECTED
        elif self.is_hovered:
            return self.COLOR_BORDER_HOVER
        else:
            return self.COLOR_BORDER_NORMAL
    
    def paint(self, painter: QPainter, option, widget=None):
        """Override to paint the shape and text label."""
        # Draw the shape (implemented by subclasses)
        self.draw_shape(painter)
        
        # Draw text label
        self.draw_text(painter)
    
    def draw_shape(self, painter: QPainter):
        """Draw the unit shape. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement draw_shape")
    
    def draw_text(self, painter: QPainter):
        """Draw the unit name as text centered on the shape."""
        # Simple centered text
        font = QFont("Arial", 8)
        painter.setFont(font)
        painter.setPen(QPen(self.COLOR_TEXT))
        
        # Get bounding rect and draw text centered
        rect = self.boundingRect()
        painter.drawText(rect, Qt.AlignCenter, self.name)
    
    def mousePressEvent(self, event):
        """Handle mouse click on the item."""
        self.is_selected = True
        self.update()
        super().mousePressEvent(event)
    
    def hoverEnterEvent(self, event):
        """Handle mouse hover enter."""
        self.is_hovered = True
        self.update()
    
    def hoverLeaveEvent(self, event):
        """Handle mouse hover leave."""
        self.is_hovered = False
        self.update()
    
    def set_selected(self, selected: bool):
        """Set selection state (called from external selection sync)."""
        self.is_selected = selected
        self.update()


class CircleItem(UnitGraphicsItem):
    """Circle shape for Side (Level 1)."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        size = self.BASE_SIZE
        return QRect(-size // 2, -size // 2, size, size)
    
    def draw_shape(self, painter: QPainter):
        """Draw a circle."""
        rect = self.boundingRect()
        
        # Fill
        painter.fillRect(rect, QBrush(self.get_side_color()))
        
        # Border
        pen = QPen(self.get_border_color(), 2)
        painter.setPen(pen)
        painter.drawEllipse(rect)


class HexagonItem(UnitGraphicsItem):
    """Hexagon shape for Army (Level 2)."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        size = self.BASE_SIZE
        return QRect(-size // 2, -size // 2, size, size)
    
    def draw_shape(self, painter: QPainter):
        """Draw a hexagon."""
        size = self.BASE_SIZE / 2
        center = QPointF(0, 0)
        
        # Create hexagon points
        points = []
        for i in range(6):
            angle = math.pi / 3 * i  # 60-degree increments
            x = center.x() + size * math.cos(angle)
            y = center.y() + size * math.sin(angle)
            points.append(QPointF(x, y))
        
        # Fill
        painter.setBrush(QBrush(self.get_side_color()))
        painter.setPen(QPen(self.get_border_color(), 2))
        painter.drawPolygon(points)


class PentagonItem(UnitGraphicsItem):
    """Pentagon shape for Corps (Level 3)."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        size = self.BASE_SIZE
        return QRect(-size // 2, -size // 2, size, size)
    
    def draw_shape(self, painter: QPainter):
        """Draw a pentagon."""
        size = self.BASE_SIZE / 2
        center = QPointF(0, 0)
        
        # Create pentagon points
        points = []
        for i in range(5):
            angle = math.pi / 2.5 * i - math.pi / 2  # Start from top
            x = center.x() + size * math.cos(angle)
            y = center.y() + size * math.sin(angle)
            points.append(QPointF(x, y))
        
        # Fill
        painter.setBrush(QBrush(self.get_side_color()))
        painter.setPen(QPen(self.get_border_color(), 2))
        painter.drawPolygon(points)


class DiamondItem(UnitGraphicsItem):
    """Diamond shape for Division (Level 4)."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        size = self.BASE_SIZE
        return QRect(-size // 2, -size // 2, size, size)
    
    def draw_shape(self, painter: QPainter):
        """Draw a diamond."""
        size = self.BASE_SIZE / 2
        center = QPointF(0, 0)
        
        # Create diamond points
        points = [
            QPointF(center.x(), center.y() - size),      # Top
            QPointF(center.x() + size, center.y()),      # Right
            QPointF(center.x(), center.y() + size),      # Bottom
            QPointF(center.x() - size, center.y()),      # Left
        ]
        
        # Fill
        painter.setBrush(QBrush(self.get_side_color()))
        painter.setPen(QPen(self.get_border_color(), 2))
        painter.drawPolygon(points)


class TriangleItem(UnitGraphicsItem):
    """Triangle shape for Brigade (Level 5)."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        size = self.BASE_SIZE
        return QRect(-size // 2, -size // 2, size, size)
    
    def draw_shape(self, painter: QPainter):
        """Draw a triangle (pointing up)."""
        size = self.BASE_SIZE / 2
        center = QPointF(0, 0)
        
        # Create triangle points
        points = [
            QPointF(center.x(), center.y() - size),           # Top
            QPointF(center.x() + size, center.y() + size),    # Bottom right
            QPointF(center.x() - size, center.y() + size),    # Bottom left
        ]
        
        # Fill
        painter.setBrush(QBrush(self.get_side_color()))
        painter.setPen(QPen(self.get_border_color(), 2))
        painter.drawPolygon(points)


class RectangleItem(UnitGraphicsItem):
    """Rectangle shape for Regiment (Level 6)."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        width = self.BASE_SIZE
        height = self.BASE_SIZE * 0.7  # Slightly shorter than wide
        return QRect(-width // 2, -height // 2, width, height)
    
    def draw_shape(self, painter: QPainter):
        """Draw a rectangle."""
        rect = self.boundingRect()
        
        # Fill
        painter.fillRect(rect, QBrush(self.get_side_color()))
        
        # Border
        pen = QPen(self.get_border_color(), 2)
        painter.setPen(pen)
        painter.drawRect(rect)


def get_shape_class_for_level(level: int):
    """
    Get the appropriate shape class for a given hierarchy level.
    
    Args:
        level: Hierarchy level (1-6)
    
    Returns:
        Shape class (CircleItem, HexagonItem, etc.)
    """
    shape_map = {
        1: CircleItem,
        2: HexagonItem,
        3: PentagonItem,
        4: DiamondItem,
        5: TriangleItem,
        6: RectangleItem,
    }
    return shape_map.get(level, RectangleItem)
