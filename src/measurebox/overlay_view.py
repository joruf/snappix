"""Transparent always-on-top overlay for drawing and editing rectangles."""

from __future__ import annotations

try:
    from pynput import mouse

    PYNPUT_AVAILABLE = True
except ImportError:
    # Not just ModuleNotFoundError: on a display-less session pynput picks a
    # backend at import time and raises a plain ImportError. Importing this
    # module must stay safe there so headless runs and CI can load MeasureBox.
    mouse = None
    PYNPUT_AVAILABLE = False

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from src.measurebox.geometry import normalize_rect
from src.measurebox.resizable_rect_item import ResizableRectItem


class OverlayView(QGraphicsView):
    """Transparent always-on-top overlay for drawing and editing rectangles."""

    rectangle_created = Signal()
    interaction_lock_changed = Signal(bool)

    def __init__(self, line_color: QColor, fill_color: QColor) -> None:
        """Build overlay scene and configure window flags.

        :param line_color: Initial border color.
        :param fill_color: Initial fill color.
        """
        self.scene = QGraphicsScene()
        super().__init__(self.scene)
        self._line_color = QColor(line_color)
        self._fill_color = QColor(fill_color)
        self._edit_mode_enabled = False
        self._drawing_active = False
        self._draw_start: QPointF | None = None
        self._preview_item: ResizableRectItem | None = None
        self._items: list[ResizableRectItem] = []
        self._max_rectangles = 1
        self._interaction_locked = True
        self._auto_interaction_enabled = False
        self._border_activation_tolerance = 10.0
        self._body_activation_padding = 4.0
        self._transparent_state_applied: bool | None = None
        self._ruler_enabled = False
        self._ruler_outside = False
        self._crosshair_enabled = True
        self._crosshair_scene_pos: QPointF | None = None
        self._mouse_controller = mouse.Controller() if PYNPUT_AVAILABLE else None
        self._forwarding_wheel = False
        self._wheel_angle_remainder_x = 0
        self._wheel_angle_remainder_y = 0
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(60)
        self._hover_timer.timeout.connect(self._sync_auto_interaction_mode)
        self._foreground_timer = QTimer(self)
        self._foreground_timer.setInterval(400)
        self._foreground_timer.timeout.connect(self._ensure_overlay_foreground)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")
        self._draw_window_flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self._passthrough_window_flags = (
            self._draw_window_flags
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(self._draw_window_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._apply_virtual_geometry()
        self.show()
        self.set_edit_mode(False)
        self._hover_timer.start()
        self._foreground_timer.start()

    def set_line_color(self, color: QColor) -> None:
        """Set border color for new and existing rectangles.

        :param color: New border color.
        :return: None.
        """
        self._line_color = QColor(color)
        for item in self._items:
            item.set_colors(self._line_color, self._fill_color)

    def set_fill_color(self, color: QColor) -> None:
        """Set fill color for new and existing rectangles.

        :param color: New fill color.
        :return: None.
        """
        self._fill_color = QColor(color)
        for item in self._items:
            item.set_colors(self._line_color, self._fill_color)

    def set_ruler_options(self, enabled: bool, outside: bool) -> None:
        """Set pixel ruler options for existing and new rectangles.

        :param enabled: True to render ruler.
        :param outside: True to draw ruler outside rectangle.
        :return: None.
        """
        self._ruler_enabled = enabled
        self._ruler_outside = outside
        for item in self._items:
            item.set_ruler_options(enabled, outside)

    def set_crosshair_enabled(self, enabled: bool) -> None:
        """Enable or disable Left-Shift crosshair rendering.

        :param enabled: True to show crosshair while Left-Shift is held.
        :return: None.
        """
        self._crosshair_enabled = enabled
        if not enabled:
            self.clear_crosshair()
            return
        self.viewport().update()

    def set_crosshair_at_global(self, x: int, y: int) -> None:
        """Update crosshair position from global screen coordinates.

        :param x: Global X coordinate at cursor hotspot.
        :param y: Global Y coordinate at cursor hotspot.
        :return: None.
        """
        if not self._crosshair_enabled:
            return
        local_pos = self.mapFromGlobal(QPointF(float(x), float(y)).toPoint())
        self._crosshair_scene_pos = self.mapToScene(local_pos)
        self.viewport().update()

    def clear_crosshair(self) -> None:
        """Hide the Left-Shift crosshair overlay.

        :return: None.
        """
        if self._crosshair_scene_pos is None:
            return
        self._crosshair_scene_pos = None
        self.viewport().update()

    def set_edit_mode(self, enabled: bool) -> None:
        """Enable or disable interactive editing mode.

        :param enabled: True to capture mouse interactions.
        :return: None.
        """
        self._edit_mode_enabled = enabled
        self._apply_mouse_transparency()
        if enabled:
            self.raise_()
            if self._interaction_locked:
                self.activateWindow()
                self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        else:
            self.clear_selection()

    def set_interaction_lock(self, locked: bool) -> None:
        """Set whether overlay should capture interactions in edit mode.

        :param locked: True to capture input, False for click/scroll-through.
        :return: None.
        """
        if self._interaction_locked == locked:
            return
        self._interaction_locked = locked
        for item in self._items:
            item.set_edit_overlay_visible(locked)
        self._apply_mouse_transparency()
        self.interaction_lock_changed.emit(locked)

    def has_active_rectangle(self) -> bool:
        """Check whether the overlay currently tracks an active rectangle.

        :return: True when at least one rectangle exists.
        """
        return bool(self._items)

    def is_global_point_on_active_item(self, x: int, y: int) -> bool:
        """Check whether a global point is on the active rectangle interaction area.

        :param x: Global X coordinate.
        :param y: Global Y coordinate.
        :return: True when the point can interact with the active rectangle.
        """
        if not self._items:
            return False
        active_item = self._items[-1]
        if active_item.scene() is None:
            return False
        local_pos = self.mapFromGlobal(QPointF(float(x), float(y)).toPoint())
        scene_pos = self.mapToScene(local_pos)
        return self._is_point_interacting_with_item(scene_pos, active_item)

    def try_activate_interaction_at_cursor(self) -> bool:
        """Enable edit interaction when the cursor hits the active rectangle.

        :return: True if interaction was activated.
        """
        cursor_pos = QCursor.pos()
        return self.try_activate_interaction_at_global(cursor_pos.x(), cursor_pos.y())

    def set_auto_interaction(self, enabled: bool) -> None:
        """Enable or disable automatic draw/pass-through switching.

        :param enabled: True to use automatic switching.
        :return: None.
        """
        self._auto_interaction_enabled = enabled

    def is_interaction_locked(self) -> bool:
        """Return whether overlay currently captures pointer input.

        :return: True when interaction is locked for editing.
        """
        return self._interaction_locked

    def is_cursor_in_active_item_area(self) -> bool:
        """Check whether the cursor is over the active rectangle interaction area.

        :return: True when cursor is over active rectangle interaction bounds.
        """
        if not self._items:
            return False
        active_item = self._items[-1]
        if active_item.scene() is None:
            return False
        cursor_pos_global = QCursor.pos()
        local_pos = self.mapFromGlobal(cursor_pos_global)
        scene_pos = self.mapToScene(local_pos)
        interaction_area = active_item.sceneBoundingRect().adjusted(
            -self._border_activation_tolerance,
            -self._border_activation_tolerance,
            self._border_activation_tolerance,
            self._border_activation_tolerance,
        )
        return interaction_area.contains(scene_pos)

    def try_activate_interaction_at_global(self, x: int, y: int) -> bool:
        """Enable edit interaction when a global point hits the active rectangle.

        :param x: Global X coordinate.
        :param y: Global Y coordinate.
        :return: True if interaction was activated.
        """
        if not self._items:
            return False
        active_item = self._items[-1]
        if active_item.scene() is None:
            self.scene.addItem(active_item)
        local_pos = self.mapFromGlobal(QPointF(float(x), float(y)).toPoint())
        scene_pos = self.mapToScene(local_pos)
        if not self._is_point_interacting_with_item(scene_pos, active_item):
            return False
        self.set_interaction_lock(True)
        self.clear_selection()
        active_item.setSelected(True)
        active_item.setFocus()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.reapply_interaction_state()
        self.raise_()
        return True

    def reapply_interaction_state(self) -> None:
        """Force a full re-application of current interaction flags.

        :return: None.
        """
        self._transparent_state_applied = None
        self._apply_mouse_transparency()

    def ensure_visible_foreground(self) -> None:
        """Ensure overlay and rectangle stay visible in the foreground.

        :return: None.
        """
        if not self._items:
            return
        self.show()
        self._ensure_scene_items_present()
        self.raise_()
        self.viewport().update()

    def clear_selection(self) -> None:
        """Unselect all rectangles.

        :return: None.
        """
        for item in self._items:
            item.setSelected(False)

    def select_active_rectangle_for_edit(self) -> bool:
        """Select and focus the active rectangle for immediate handle display.

        :return: True when an active rectangle exists and was selected.
        """
        if not self._items:
            return False
        active_item = self._items[-1]
        if active_item.scene() is None:
            self.scene.addItem(active_item)
        self.clear_selection()
        active_item.setSelected(True)
        active_item.setFocus()
        return True

    def clear_all(self) -> None:
        """Remove all rectangles from the overlay.

        :return: None.
        """
        for item in list(self._items):
            self.scene.removeItem(item)
        self._items.clear()
        self._preview_item = None

    def set_active_pick_result(self, color_hex: str, x: int, y: int) -> None:
        """Set sampled color and position text on active rectangle label.

        :param color_hex: Picked color in hex format.
        :param x: Picked global X position.
        :param y: Picked global Y position.
        :return: None.
        """
        if not self._items:
            return
        active_item = self._items[-1]
        active_item.set_picked_color_hex(color_hex)
        active_item.set_picked_position(x, y)

    def delete_selected(self) -> None:
        """Delete currently selected rectangles.

        :return: None.
        """
        for item in list(self._items):
            if item.isSelected():
                self.scene.removeItem(item)
                self._items.remove(item)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle local shortcuts in edit mode.

        :param event: Key event.
        :return: None.
        """
        if event.key() == Qt.Key.Key_Escape and self._drawing_active:
            self._cancel_drawing()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            self.delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Begin drawing rectangle in empty scene area.

        :param event: Mouse press event.
        :return: None.
        """
        if not self._edit_mode_enabled or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        target = self.itemAt(event.position().toPoint())
        active_item = self._items[-1] if self._items else None
        if target is None and active_item is not None:
            if self._is_point_interacting_with_item(scene_pos, active_item):
                target = active_item
                if not self._interaction_locked:
                    self.set_interaction_lock(True)
                self.clear_selection()
                active_item.setSelected(True)
                active_item.setFocus()

        if target is None:
            if self._items:
                # Existing rectangle: empty clicks never start a replacement draw.
                self.clear_selection()
                self.set_interaction_lock(False)
                event.accept()
                return

            if self._interaction_locked:
                self.clear_selection()
                self._drawing_active = True
                self._draw_start = scene_pos
                self._prepare_slot_for_new_rectangle()
                start_rect = QRectF(scene_pos, scene_pos)
                self._preview_item = ResizableRectItem(start_rect, self._line_color, self._fill_color)
                self._preview_item.set_edit_overlay_visible(self._interaction_locked)
                self._preview_item.set_ruler_options(self._ruler_enabled, self._ruler_outside)
                self.scene.addItem(self._preview_item)
                self._items.append(self._preview_item)
                self._preview_item.setSelected(True)
                event.accept()
                return

            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Update preview rectangle while drawing.

        :param event: Mouse move event.
        :return: None.
        """
        if self._drawing_active and self._draw_start is not None and self._preview_item is not None:
            current = self.mapToScene(event.position().toPoint())
            rect = normalize_rect(self._draw_start, current)
            self._preview_item.setPos(rect.topLeft())
            self._preview_item.setRect(0.0, 0.0, max(rect.width(), 1.0), max(rect.height(), 1.0))
            self._preview_item.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finalize rectangle drawing when mouse is released.

        :param event: Mouse release event.
        :return: None.
        """
        if self._drawing_active and event.button() == Qt.MouseButton.LeftButton:
            created_rectangle = False
            if self._preview_item is not None:
                rect = self._preview_item.rect()
                if rect.width() < 2.0 or rect.height() < 2.0:
                    self.scene.removeItem(self._preview_item)
                    self._items.remove(self._preview_item)
                else:
                    created_rectangle = True
            self._drawing_active = False
            self._draw_start = None
            self._preview_item = None
            if created_rectangle:
                self.clear_selection()
                self.rectangle_created.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        """Forward wheel scrolling so underlying apps keep scrolling.

        :param event: Wheel event.
        :return: None.
        """
        if not self._edit_mode_enabled or not self._interaction_locked:
            super().wheelEvent(event)
            return
        if self._forwarding_wheel:
            event.accept()
            return

        angle_x = event.angleDelta().x()
        angle_y = event.angleDelta().y()
        pixel_x = event.pixelDelta().x()
        pixel_y = event.pixelDelta().y()

        self._wheel_angle_remainder_x += angle_x
        self._wheel_angle_remainder_y += angle_y

        horizontal_steps = int(self._wheel_angle_remainder_x / 120)
        vertical_steps = int(self._wheel_angle_remainder_y / 120)

        self._wheel_angle_remainder_x -= horizontal_steps * 120
        self._wheel_angle_remainder_y -= vertical_steps * 120

        if horizontal_steps == 0 and angle_x == 0 and pixel_x != 0:
            horizontal_steps = 1 if pixel_x > 0 else -1
        if vertical_steps == 0 and angle_y == 0 and pixel_y != 0:
            vertical_steps = 1 if pixel_y > 0 else -1

        if vertical_steps == 0 and horizontal_steps == 0:
            event.accept()
            return

        if self._mouse_controller is None:
            # No pynput backend (display-less session): nothing to forward to.
            event.accept()
            return

        self._forwarding_wheel = True
        try:
            if vertical_steps != 0:
                self._mouse_controller.scroll(0, vertical_steps)
            if horizontal_steps != 0:
                self._mouse_controller.scroll(horizontal_steps, 0)
        finally:
            self._forwarding_wheel = False
        event.accept()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        """Draw transient Left-Shift crosshair at the cursor hotspot.

        :param painter: Scene foreground painter.
        :param rect: Scene update rectangle.
        :return: None.
        """
        super().drawForeground(painter, rect)
        if not self._crosshair_enabled or self._crosshair_scene_pos is None:
            return

        center = self._crosshair_scene_pos
        bounds = self.sceneRect()
        crosshair_color = QColor(self._line_color)
        crosshair_color.setAlpha(255)
        pen = QPen(crosshair_color, 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(
            QPointF(bounds.left(), center.y()),
            QPointF(bounds.right(), center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), bounds.top()),
            QPointF(center.x(), bounds.bottom()),
        )

    def _cancel_drawing(self) -> None:
        """Abort active drawing preview and remove temporary shape.

        :return: None.
        """
        if self._preview_item is not None and self._preview_item in self._items:
            self.scene.removeItem(self._preview_item)
            self._items.remove(self._preview_item)
        self._drawing_active = False
        self._draw_start = None
        self._preview_item = None

    def _prepare_slot_for_new_rectangle(self) -> None:
        """Enforce maximum rectangle count before creating a new one.

        :return: None.
        """
        while len(self._items) >= self._max_rectangles:
            oldest = self._items.pop(0)
            self.scene.removeItem(oldest)

    def _is_point_interacting_with_item(self, scene_pos: QPointF, item: ResizableRectItem) -> bool:
        """Check if a scene point should count as rectangle interaction.

        :param scene_pos: Point in scene coordinates.
        :param item: Active rectangle item.
        :return: True when point is on border/handles or inside item area.
        """
        if item.scene() is None:
            return False
        if item.is_point_on_border(scene_pos, self._border_activation_tolerance):
            return True
        local_point = item.mapFromScene(scene_pos)
        interaction_rect = item.rect().adjusted(
            -self._body_activation_padding,
            -self._body_activation_padding,
            self._body_activation_padding,
            self._body_activation_padding,
        )
        return interaction_rect.contains(local_point)

    def _apply_mouse_transparency(self) -> None:
        """Apply click-through behavior based on mode and interaction lock.

        :return: None.
        """
        transparent = not self._edit_mode_enabled or not self._interaction_locked
        if self._transparent_state_applied == transparent:
            return
        self._transparent_state_applied = transparent
        if transparent:
            window_flags = self._passthrough_window_flags | Qt.WindowType.WindowTransparentForInput
        else:
            window_flags = self._draw_window_flags
        if self.windowFlags() != window_flags:
            self.setWindowFlags(window_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, transparent)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, transparent)
        self.show()
        self._apply_virtual_geometry()
        self._ensure_scene_items_present()
        self.raise_()

    def _sync_auto_interaction_mode(self) -> None:
        """Auto-switch between draw and pass-through based on pointer position.

        :return: None.
        """
        if not self._auto_interaction_enabled or not self._edit_mode_enabled:
            return
        if self._drawing_active:
            if not self._interaction_locked:
                self.set_interaction_lock(True)
            return
        if not self._items:
            if not self._interaction_locked:
                self.set_interaction_lock(True)
            return
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return

        cursor_pos_global = QCursor.pos()
        local_pos = self.mapFromGlobal(cursor_pos_global)
        scene_pos = self.mapToScene(local_pos)
        active_item = self._items[-1]
        if active_item.scene() is None:
            self.scene.addItem(active_item)
        interaction_area = active_item.sceneBoundingRect().adjusted(
            -self._border_activation_tolerance,
            -self._border_activation_tolerance,
            self._border_activation_tolerance,
            self._border_activation_tolerance,
        )
        in_interaction_area = interaction_area.contains(scene_pos)

        left_pressed = bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)
        if in_interaction_area and not self._interaction_locked and left_pressed:
            self.set_interaction_lock(True)
            active_item.setSelected(True)
            active_item.setFocus()
            return
        if self._interaction_locked and in_interaction_area and not active_item.isSelected():
            active_item.setSelected(True)

    def _ensure_overlay_foreground(self) -> None:
        """Keep overlay visible above desktop when rectangles exist.

        :return: None.
        """
        if not self._edit_mode_enabled:
            return
        if not self._items:
            return
        self.raise_()

    def _ensure_scene_items_present(self) -> None:
        """Re-attach tracked rectangle items if compositor remaps the window.

        :return: None.
        """
        for item in self._items:
            if item.scene() is None:
                self.scene.addItem(item)

    def _apply_virtual_geometry(self) -> None:
        """Resize overlay to span all X11 screens.

        :return: None.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.virtualGeometry()
        self.setGeometry(geometry)
        self.scene.setSceneRect(QRectF(geometry))
