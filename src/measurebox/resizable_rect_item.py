"""Resizable rectangle graphics item for the overlay scene."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from src.measurebox.geometry import compute_resized_scene_rect, normalize_rect


class ResizableRectItem(QGraphicsRectItem):
    """Draggable and resizable rectangle with 8 resize handles."""

    HANDLE_SIZE = 8.0
    MIN_SIZE = 6.0
    HANDLE_ORDER = (
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
        "top",
        "bottom",
        "left",
        "right",
    )

    def __init__(self, scene_rect: QRectF, line_color: QColor, fill_color: QColor) -> None:
        """Create a new rectangle item.

        :param scene_rect: Initial geometry in scene coordinates.
        :param line_color: Border color.
        :param fill_color: Fill color.
        """
        super().__init__(QRectF(0.0, 0.0, scene_rect.width(), scene_rect.height()))
        self.setPos(scene_rect.topLeft())
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)
        self._line_color = QColor(line_color)
        self._fill_color = QColor(fill_color)
        self._active_handle: str | None = None
        self._is_resizing = False
        self._show_edit_overlay = False
        self._picked_color_hex = "-"
        self._picked_position_text = "-"
        self._label_text = ""
        self._ruler_enabled = False
        self._ruler_outside = False
        self._label_font = QFont()
        self._label_font.setPointSize(9)
        self._apply_style()
        self._update_measure_label()

    def set_colors(self, line_color: QColor, fill_color: QColor) -> None:
        """Update line and fill colors for this rectangle.

        :param line_color: New border color.
        :param fill_color: New fill color.
        :return: None.
        """
        self._line_color = QColor(line_color)
        self._fill_color = QColor(fill_color)
        self._apply_style()
        self.update()

    def set_picked_color_hex(self, color_hex: str) -> None:
        """Set sampled color text shown in the measure label.

        :param color_hex: Picked color in hex format.
        :return: None.
        """
        self._picked_color_hex = color_hex
        self._update_measure_label()

    def set_picked_position(self, x: int, y: int) -> None:
        """Set sampled mouse position text shown in the measure label.

        :param x: Picked global X position.
        :param y: Picked global Y position.
        :return: None.
        """
        self._picked_position_text = f"{x},{y}"
        self._update_measure_label()

    def boundingRect(self) -> QRectF:
        """Return item bounds including handle area.

        :return: Expanded bounding rectangle.
        """
        margin = self.HANDLE_SIZE
        if self._ruler_enabled and self._ruler_outside:
            margin = max(margin, 20.0)
        top_margin = margin
        if self._ruler_enabled and not self._ruler_outside:
            top_margin = max(top_margin, 26.0)
        return self.rect().adjusted(-margin, -top_margin, margin, margin)

    def shape(self) -> QPainterPath:
        """Return hit-test shape including handle area when selected.

        :return: Item shape path used for mouse interaction.
        """
        path = QPainterPath()
        if self.isSelected() and self._show_edit_overlay:
            path.addRect(self.boundingRect())
        else:
            path.addRect(self.rect())
        return path

    def set_edit_overlay_visible(self, visible: bool) -> None:
        """Set whether move/resize overlay visuals should be rendered.

        :param visible: True to show handles and extended hit area.
        :return: None.
        """
        self.prepareGeometryChange()
        self._show_edit_overlay = visible
        self.update()

    def set_ruler_options(self, enabled: bool, outside: bool) -> None:
        """Set ruler rendering options for this rectangle.

        :param enabled: True to render pixel ruler.
        :param outside: True to draw ruler outside rectangle border.
        :return: None.
        """
        self.prepareGeometryChange()
        self._ruler_enabled = enabled
        self._ruler_outside = outside
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        """Paint rectangle and resize handles when selected.

        :param painter: Active painter.
        :param option: Style option.
        :param widget: Optional paint widget.
        :return: None.
        """
        painter.save()
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRect(self.rect())
        painter.restore()
        self._draw_ruler(painter)
        self._draw_label(painter)
        if not self.isSelected() or not self._show_edit_overlay:
            return
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
        painter.setBrush(QColor(30, 30, 30, 220))
        for handle_rect in self._handle_rects().values():
            painter.drawRect(handle_rect)
        painter.restore()

    def hoverMoveEvent(self, event) -> None:  # type: ignore[override]
        """Set cursor shape according to active handle.

        :param event: Hover event.
        :return: None.
        """
        handle = self._handle_at(event.pos())
        self._set_cursor_for_handle(handle)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        """Restore cursor when leaving item bounds.

        :param event: Hover leave event.
        :return: None.
        """
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Start resizing if a handle is pressed.

        :param event: Mouse press event.
        :return: None.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._handle_at(event.pos())
            if handle is not None:
                self._active_handle = handle
                self._is_resizing = True
                self.grabMouse()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        """Resize item while dragging a handle.

        :param event: Mouse move event.
        :return: None.
        """
        if self._is_resizing and self._active_handle is not None:
            self._resize_from_handle(self._active_handle, event.scenePos())
            self._update_measure_label()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        """Finish resize operation and refresh label.

        :param event: Mouse release event.
        :return: None.
        """
        if self._is_resizing:
            self._is_resizing = False
            self._active_handle = None
            if self.scene() is not None and self.scene().mouseGrabberItem() is self:
                self.ungrabMouse()
            self._update_measure_label()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._update_measure_label()

    def itemChange(self, change, value):  # type: ignore[override]
        """Update measure label after item movement.

        :param change: Change type.
        :param value: Proposed value.
        :return: Result passed to Qt.
        """
        result = super().itemChange(change, value)
        if change in {
            QGraphicsItem.GraphicsItemChange.ItemSelectedChange,
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged,
        }:
            self.prepareGeometryChange()
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._update_measure_label()
        return result

    def _apply_style(self) -> None:
        """Apply pen and brush styles.

        :return: None.
        """
        self.setPen(QPen(self._line_color, 2))
        self.setBrush(self._fill_color)

    def _scene_rect(self) -> QRectF:
        """Return current geometry in scene coordinates.

        :return: Scene rectangle.
        """
        local = self.rect()
        top_left = self.mapToScene(local.topLeft())
        bottom_right = self.mapToScene(local.bottomRight())
        return normalize_rect(top_left, bottom_right)

    def _update_measure_label(self) -> None:
        """Refresh dimensions label text and position.

        :return: None.
        """
        scene_rect = self._scene_rect()
        self._label_text = (
            f"x:{int(scene_rect.x())} y:{int(scene_rect.y())}  "
            f"w:{int(scene_rect.width())} h:{int(scene_rect.height())}  "
            f"color:{self._picked_color_hex}  mouse:{self._picked_position_text}px"
        )
        self.update()

    def _draw_label(self, painter: QPainter) -> None:
        """Draw label text in plain black.

        :param painter: Active painter.
        :return: None.
        """
        if not self._label_text:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        path = QPainterPath()
        baseline_y = 16.0
        if self._ruler_enabled and not self._ruler_outside:
            baseline_y = -6.0
        baseline = QPointF(6.0, baseline_y)
        path.addText(baseline, self._label_font, self._label_text)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 235))
        painter.drawPath(path)
        painter.restore()

    def _draw_ruler(self, painter: QPainter) -> None:
        """Draw optional pixel ruler on top and left edges.

        :param painter: Active painter.
        :return: None.
        """
        if not self._ruler_enabled:
            return
        rect = self.rect()
        if rect.width() < 10 or rect.height() < 10:
            return

        step = 10
        major_step = 50
        major_size = 10
        minor_size = 5
        text_offset = 2
        label_is_outside_top = self._ruler_enabled and not self._ruler_outside

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(QPen(QColor(0, 0, 0, 220), 1))
        font = QFont(self._label_font)
        font.setPointSize(8)
        painter.setFont(font)

        base_y = 0.0
        base_x = 0.0

        for x in range(0, int(rect.width()) + 1, step):
            tick_size = major_size if x % major_step == 0 else minor_size
            if self._ruler_outside:
                painter.drawLine(QPointF(float(x), base_y), QPointF(float(x), base_y - tick_size))
            else:
                painter.drawLine(QPointF(float(x), base_y), QPointF(float(x), base_y + tick_size))
            if x % major_step == 0:
                if label_is_outside_top and x == 0:
                    continue
                if self._ruler_outside:
                    painter.drawText(QPointF(float(x) + text_offset, base_y - major_size - 2), f"{x}px")
                else:
                    painter.drawText(QPointF(float(x) + text_offset, base_y + major_size + 10), f"{x}px")

        for y in range(0, int(rect.height()) + 1, step):
            tick_size = major_size if y % major_step == 0 else minor_size
            if self._ruler_outside:
                painter.drawLine(QPointF(base_x, float(y)), QPointF(base_x - tick_size, float(y)))
            else:
                painter.drawLine(QPointF(base_x, float(y)), QPointF(base_x + tick_size, float(y)))
            if y % major_step == 0:
                if label_is_outside_top and y == 0:
                    continue
                if self._ruler_outside:
                    painter.drawText(QPointF(base_x - major_size - 28, float(y) - text_offset), f"{y}px")
                else:
                    painter.drawText(QPointF(base_x + major_size + 2, float(y) - text_offset), f"{y}px")

        painter.restore()

    def _set_cursor_for_handle(self, handle: str | None) -> None:
        """Set resize/move cursor based on handle identifier.

        :param handle: Handle key.
        :return: None.
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
        cursor_shape = cursor_map.get(handle, Qt.CursorShape.SizeAllCursor)
        # Item-level cursor, never QApplication.setOverrideCursor(): the
        # override cursor is a stack, and this runs on every hover move. Each
        # move pushed another entry while leaving popped only one, so after a
        # drag the last resize cursor stayed on screen for good.
        self.setCursor(QCursor(cursor_shape))

    def _handle_rects(self) -> dict[str, QRectF]:
        """Compute all resize handle rectangles.

        :return: Mapping of handle name to local rect.
        """
        rect = self.rect()
        s = self.HANDLE_SIZE
        x_mid = rect.width() / 2.0
        y_mid = rect.height() / 2.0
        return {
            "top_left": QRectF(0 - s / 2.0, 0 - s / 2.0, s, s),
            "top": QRectF(x_mid - s / 2.0, 0 - s / 2.0, s, s),
            "top_right": QRectF(rect.width() - s / 2.0, 0 - s / 2.0, s, s),
            "right": QRectF(rect.width() - s / 2.0, y_mid - s / 2.0, s, s),
            "bottom_right": QRectF(rect.width() - s / 2.0, rect.height() - s / 2.0, s, s),
            "bottom": QRectF(x_mid - s / 2.0, rect.height() - s / 2.0, s, s),
            "bottom_left": QRectF(0 - s / 2.0, rect.height() - s / 2.0, s, s),
            "left": QRectF(0 - s / 2.0, y_mid - s / 2.0, s, s),
        }

    def _handle_at(self, local_pos: QPointF) -> str | None:
        """Find handle under local mouse position.

        :param local_pos: Mouse position in item coordinates.
        :return: Handle identifier or None.
        """
        handle_rects = self._handle_rects()
        for name in self.HANDLE_ORDER:
            handle_rect = handle_rects.get(name)
            if handle_rect is not None and handle_rect.contains(local_pos):
                return name
        return None

    def is_point_on_border(self, scene_pos: QPointF, tolerance: float = 6.0) -> bool:
        """Check whether a scene point is on the visible rectangle border area.

        :param scene_pos: Point in scene coordinates.
        :param tolerance: Border hit tolerance in pixels.
        :return: True if the point is on border/handle area.
        """
        local_pos = self.mapFromScene(scene_pos)
        if self._handle_at(local_pos) is not None:
            return True

        rect = self.rect()
        outer = rect.adjusted(-tolerance, -tolerance, tolerance, tolerance)
        inner = rect.adjusted(tolerance, tolerance, -tolerance, -tolerance)
        if not outer.contains(local_pos):
            return False
        if inner.width() <= 0 or inner.height() <= 0:
            return True
        return not inner.contains(local_pos)

    def _resize_from_handle(self, handle: str, scene_pos: QPointF) -> None:
        """Resize item from a specific handle using scene coordinates.

        :param handle: Handle identifier.
        :param scene_pos: Current mouse scene position.
        :return: None.
        """
        current = self._scene_rect()
        new_rect = compute_resized_scene_rect(
            current.left(),
            current.top(),
            current.right(),
            current.bottom(),
            handle,
            scene_pos.x(),
            scene_pos.y(),
            self.MIN_SIZE,
        )
        self.setPos(new_rect.topLeft())
        self.setRect(QRectF(0.0, 0.0, new_rect.width(), new_rect.height()))
        self.update()
