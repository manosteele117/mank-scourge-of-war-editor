"""Shared base class for the two zoomable QGraphicsView subclasses.

Both the visual-hierarchy view and the minimap view implement the same wheel
zoom + middle-click pan + reset_view pattern with identical tunables. They
differ only in mouse-button handling for selection, so the common parts are
factored out here.
"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QWheelEvent


class ZoomableGraphicsView:
    """Mixin providing zoom, middle-click pan, and reset_view.

    Concrete subclasses should inherit this *after* QGraphicsView (or another
    QGraphicsView subclass) and call super().__init__(...) normally.
    """

    MIN_ZOOM: float = 0.1
    MAX_ZOOM: float = 50.0
    ZOOM_FACTOR: float = 1.2

    def init_zoom_state(self) -> None:
        self.zoom_level: float = 1.0
        self._is_panning: bool = False
        self._pan_start_pos = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        angle = event.angleDelta().y()
        if angle == 0:
            return
        factor = self.ZOOM_FACTOR if angle > 0 else 1 / self.ZOOM_FACTOR

        new_zoom = self.zoom_level * factor
        if new_zoom < self.MIN_ZOOM or new_zoom > self.MAX_ZOOM:
            return

        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self.zoom_level = new_zoom
        event.accept()

    def reset_view(self, rect: QRectF) -> None:
        if rect is None or rect.isNull() or not rect.isValid():
            return
        self.resetTransform()
        self.zoom_level = 1.0
        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _handle_middle_press(self, event) -> bool:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return True
        return False

    def _handle_middle_release(self, event) -> bool:
        if event.button() == Qt.MouseButton.MiddleButton and self._is_panning:
            self._is_panning = False
            self._pan_start_pos = None
            self.unsetCursor()
            event.accept()
            return True
        return False

    def _handle_pan_move(self, event) -> bool:
        if self._is_panning and self._pan_start_pos is not None:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return True
        return False
