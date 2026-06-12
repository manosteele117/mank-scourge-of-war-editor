from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtCore import Qt, QRect, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QTextDocument, QTextOption
import math

from core.constants import (
    get_border_color, get_side_color,
)


def draw_star(painter: QPainter, center: QPointF, size: float, color: QColor, border_color: QColor) -> None:
    """Draw a single 5-pointed star."""
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = size if i % 2 == 0 else size * 0.4
        x = center.x() + r * math.cos(angle)
        y = center.y() - r * math.sin(angle)
        points.append(QPointF(x, y))
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(border_color, 1.5))
    painter.drawPolygon(points)


def _draw_text_label(painter: QPainter, doc: QTextDocument, rect, color: QColor,
                     center_vertically: bool = False):
    painter.setPen(QPen(color))

    painter.save()
    text_height = doc.size().height()

    if center_vertically:
        y_offset = -text_height / 2
        painter.translate(rect.left(), y_offset)
    else:
        text_x = rect.left()
        text_y = rect.bottom()
        painter.translate(text_x, text_y)

    doc.drawContents(painter, QRect(0, 0, int(rect.width() - 4), int(text_height)))
    painter.restore()


class UnitGraphicsItem(QGraphicsItem):
    """Base class for visual unit representations."""

    STAR_SIZE = 20
    BASE_SIZE = 200
    COLOR_TEXT = QColor("#ffffff")

    def __init__(self, name: str, unit_row_index: int, side: int, level: int, parent=None):
        super().__init__(parent)
        self.name = name
        self.unit_row_index = unit_row_index
        self.side = side
        self.level = level
        self.is_selected = False
        self.is_highlighted = False
        self.is_hovered = False

        self.setData(Qt.UserRole, unit_row_index)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setPos(0, 0)

        rect = self.boundingRect()
        self._text_doc = QTextDocument()
        self._text_doc.setPlainText(self.name)
        self._text_doc.setDefaultFont(QFont("Arial", 12))
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WordWrap)
        text_option.setAlignment(Qt.AlignCenter)
        self._text_doc.setDefaultTextOption(text_option)
        self._text_doc.setTextWidth(rect.width() - 4)

    def get_side_color(self) -> QColor:
        return get_side_color(
            self.side,
            is_selected=self.is_selected,
            is_hovered=self.is_hovered,
            is_highlighted=self.is_highlighted,
        )

    def get_border_color(self) -> QColor:
        return get_border_color(self.is_selected, self.is_hovered, self.is_highlighted)

    def paint(self, painter: QPainter, option, widget=None):
        self.draw_shape(painter)
        self.draw_text(painter)

    def draw_shape(self, painter: QPainter):
        raise NotImplementedError("Subclasses must implement draw_shape")

    def draw_text(self, painter: QPainter):
        _draw_text_label(painter, self._text_doc, self.boundingRect(),
                         self.COLOR_TEXT, center_vertically=False)

    def _draw_stars(self, painter: QPainter, n: int):
        center = QPointF(0, 0)
        spacing = self.STAR_SIZE * 1.3
        color = self.get_side_color()
        border_color = self.get_border_color()
        for i in range(n):
            x = center.x() + (i - (n - 1) / 2) * spacing
            draw_star(painter, QPointF(x, center.y()), self.STAR_SIZE, color, border_color)

    def boundingRect(self):
        size = self.STAR_SIZE * 3.5
        return QRect(-int(size*2), -int(size/3), int(size * 4), int(size/2))

    def mousePressEvent(self, event):
        self.is_selected = True
        self.update()
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def set_highlighted(self, highlighted: bool):
        self.is_highlighted = highlighted
        self.update()


class StarLevel1Item(UnitGraphicsItem):
    def draw_shape(self, painter: QPainter):
        self._draw_stars(painter, 5)


class StarLevel2Item(UnitGraphicsItem):
    def draw_shape(self, painter: QPainter):
        self._draw_stars(painter, 4)


class StarLevel3Item(UnitGraphicsItem):
    def draw_shape(self, painter: QPainter):
        self._draw_stars(painter, 3)


class StarLevel4Item(UnitGraphicsItem):
    def draw_shape(self, painter: QPainter):
        self._draw_stars(painter, 2)


