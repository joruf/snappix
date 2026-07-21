"""
Resizable crop selection item.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsRectItem


class CropSelectionItem(QGraphicsRectItem):
    """
    Provides a draggable and resizable crop rectangle with handles.
    """

    HANDLE_SIZE = 16.0
    MIN_SIZE = 12.0
    BORDER_HIT_TOLERANCE = 8.0
    HANDLE_NAMES = (
        "top_left",
        "top",
        "top_right",
        "right",
        "bottom_right",
        "bottom",
        "bottom_left",
        "left",
    )

    def __init__(self, rect: QRectF) -> None:
        """
        Initializes a crop item in scene coordinates.

        Args:
            rect: Initial crop geometry.
        """

        super().__init__(QRectF(0.0, 0.0, rect.width(), rect.height()))
        self.setPos(rect.topLeft())
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)
        self._active_handle: str | None = None
        self._resizing = False
        self._always_show_handles = False
        self.on_geometry_changed: Callable[[], None] | None = None

        border_pen = QPen(QColor(52, 152, 219, 230), 2.0, Qt.PenStyle.DashLine)
        self.setPen(border_pen)
        self.setBrush(QColor(52, 152, 219, 48))

    def boundingRect(self) -> QRectF:
        """
        Returns expanded bounds so handles remain interactive.

        Returns:
            QRectF: Expanded local bounds.
        """

        margin = self.HANDLE_SIZE
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """
        Paints crop frame and resize handles.

        Args:
            painter: Active painter instance.
            option: Paint option from Qt.
            widget: Optional target widget.

        Returns:
            None
        """

        super().paint(painter, option, widget)
        if not self.isSelected() and not self._always_show_handles:
            return
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
        painter.setBrush(QColor(20, 20, 20, 220))
        for handle in self._handle_rects().values():
            painter.drawRect(handle)
        painter.restore()

    def set_always_show_handles(self, enabled: bool) -> None:
        """
        Controls whether resize handles stay visible without selection.

        Args:
            enabled: True to always show handles.

        Returns:
            None
        """

        self._always_show_handles = enabled
        self.update()

    def hoverMoveEvent(self, event) -> None:
        """
        Updates cursor style when hovering handles.

        Args:
            event: Hover event.

        Returns:
            None
        """

        handle_name = self._handle_at(event.pos())
        self._set_cursor_for_handle(handle_name)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        """
        Restores cursor on leave.

        Args:
            event: Hover leave event.

        Returns:
            None
        """

        QApplication.restoreOverrideCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        """
        Starts resizing if a handle was pressed.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() == Qt.MouseButton.LeftButton:
            handle_name = self._handle_at(event.pos())
            if handle_name is None:
                handle_name = self._border_handle_at(event.pos())
            if handle_name is not None:
                self._active_handle = handle_name
                self._resizing = True
                self.grabMouse()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """
        Resizes item while dragging a handle.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        if self._resizing and self._active_handle is not None:
            self._resize_from_handle(self._active_handle, event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """
        Finishes active resize operation.

        Args:
            event: Mouse release event.

        Returns:
            None
        """

        if self._resizing:
            self._resizing = False
            self._active_handle = None
            if self.scene() is not None and self.scene().mouseGrabberItem() is self:
                self.ungrabMouse()
            self._notify_geometry_changed()
            event.accept()
            return
        self._notify_geometry_changed()
        super().mouseReleaseEvent(event)

    def scene_rect(self) -> QRectF:
        """
        Returns current geometry in scene coordinates.

        Returns:
            QRectF: Item scene rectangle.
        """

        local = self.rect()
        return QRectF(
            self.pos().x() + local.x(),
            self.pos().y() + local.y(),
            local.width(),
            local.height(),
        )

    def _set_cursor_for_handle(self, handle_name: str | None) -> None:
        """
        Applies a cursor shape for current resize handle.

        Args:
            handle_name: Handle key or None.

        Returns:
            None
        """

        cursor_map = {
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
        }
        QApplication.setOverrideCursor(QCursor(cursor_map.get(handle_name, Qt.CursorShape.SizeAllCursor)))

    def _handle_rects(self) -> dict[str, QRectF]:
        """
        Computes all handle rectangles in local coordinates.

        Returns:
            dict[str, QRectF]: Mapping of handle id to rect.
        """

        rect = self.rect()
        handle_size = self.HANDLE_SIZE
        x_mid = rect.width() / 2.0
        y_mid = rect.height() / 2.0
        return {
            "top_left": QRectF(0.0, 0.0, handle_size, handle_size),
            "top": QRectF(x_mid - handle_size / 2.0, 0.0, handle_size, handle_size),
            "top_right": QRectF(rect.width() - handle_size, 0.0, handle_size, handle_size),
            "right": QRectF(rect.width() - handle_size, y_mid - handle_size / 2.0, handle_size, handle_size),
            "bottom_right": QRectF(rect.width() - handle_size, rect.height() - handle_size, handle_size, handle_size),
            "bottom": QRectF(x_mid - handle_size / 2.0, rect.height() - handle_size, handle_size, handle_size),
            "bottom_left": QRectF(0.0, rect.height() - handle_size, handle_size, handle_size),
            "left": QRectF(0.0, y_mid - handle_size / 2.0, handle_size, handle_size),
        }

    def _handle_at(self, local_pos: QPointF) -> str | None:
        """
        Returns handle identifier under local mouse position.

        Args:
            local_pos: Local item coordinates.

        Returns:
            str | None: Handle key or None.
        """

        for handle_name in self.HANDLE_NAMES:
            rect = self._handle_rects()[handle_name]
            if rect.contains(local_pos):
                return handle_name
        return None

    def _border_handle_at(self, local_pos: QPointF) -> str | None:
        """
        Infers resize handle from border-near positions.

        Args:
            local_pos: Local item coordinates.

        Returns:
            str | None: Inferred handle key or None.
        """

        rect = self.rect()
        tolerance = self.BORDER_HIT_TOLERANCE
        if rect.width() <= 0 or rect.height() <= 0:
            return None

        near_left = abs(local_pos.x() - rect.left()) <= tolerance
        near_right = abs(local_pos.x() - rect.right()) <= tolerance
        near_top = abs(local_pos.y() - rect.top()) <= tolerance
        near_bottom = abs(local_pos.y() - rect.bottom()) <= tolerance

        if near_top and near_left:
            return "top_left"
        if near_top and near_right:
            return "top_right"
        if near_bottom and near_left:
            return "bottom_left"
        if near_bottom and near_right:
            return "bottom_right"
        if near_top:
            return "top"
        if near_bottom:
            return "bottom"
        if near_left:
            return "left"
        if near_right:
            return "right"
        return None

    def _resize_from_handle(self, handle_name: str, scene_pos: QPointF) -> None:
        """
        Resizes rectangle based on dragged handle.

        Args:
            handle_name: Active handle identifier.
            scene_pos: Current cursor position in scene coordinates.

        Returns:
            None
        """

        rect = self.scene_rect()
        left = rect.left()
        top = rect.top()
        right = rect.right()
        bottom = rect.bottom()

        if "left" in handle_name:
            left = min(scene_pos.x(), right - self.MIN_SIZE)
        if "right" in handle_name:
            right = max(scene_pos.x(), left + self.MIN_SIZE)
        if "top" in handle_name:
            top = min(scene_pos.y(), bottom - self.MIN_SIZE)
        if "bottom" in handle_name:
            bottom = max(scene_pos.y(), top + self.MIN_SIZE)

        resized = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        self.setPos(resized.topLeft())
        self.setRect(QRectF(0.0, 0.0, resized.width(), resized.height()))
        self.update()
        self._notify_geometry_changed()

    def itemChange(self, change, value):  # type: ignore[override]
        """
        Notifies geometry updates after item movement.

        Args:
            change: Item change enum.
            value: Proposed value.

        Returns:
            object: Value passed through to Qt.
        """

        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._notify_geometry_changed()
        return result

    def _notify_geometry_changed(self) -> None:
        """
        Triggers optional geometry-changed callback.

        Returns:
            None
        """

        if self.on_geometry_changed is not None:
            self.on_geometry_changed()
