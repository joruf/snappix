"""
Floating always-on-top window that keeps one image visible while working.

Pinning answers a workflow the editor cannot: keeping a reference (a spec, an
error message, a design) on screen while typing in another application. The
window is frameless and stays above everything, so it behaves like a sticky note
made of pixels rather than like a second editor.

Interaction is deliberately small:

- drag anywhere to move it
- mouse wheel to zoom, double-click to reset to 100 %
- ``Esc`` or middle-click to close, ``Ctrl+C`` to copy the image again
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

# Zoom bounds and step for the wheel. Beyond these the window either vanishes or
# covers the screen it is supposed to sit next to.
MIN_PIN_ZOOM = 0.1
MAX_PIN_ZOOM = 8.0
PIN_ZOOM_STEP = 1.1

# Border drawn around the image so a light screenshot stays distinguishable from
# the desktop behind it.
PIN_BORDER_WIDTH = 1


class PinWindow(QWidget):
    """
    Shows one pixmap in a frameless, always-on-top window.
    """

    closed = Signal()

    def __init__(self, pixmap: QPixmap, screen_position: QPoint | None = None) -> None:
        """
        Initializes a pinned image window.

        Args:
            pixmap: Image to show.
            screen_position: Optional top-left position in global coordinates.
        """

        super().__init__()
        self._pixmap = pixmap
        self._zoom = 1.0
        self._drag_offset = QPoint()
        self._dragging = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setWindowTitle("Snappix Pin")
        self._apply_zoom()
        if screen_position is not None:
            self.move(screen_position)
        else:
            self._center_on_cursor_screen()

    def pixmap(self) -> QPixmap:
        """
        Returns the pinned image.

        Returns:
            QPixmap: Image shown in this window.
        """

        return self._pixmap

    def zoom(self) -> float:
        """
        Returns the active zoom factor.

        Returns:
            float: Zoom factor where 1.0 is the original size.
        """

        return self._zoom

    def set_zoom(self, zoom: float) -> None:
        """
        Sets the zoom factor within the supported range.

        Args:
            zoom: Requested factor.

        Returns:
            None
        """

        self._zoom = max(MIN_PIN_ZOOM, min(MAX_PIN_ZOOM, float(zoom)))
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        """
        Resizes the window to the zoomed image size.

        Returns:
            None
        """

        width = max(1, int(round(self._pixmap.width() * self._zoom)))
        height = max(1, int(round(self._pixmap.height() * self._zoom)))
        self.resize(width, height)
        self.update()

    def _center_on_cursor_screen(self) -> None:
        """
        Places the window on the screen holding the mouse pointer.

        Returns:
            None
        """

        from PySide6.QtGui import QCursor

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available: QRect = screen.availableGeometry()
        self.move(
            available.center().x() - (self.width() // 2),
            available.center().y() - (self.height() // 2),
        )

    def paintEvent(self, _event) -> None:
        """
        Paints the image and a thin border.

        Args:
            _event: Unused paint event.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.setPen(QPen(QColor(20, 20, 20, 160), PIN_BORDER_WIDTH))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event) -> None:
        """
        Starts dragging, or closes on a middle click.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() == Qt.MouseButton.MiddleButton:
            self.close()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        """
        Moves the window while dragging.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        """
        Ends dragging.

        Args:
            event: Mouse release event.

        Returns:
            None
        """

        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, _event) -> None:
        """
        Resets the zoom to the original size.

        Args:
            _event: Unused mouse event.

        Returns:
            None
        """

        self.set_zoom(1.0)

    def wheelEvent(self, event) -> None:
        """
        Zooms the pinned image.

        Args:
            event: Wheel event.

        Returns:
            None
        """

        delta = event.angleDelta().y()
        if delta == 0:
            return
        self.set_zoom(self._zoom * (PIN_ZOOM_STEP if delta > 0 else 1.0 / PIN_ZOOM_STEP))
        event.accept()

    def keyPressEvent(self, event) -> None:
        """
        Closes on Escape and copies the image on Ctrl+C.

        Args:
            event: Key event.

        Returns:
            None
        """

        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            QGuiApplication.clipboard().setPixmap(self._pixmap)
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """
        Notifies listeners that the pin was closed.

        Args:
            event: Close event.

        Returns:
            None
        """

        self.closed.emit()
        super().closeEvent(event)