class StarLevel5Item(UnitGraphicsItem):
    def draw_shape(self, painter: QPainter):
        self._draw_stars(painter, 1)


class RectangleItem(UnitGraphicsItem):
    def boundingRect(self):
        width = self.BASE_SIZE
        height = self.BASE_SIZE * 0.4
        return QRect(-width // 2, -height // 2, width, height)

    def draw_shape(self, painter: QPainter):
        rect = self.boundingRect()
        painter.fillRect(rect, QBrush(self.get_side_color()))
        painter.setPen(QPen(self.get_border_color(), 2))
        painter.drawRect(rect)

    def draw_text(self, painter: QPainter):
        _draw_text_label(painter, self._text_doc, self.boundingRect(),
                         self.COLOR_TEXT, center_vertically=True)


class ArtilleryItem(UnitGraphicsItem):
    def boundingRect(self):
        width = self.BASE_SIZE * 1.2
        height = self.BASE_SIZE * 0.7
        return QRect(-width // 2, -height // 2, width, height)

    def draw_shape(self, painter: QPainter):
        color = self.get_side_color()
        border_color = self.get_border_color()

        barrel_width = 15
        barrel_height = 60
        barrel_rect = QRect(-barrel_width // 2, -barrel_height // 2, barrel_width, barrel_height)
        painter.fillRect(barrel_rect, QBrush(color))
        painter.setPen(QPen(border_color, 2))
        painter.drawRect(barrel_rect)

        wheel_width = 10
        wheel_height = 25
        left_wheel_rect = QRect(-barrel_width // 2 - wheel_width - 5, -wheel_height // 2, wheel_width, wheel_height)
        painter.fillRect(left_wheel_rect, QBrush(color))
        painter.drawRect(left_wheel_rect)

        right_wheel_rect = QRect(barrel_width // 2 + 5, -wheel_height // 2, wheel_width, wheel_height)
        painter.fillRect(right_wheel_rect, QBrush(color))
        painter.drawRect(right_wheel_rect)

        left_connector_rect = QRect(-barrel_width // 2 - 5, -8, 5, 16)
        painter.fillRect(left_connector_rect, QBrush(color))
        painter.drawRect(left_connector_rect)

        right_connector_rect = QRect(barrel_width // 2, -8, 5, 16)
        painter.fillRect(right_connector_rect, QBrush(color))
        painter.drawRect(right_connector_rect)


class WagonItem(UnitGraphicsItem):
    def boundingRect(self):
        width = self.BASE_SIZE * 1.1
        height = self.BASE_SIZE * 1.1
        return QRect(-width // 2, -height // 2, width, height)

    def draw_shape(self, painter: QPainter):
        color = self.get_side_color()
        border_color = self.get_border_color()

        body_width = 36
        body_height = 100
        body_rect = QRect(-body_width // 2, -body_height // 2, body_width, body_height)
        painter.fillRect(body_rect, QBrush(color))
        painter.setPen(QPen(border_color, 2))
        painter.drawRect(body_rect)

        wheel_height = 20
        wheel_width = 8
        wheel_offset_x = body_width // 2 + 8
        wheel_offset_y = body_height // 2 - 8

        for x_sign, y_sign in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            wx = x_sign * wheel_offset_x if x_sign < 0 else wheel_offset_x - wheel_width
            wy = y_sign * wheel_offset_y if y_sign < 0 else wheel_offset_y - wheel_height
            wheel = QRect(wx, wy, wheel_width, wheel_height)
            painter.fillRect(wheel, QBrush(color))
            painter.drawRect(wheel)

    def draw_text(self, painter: QPainter):
        _draw_text_label(painter, self._text_doc, self.boundingRect(),
                         self.COLOR_TEXT, center_vertically=True)


def get_shape_class_for_level(level: int, formation: str = ""):
    if level == 6 and "Art" in formation:
        return ArtilleryItem
    elif "SupplyWagon" in formation:
        return WagonItem
    shape_map = {
        1: StarLevel1Item,
        2: StarLevel2Item,
        3: StarLevel3Item,
        4: StarLevel4Item,
        5: StarLevel5Item,
        6: RectangleItem,
    }
    return shape_map.get(level, RectangleItem)
