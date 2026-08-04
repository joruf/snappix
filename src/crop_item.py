"""
Resizable crop selection item.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

FRAME_MODE_RECT = "rect"
FRAME_MODE_ELLIPSE = "ellipse"
FRAME_MODE_LINE = "line"
FRAME_MODES = frozenset({FRAME_MODE_RECT, FRAME_MODE_ELLIPSE, FRAME_MODE_LINE})


# Modifiers that lock the aspect ratio while dragging a resize handle. Read live
# from each move event rather than latched at press, so holding the key down
# before grabbing the handle works -- which is how every other editor behaves,
# and the order users reach for first.
ASPECT_LOCK_MODIFIERS = (
    Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
)


def aspect_lock_requested(modifiers) -> bool:
    """
    Reports whether the pressed modifiers ask for a proportional resize.

    Args:
        modifiers: Keyboard modifiers carried by the event.

    Returns:
        bool: True when the aspect ratio should be preserved.
    """

    return bool(modifiers & ASPECT_LOCK_MODIFIERS)


class CropSelectionItem(QGraphicsRectItem):
    """
    Provides a draggable and resizable crop/selection overlay with handles.

    Frame modes:
    - ``rect``: dashed rectangle (default crop / rect annotations)
    - ``ellipse``: dashed ellipse inscribed in the AABB
    - ``line``: dashed line with endpoint handles
    """

    HANDLE_SIZE = 16.0
    MIN_SIZE = 12.0
    BORDER_HIT_TOLERANCE = 8.0
    LINE_HIT_TOLERANCE = 10.0
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
    LINE_HANDLE_NAMES = ("p1", "p2")

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
        self._aspect_ratio_lock_enabled = True
        self._resize_aspect_ratio = 1.0
        self._interior_interactive = True
        self._handle_size = self.HANDLE_SIZE
        self._handle_position = "inside"
        self._frame_mode = FRAME_MODE_RECT
        self._line_p1 = QPointF(0.0, 0.0)
        self._line_p2 = QPointF(max(rect.width(), 1.0), max(rect.height(), 1.0))
        self.on_geometry_changed: Callable[[], None] | None = None

        border_pen = QPen(QColor(52, 152, 219, 230), 2.0, Qt.PenStyle.DashLine)
        self.setPen(border_pen)
        self.setBrush(QColor(52, 152, 219, 48))

    def frame_mode(self) -> str:
        """
        Returns the active overlay frame mode.

        Returns:
            str: One of ``rect``, ``ellipse``, or ``line``.
        """

        return self._frame_mode

    def set_frame_mode(self, mode: str) -> None:
        """
        Sets whether the overlay paints as a rect, ellipse, or line.

        Args:
            mode: Frame mode identifier.

        Returns:
            None
        """

        resolved = str(mode).strip().lower()
        if resolved not in FRAME_MODES:
            resolved = FRAME_MODE_RECT
        if resolved == self._frame_mode:
            return
        self.prepareGeometryChange()
        self._frame_mode = resolved
        if resolved == FRAME_MODE_LINE:
            self.setBrush(Qt.BrushStyle.NoBrush)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        elif self._interior_interactive:
            self.setBrush(QColor(52, 152, 219, 48))
        else:
            self.setBrush(QColor(52, 152, 219, 24))
        self.update()

    def set_line_endpoints(self, p1: QPointF, p2: QPointF) -> None:
        """
        Sets line-mode endpoints in scene coordinates and syncs the AABB.

        Args:
            p1: First endpoint in scene coordinates.
            p2: Second endpoint in scene coordinates.

        Returns:
            None
        """

        self.prepareGeometryChange()
        self.setPos(0.0, 0.0)
        self._line_p1 = QPointF(p1)
        self._line_p2 = QPointF(p2)
        self._sync_rect_from_line_endpoints()
        self.update()

    def scene_line(self) -> QLineF:
        """
        Returns the current line-mode geometry in scene coordinates.

        Returns:
            QLineF: Scene-space line (meaningful in line mode).
        """

        return QLineF(self.mapToScene(self._line_p1), self.mapToScene(self._line_p2))

    def _sync_rect_from_line_endpoints(self) -> None:
        """
        Updates the local AABB so Qt bounds cover the line and handles.

        Returns:
            None
        """

        pad = max(self._handle_size, self.LINE_HIT_TOLERANCE)
        left = min(self._line_p1.x(), self._line_p2.x()) - pad
        top = min(self._line_p1.y(), self._line_p2.y()) - pad
        right = max(self._line_p1.x(), self._line_p2.x()) + pad
        bottom = max(self._line_p1.y(), self._line_p2.y()) + pad
        self.setRect(QRectF(left, top, max(2.0, right - left), max(2.0, bottom - top)))

    def boundingRect(self) -> QRectF:
        """
        Returns expanded bounds so handles remain interactive.

        Returns:
            QRectF: Expanded local bounds.
        """

        margin = self._handle_margin()
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def set_handle_style(self, *, size: float, position: str) -> None:
        """
        Configures resize-handle size and placement for selection overlays.

        Args:
            size: Handle edge length in pixels.
            position: One of ``center``, ``inside``, or ``outside``.

        Returns:
            None
        """

        from src.config import normalize_resize_handle_position, normalize_resize_handle_size

        self._handle_size = float(normalize_resize_handle_size(size))
        self._handle_position = normalize_resize_handle_position(position)
        self.prepareGeometryChange()
        if self._frame_mode == FRAME_MODE_LINE:
            self._sync_rect_from_line_endpoints()
        self.update()

    def _handle_margin(self) -> float:
        """
        Returns extra bounds needed so handles remain interactive.

        Returns:
            float: Margin in local coordinates.
        """

        if self._handle_position == "outside":
            return self._handle_size
        if self._handle_position == "center":
            return self._handle_size / 2.0
        return 0.0

    def _active_handle_names(self) -> tuple[str, ...]:
        """
        Returns handle identifiers for the current frame mode.

        Returns:
            tuple[str, ...]: Handle names.
        """

        if self._frame_mode == FRAME_MODE_LINE:
            return self.LINE_HANDLE_NAMES
        return self.HANDLE_NAMES

    def _handle_anchor(self, handle_name: str) -> tuple[float, float]:
        """
        Returns the border anchor point for one handle in local coordinates.

        Args:
            handle_name: Handle identifier.

        Returns:
            tuple[float, float]: Anchor x/y on the selection border.
        """

        if handle_name == "p1":
            return self._line_p1.x(), self._line_p1.y()
        if handle_name == "p2":
            return self._line_p2.x(), self._line_p2.y()

        rect = self.rect()
        x_mid = rect.left() + rect.width() / 2.0
        y_mid = rect.top() + rect.height() / 2.0
        anchors = {
            "top_left": (rect.left(), rect.top()),
            "top": (x_mid, rect.top()),
            "top_right": (rect.right(), rect.top()),
            "right": (rect.right(), y_mid),
            "bottom_right": (rect.right(), rect.bottom()),
            "bottom": (x_mid, rect.bottom()),
            "bottom_left": (rect.left(), rect.bottom()),
            "left": (rect.left(), y_mid),
        }
        return anchors[handle_name]

    def _handle_origin(self, handle_name: str) -> tuple[float, float]:
        """
        Computes the top-left corner for one handle rectangle.

        Args:
            handle_name: Handle identifier.

        Returns:
            tuple[float, float]: Handle rectangle origin in local coordinates.
        """

        if handle_name in self.LINE_HANDLE_NAMES:
            anchor_x, anchor_y = self._handle_anchor(handle_name)
            size = self._handle_size
            return anchor_x - size / 2.0, anchor_y - size / 2.0

        anchor_x, anchor_y = self._handle_anchor(handle_name)
        size = self._handle_size
        position = self._handle_position

        if handle_name == "top_left":
            if position == "inside":
                return anchor_x, anchor_y
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x - size, anchor_y - size

        if handle_name == "top":
            if position == "inside":
                return anchor_x - size / 2.0, anchor_y
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x - size / 2.0, anchor_y - size

        if handle_name == "top_right":
            if position == "inside":
                return anchor_x - size, anchor_y
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x, anchor_y - size

        if handle_name == "right":
            if position == "inside":
                return anchor_x - size, anchor_y - size / 2.0
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x, anchor_y - size / 2.0

        if handle_name == "bottom_right":
            if position == "inside":
                return anchor_x - size, anchor_y - size
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x, anchor_y

        if handle_name == "bottom":
            if position == "inside":
                return anchor_x - size / 2.0, anchor_y - size
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x - size / 2.0, anchor_y

        if handle_name == "bottom_left":
            if position == "inside":
                return anchor_x, anchor_y - size
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x - size, anchor_y

        if handle_name == "left":
            if position == "inside":
                return anchor_x, anchor_y - size / 2.0
            if position == "center":
                return anchor_x - size / 2.0, anchor_y - size / 2.0
            return anchor_x - size, anchor_y - size / 2.0

        return anchor_x, anchor_y

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

        painter.save()
        painter.setPen(self.pen())
        if self._frame_mode == FRAME_MODE_LINE:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(self._line_p1, self._line_p2)
        elif self._frame_mode == FRAME_MODE_ELLIPSE:
            painter.setBrush(self.brush())
            painter.drawEllipse(self.rect())
        else:
            painter.setBrush(self.brush())
            painter.drawRect(self.rect())
        painter.restore()

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

    def set_interior_interactive(self, enabled: bool) -> None:
        """
        Controls whether the filled interior captures mouse events.

        When disabled, only the border and handles are interactive so thin
        annotations (lines/arrows) remain clickable underneath the overlay.

        Args:
            enabled: True to include the filled rectangle in hit testing.

        Returns:
            None
        """

        self._interior_interactive = bool(enabled)
        if self._frame_mode == FRAME_MODE_LINE:
            self.setBrush(Qt.BrushStyle.NoBrush)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        elif self._interior_interactive:
            self.setBrush(QColor(52, 152, 219, 48))
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        else:
            self.setBrush(QColor(52, 152, 219, 24))
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.prepareGeometryChange()
        self.update()

    def shape(self) -> QPainterPath:
        """
        Returns the interactive hit region for the overlay.

        Returns:
            QPainterPath: Full rectangle, or only border/handles when interior
            clicks should pass through to annotations below.
        """

        path = QPainterPath()
        for handle in self._handle_rects().values():
            path.addRect(handle)

        if self._frame_mode == FRAME_MODE_LINE:
            # Endpoints only: keep the painted shaft non-interactive so the
            # underlying line/arrow remains selectable underneath the overlay.
            return path

        rect = self.rect()
        if self._frame_mode == FRAME_MODE_ELLIPSE:
            if self._interior_interactive:
                path.addEllipse(rect)
                return path
            outer = QPainterPath()
            outer.addEllipse(
                rect.adjusted(
                    -self.BORDER_HIT_TOLERANCE,
                    -self.BORDER_HIT_TOLERANCE,
                    self.BORDER_HIT_TOLERANCE,
                    self.BORDER_HIT_TOLERANCE,
                )
            )
            shrink = self.BORDER_HIT_TOLERANCE
            inner_rect = rect.adjusted(shrink, shrink, -shrink, -shrink)
            if inner_rect.width() > 2.0 and inner_rect.height() > 2.0:
                inner = QPainterPath()
                inner.addEllipse(inner_rect)
                # united() avoids OddEvenFill cancellation with handle rects.
                return path.united(outer.subtracted(inner))
            return path.united(outer)

        if self._interior_interactive:
            path.addRect(rect)
            return path

        tolerance = self.BORDER_HIT_TOLERANCE
        border = QPainterPath()
        border.addRect(rect.adjusted(-tolerance, -tolerance, tolerance, tolerance))
        inner = QPainterPath()
        inner.addRect(rect.adjusted(tolerance, tolerance, -tolerance, -tolerance))
        return path.united(border.subtracted(inner))

    def set_aspect_ratio_lock_enabled(self, enabled: bool) -> None:
        """
        Enables Shift-modified resize to preserve the current width/height ratio.

        Args:
            enabled: True for crop selections that should support ratio locking.

        Returns:
            None
        """

        self._aspect_ratio_lock_enabled = bool(enabled)

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

        self.unsetCursor()
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
            if handle_name is None and self._frame_mode != FRAME_MODE_LINE:
                handle_name = self._border_handle_at(event.pos())
            if handle_name is not None:
                self._active_handle = handle_name
                self._resizing = True
                scene_rect = self.scene_rect()
                if scene_rect.height() > 0.0:
                    self._resize_aspect_ratio = scene_rect.width() / scene_rect.height()
                else:
                    self._resize_aspect_ratio = 1.0
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
            if self._frame_mode == FRAME_MODE_LINE:
                self._resize_line_endpoint(self._active_handle, event.scenePos())
                event.accept()
                return
            lock_aspect_ratio = (
                self._aspect_ratio_lock_enabled
                and aspect_lock_requested(event.modifiers())
            )
            self._resize_from_handle(
                self._active_handle,
                event.scenePos(),
                lock_aspect_ratio=lock_aspect_ratio,
            )
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

        if self._frame_mode == FRAME_MODE_LINE:
            line = self.scene_line()
            return QRectF(line.p1(), line.p2()).normalized()

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

        if handle_name in self.LINE_HANDLE_NAMES:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            return
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
        self.setCursor(QCursor(cursor_map.get(handle_name, Qt.CursorShape.SizeAllCursor)))

    def _handle_rects(self) -> dict[str, QRectF]:
        """
        Computes all handle rectangles in local coordinates.

        Returns:
            dict[str, QRectF]: Mapping of handle id to rect.
        """

        handle_size = self._handle_size
        handle_rects: dict[str, QRectF] = {}
        for handle_name in self._active_handle_names():
            origin_x, origin_y = self._handle_origin(handle_name)
            handle_rects[handle_name] = QRectF(
                origin_x,
                origin_y,
                handle_size,
                handle_size,
            )
        return handle_rects

    def _handle_at(self, local_pos: QPointF) -> str | None:
        """
        Returns handle identifier under local mouse position.

        Args:
            local_pos: Local item coordinates.

        Returns:
            str | None: Handle key or None.
        """

        for handle_name in self._active_handle_names():
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

        if self._frame_mode == FRAME_MODE_LINE:
            return None

        rect = self.rect()
        tolerance = self.BORDER_HIT_TOLERANCE
        if rect.width() <= 0 or rect.height() <= 0:
            return None

        if self._frame_mode == FRAME_MODE_ELLIPSE:
            cx = rect.center().x()
            cy = rect.center().y()
            rx = max(rect.width() / 2.0, 0.001)
            ry = max(rect.height() / 2.0, 0.001)
            dx = (local_pos.x() - cx) / rx
            dy = (local_pos.y() - cy) / ry
            radius = math.hypot(dx, dy)
            if abs(radius - 1.0) > (tolerance / min(rx, ry)):
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

    def _resize_line_endpoint(self, handle_name: str, scene_pos: QPointF) -> None:
        """
        Moves one line endpoint while keeping the other fixed.

        Args:
            handle_name: ``p1`` or ``p2``.
            scene_pos: Cursor position in scene coordinates.

        Returns:
            None
        """

        local = self.mapFromScene(scene_pos)
        self.prepareGeometryChange()
        if handle_name == "p1":
            if (local - self._line_p2).manhattanLength() < self.MIN_SIZE:
                return
            self._line_p1 = QPointF(local)
        elif handle_name == "p2":
            if (local - self._line_p1).manhattanLength() < self.MIN_SIZE:
                return
            self._line_p2 = QPointF(local)
        else:
            return
        self._sync_rect_from_line_endpoints()
        self.update()
        self._notify_geometry_changed()

    def _resize_from_handle(
        self,
        handle_name: str,
        scene_pos: QPointF,
        *,
        lock_aspect_ratio: bool = False,
    ) -> None:
        """
        Resizes rectangle based on dragged handle.

        Args:
            handle_name: Active handle identifier.
            scene_pos: Current cursor position in scene coordinates.
            lock_aspect_ratio: True to preserve the ratio active at resize start.

        Returns:
            None
        """

        if lock_aspect_ratio:
            self._resize_from_handle_with_aspect_ratio(handle_name, scene_pos)
            return

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

    def _fit_aspect_size(self, width: float, height: float, aspect_ratio: float) -> tuple[float, float]:
        """
        Returns one width/height pair that matches the requested aspect ratio.

        Args:
            width: Proposed width.
            height: Proposed height.
            aspect_ratio: Width divided by height.

        Returns:
            tuple[float, float]: Adjusted width and height.
        """

        if width / max(height, 0.0001) >= aspect_ratio:
            height = width / aspect_ratio
        else:
            width = height * aspect_ratio
        width = max(width, self.MIN_SIZE)
        height = max(height, self.MIN_SIZE)
        if width / max(height, 0.0001) >= aspect_ratio:
            height = width / aspect_ratio
        else:
            width = height * aspect_ratio
        return width, height

    def _resize_from_handle_with_aspect_ratio(self, handle_name: str, scene_pos: QPointF) -> None:
        """
        Resizes the crop frame while preserving its starting aspect ratio.

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
        aspect_ratio = self._resize_aspect_ratio
        resized: QRectF

        if handle_name == "bottom_right":
            new_width, new_height = self._fit_aspect_size(
                max(self.MIN_SIZE, scene_pos.x() - left),
                max(self.MIN_SIZE, scene_pos.y() - top),
                aspect_ratio,
            )
            resized = QRectF(left, top, new_width, new_height)
        elif handle_name == "top_left":
            new_width, new_height = self._fit_aspect_size(
                max(self.MIN_SIZE, right - scene_pos.x()),
                max(self.MIN_SIZE, bottom - scene_pos.y()),
                aspect_ratio,
            )
            resized = QRectF(right - new_width, bottom - new_height, new_width, new_height)
        elif handle_name == "top_right":
            new_width, new_height = self._fit_aspect_size(
                max(self.MIN_SIZE, scene_pos.x() - left),
                max(self.MIN_SIZE, bottom - scene_pos.y()),
                aspect_ratio,
            )
            resized = QRectF(left, bottom - new_height, new_width, new_height)
        elif handle_name == "bottom_left":
            new_width, new_height = self._fit_aspect_size(
                max(self.MIN_SIZE, right - scene_pos.x()),
                max(self.MIN_SIZE, scene_pos.y() - top),
                aspect_ratio,
            )
            resized = QRectF(right - new_width, top, new_width, new_height)
        elif handle_name == "right":
            new_width = max(self.MIN_SIZE, scene_pos.x() - left)
            new_height = max(new_width / aspect_ratio, self.MIN_SIZE)
            new_width = new_height * aspect_ratio
            resized = QRectF(left, top, new_width, new_height)
        elif handle_name == "left":
            new_width = max(self.MIN_SIZE, right - scene_pos.x())
            new_height = max(new_width / aspect_ratio, self.MIN_SIZE)
            new_width = new_height * aspect_ratio
            resized = QRectF(right - new_width, top, new_width, new_height)
        elif handle_name == "bottom":
            new_height = max(self.MIN_SIZE, scene_pos.y() - top)
            new_width = max(new_height * aspect_ratio, self.MIN_SIZE)
            new_height = new_width / aspect_ratio
            resized = QRectF(left, top, new_width, new_height)
        elif handle_name == "top":
            new_height = max(self.MIN_SIZE, bottom - scene_pos.y())
            new_width = max(new_height * aspect_ratio, self.MIN_SIZE)
            new_height = new_width / aspect_ratio
            resized = QRectF(left, bottom - new_height, new_width, new_height)
        else:
            return

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
