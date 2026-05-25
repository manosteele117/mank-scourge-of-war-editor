from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtCore import Qt, QRect, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
import math


def draw_star(painter: QPainter, center: QPointF, size: float, color: QColor, border_color: QColor) -> None:
    """
    Draw a single 5-pointed star.
    
    Args:
        painter: QPainter object to draw with
        center: Center point of the star
        size: Radius of the star
        color: Fill color
        border_color: Border color
    """
    # Calculate 5-pointed star points
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        if i % 2 == 0:
            # Outer point
            r = size
        else:
            # Inner point
            r = size * 0.4
        x = center.x() + r * math.cos(angle)
        y = center.y() - r * math.sin(angle)
        points.append(QPointF(x, y))
    
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(border_color, 1.5))
    painter.drawPolygon(points)


class UnitGraphicsItem(QGraphicsItem):
    """
    Base class for visual unit representations.
    
    Each unit is rendered as star(s) with a text label. Supports selection,
    hovering, and stores the row index for selection tracking.
    """
    
    
    # Star size constants (in logical units)
    STAR_SIZE = 12
    BASE_SIZE = 60  # Base size for non-star shapes
    
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


class StarLevel1Item(UnitGraphicsItem):
    """Level 1 (Side): 5 stars arranged in a tight circle."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        size = self.STAR_SIZE * 3.5
        return QRect(-int(size), -int(size), int(size * 2), int(size * 2))
    
    def draw_shape(self, painter: QPainter):
        """Draw 5 stars in a tight circle."""
        center = QPointF(0, 0)
        radius = self.STAR_SIZE * 1.2
        color = self.get_side_color()
        border_color = self.get_border_color()
        
        # Arrange 5 stars in a circle
        for i in range(5):
            angle = (2 * math.pi * i) / 5 - math.pi / 2
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            draw_star(painter, QPointF(x, y), self.STAR_SIZE, color, border_color)


class StarLevel2Item(UnitGraphicsItem):
    """Level 2 (Army): 4 stars in a tight horizontal line."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        width = self.STAR_SIZE * 5.5
        height = self.STAR_SIZE * 2.5
        return QRect(-int(width/2), -int(height/2), int(width), int(height))
    
    def draw_shape(self, painter: QPainter):
        """Draw 4 stars in a horizontal line."""
        center = QPointF(0, 0)
        spacing = self.STAR_SIZE * 0.8
        color = self.get_side_color()
        border_color = self.get_border_color()
        
        # Arrange 4 stars horizontally
        for i in range(4):
            x = center.x() + (i - 1.5) * spacing
            y = center.y()
            draw_star(painter, QPointF(x, y), self.STAR_SIZE, color, border_color)


class StarLevel3Item(UnitGraphicsItem):
    """Level 3 (Corps): 3 stars in a tight horizontal line."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        width = self.STAR_SIZE * 4.5
        height = self.STAR_SIZE * 2.5
        return QRect(-int(width/2), -int(height/2), int(width), int(height))
    
    def draw_shape(self, painter: QPainter):
        """Draw 3 stars in a horizontal line."""
        center = QPointF(0, 0)
        spacing = self.STAR_SIZE * 0.8
        color = self.get_side_color()
        border_color = self.get_border_color()
        
        # Arrange 3 stars horizontally
        for i in range(3):
            x = center.x() + (i - 1) * spacing
            y = center.y()
            draw_star(painter, QPointF(x, y), self.STAR_SIZE, color, border_color)


class StarLevel4Item(UnitGraphicsItem):
    """Level 4 (Division): 2 stars in a tight horizontal line."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        width = self.STAR_SIZE * 3.5
        height = self.STAR_SIZE * 2.5
        return QRect(-int(width/2), -int(height/2), int(width), int(height))
    
    def draw_shape(self, painter: QPainter):
        """Draw 2 stars in a horizontal line."""
        center = QPointF(0, 0)
        spacing = self.STAR_SIZE * 0.8
        color = self.get_side_color()
        border_color = self.get_border_color()
        
        # Arrange 2 stars horizontally
        for i in range(2):
            x = center.x() + (i - 0.5) * spacing
            y = center.y()
            draw_star(painter, QPointF(x, y), self.STAR_SIZE, color, border_color)


class StarLevel5Item(UnitGraphicsItem):
    """Level 5 (Brigade): 1 star."""
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        size = self.STAR_SIZE * 1.8
        return QRect(-int(size), -int(size), int(size * 2), int(size * 2))
    
    def draw_shape(self, painter: QPainter):
        """Draw 1 star."""
        center = QPointF(0, 0)
        color = self.get_side_color()
        border_color = self.get_border_color()
        draw_star(painter, center, self.STAR_SIZE, color, border_color)


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
        Shape class for the given level (StarLevel1Item, StarLevel2Item, etc., or RectangleItem for level 6)
    """
    shape_map = {
        1: StarLevel1Item,
        2: StarLevel2Item,
        3: StarLevel3Item,
        4: StarLevel4Item,
        5: StarLevel5Item,
        6: RectangleItem,
    }
    return shape_map.get(level, RectangleItem)
