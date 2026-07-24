"""
Timeline widget: scrub bar and draggable/resizable annotation bars for the
Snappix video editor.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from src.annotation_items import list_to_color
from src.video_models import VideoAnnotationModel

LABEL_WIDTH = 160
RULER_HEIGHT = 28
ROW_HEIGHT = 30
ROW_SPACING = 4
EDGE_HIT_PX = 6
MIN_ANNOTATION_DURATION_MS = 100
MIN_VIEW_DURATION_MS = 500
DEFAULT_VISIBLE_PAGES = 5
ZOOM_WHEEL_FACTOR = 1.15
CTRL_NAV_THRESHOLD_PX = 48

DRAG_MODE_PLAYHEAD = "playhead"
DRAG_MODE_MOVE = "move"
DRAG_MODE_START = "start"
DRAG_MODE_END = "end"


class TimelineWidget(QWidget):
    """
    Displays a scrub ruler and one row per video annotation, each shown as a
    draggable/resizable time-range bar.
    """

    seek_requested = Signal(int)
    annotation_time_changed = Signal(str, int, int)
    annotation_selected = Signal(str)

    def __init__(self) -> None:
        """
        Initializes the timeline with an empty annotation list.
        """

        super().__init__()
        self.setMinimumHeight(RULER_HEIGHT + ROW_HEIGHT + ROW_SPACING)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMouseTracking(True)
        self._duration_ms = 0
        self._position_ms = 0
        self._annotations: list[VideoAnnotationModel] = []
        self._selected_id = ""
        self._drag_mode = ""
        self._drag_annotation: VideoAnnotationModel | None = None
        self._drag_anchor_ms = 0
        self._drag_orig_start = 0
        self._drag_orig_end = 0
        self._view_start_ms = 0
        self._view_duration_ms = 1
        self._ctrl_nav_anchor_x: int | None = None

    def set_duration(self, duration_ms: int) -> None:
        """
        Sets the total timeline duration.

        Args:
            duration_ms: Video duration in milliseconds.

        Returns:
            None
        """

        self._duration_ms = max(1, duration_ms)
        self.reset_view()
        self._resize_for_row_count()
        self.update()

    def duration_ms(self) -> int:
        """
        Returns the total timeline duration.

        Returns:
            int: Duration in milliseconds.
        """

        return self._duration_ms

    def reset_view(self) -> None:
        """
        Resets pan/zoom so the first page of the timeline is visible.

        Returns:
            None
        """

        self._view_start_ms = 0
        self._view_duration_ms = self._default_page_duration_ms()
        self._clamp_view()

    def can_pan_left(self) -> bool:
        """
        Returns whether the visible range can shift earlier in time.

        Returns:
            bool: True when the view is not already at the start.
        """

        return self._view_start_ms > 0

    def can_pan_right(self) -> bool:
        """
        Returns whether the visible range can shift later in time.

        Returns:
            bool: True when the view is not already at the end.
        """

        max_start = max(0, self._duration_ms - self._view_duration_ms)
        return self._view_start_ms < max_start

    def pan_left(self) -> None:
        """
        Jumps one page toward earlier times.

        Returns:
            None
        """

        self._jump_by_pages(-1)

    def pan_right(self) -> None:
        """
        Jumps one page toward later times.

        Returns:
            None
        """

        self._jump_by_pages(1)

    def set_position(self, position_ms: int) -> None:
        """
        Updates the playhead position and repaints.

        Args:
            position_ms: Current playhead position in milliseconds.

        Returns:
            None
        """

        self._position_ms = position_ms
        self.update()

    def set_annotations(self, annotations: list[VideoAnnotationModel]) -> None:
        """
        Replaces the annotation list shown as timeline rows.

        Args:
            annotations: Complete annotation list for the loaded video.

        Returns:
            None
        """

        self._annotations = annotations
        self._resize_for_row_count()
        self.update()

    def refresh(self) -> None:
        """
        Resizes rows and repaints after annotations changed in place elsewhere.

        Returns:
            None
        """

        self._resize_for_row_count()
        self.update()

    def selected_annotation_id(self) -> str:
        """
        Returns the currently selected annotation id.

        Returns:
            str: Selected annotation id, or empty string when none selected.
        """

        return self._selected_id

    def _default_page_duration_ms(self) -> int:
        """
        Returns the default visible page duration for one loaded video.

        Returns:
            int: Page duration in milliseconds.
        """

        if self._duration_ms <= MIN_VIEW_DURATION_MS:
            return self._duration_ms
        page_ms = max(MIN_VIEW_DURATION_MS, self._duration_ms // DEFAULT_VISIBLE_PAGES)
        return min(self._duration_ms, page_ms)

    def _resize_for_row_count(self) -> None:
        """
        Grows the widget's minimum height to fit all annotation rows.

        Returns:
            None
        """

        row_count = len(self._annotations)
        height = RULER_HEIGHT + row_count * (ROW_HEIGHT + ROW_SPACING) + ROW_SPACING
        self.setMinimumHeight(max(RULER_HEIGHT + ROW_HEIGHT + ROW_SPACING, height))

    def _content_width(self) -> int:
        """
        Returns the horizontal extent used for timeline rendering.

        Returns:
            int: Total widget content width in pixels.
        """

        return max(LABEL_WIDTH + 1, self.width())

    def _track_area_rect(self) -> QRect:
        """
        Returns the rectangle available for the ms-to-pixel track area.

        Returns:
            QRect: Track area, excluding the left label column.
        """

        return QRect(LABEL_WIDTH, 0, max(1, self.width() - LABEL_WIDTH), self.height())

    def _clamp_view(self) -> None:
        """
        Clamps the visible time range to valid bounds.

        Returns:
            None
        """

        self._view_duration_ms = max(
            MIN_VIEW_DURATION_MS,
            min(self._duration_ms, self._view_duration_ms),
        )
        max_start = max(0, self._duration_ms - self._view_duration_ms)
        self._view_start_ms = max(0, min(max_start, self._view_start_ms))

    def _tick_interval_ms(self, visible_ms: int) -> int:
        """
        Picks a readable ruler tick spacing for one visible time span.

        Args:
            visible_ms: Visible timeline duration in milliseconds.

        Returns:
            int: Tick interval in milliseconds.
        """

        target_ticks = 10
        raw = max(1, visible_ms // target_ticks)
        magnitude = 1
        while magnitude * 10 <= raw:
            magnitude *= 10
        for step in (1, 2, 5, 10):
            interval = step * magnitude
            if interval >= raw:
                return interval
        return magnitude * 10

    def _ms_to_x(self, ms: int) -> int:
        """
        Converts a timeline position to a pixel x coordinate.

        Args:
            ms: Position in milliseconds.

        Returns:
            int: Pixel x coordinate within the track area.
        """

        track = self._track_area_rect()
        ratio = (ms - self._view_start_ms) / max(1, self._view_duration_ms)
        return track.x() + int(ratio * track.width())

    def _x_to_ms(self, x: int) -> int:
        """
        Converts a pixel x coordinate to a clamped timeline position.

        Args:
            x: Pixel x coordinate.

        Returns:
            int: Clamped position in milliseconds within [0, duration].
        """

        track = self._track_area_rect()
        ratio = (x - track.x()) / max(1, track.width())
        ms = self._view_start_ms + ratio * self._view_duration_ms
        return int(max(0, min(self._duration_ms, ms)))

    def _jump_by_pages(self, pages: int) -> None:
        """
        Jumps the visible window by whole pages.

        Args:
            pages: Number of pages to move (negative = earlier).

        Returns:
            None
        """

        if pages == 0:
            return
        step_ms = self._view_duration_ms
        max_start = max(0, self._duration_ms - self._view_duration_ms)
        new_start = self._view_start_ms + pages * step_ms
        self._view_start_ms = max(0, min(max_start, new_start))
        self.update()

    def _zoom_at_x(self, x: int, factor: float) -> None:
        """
        Zooms the timeline in or out while keeping one anchor time fixed.

        Args:
            x: Anchor x coordinate in widget space.
            factor: Multiplier applied to the visible duration (>1 zooms out).

        Returns:
            None
        """

        track = self._track_area_rect()
        if track.width() <= 0:
            return
        anchor_ms = self._x_to_ms(x)
        ratio = (x - track.x()) / track.width()
        new_duration = int(self._view_duration_ms * factor)
        new_duration = max(MIN_VIEW_DURATION_MS, min(self._duration_ms, new_duration))
        new_start = int(anchor_ms - ratio * new_duration)
        self._view_duration_ms = new_duration
        self._view_start_ms = new_start
        self._clamp_view()
        self.update()

    def _handle_ctrl_navigation(self, pos_x: int) -> None:
        """
        Jumps timeline pages while Ctrl is held and the mouse moves horizontally.

        Args:
            pos_x: Current mouse x coordinate in widget space.

        Returns:
            None
        """

        if self._ctrl_nav_anchor_x is None:
            self._ctrl_nav_anchor_x = pos_x
            return

        delta_x = pos_x - self._ctrl_nav_anchor_x
        while delta_x >= CTRL_NAV_THRESHOLD_PX:
            self._jump_by_pages(1)
            self._ctrl_nav_anchor_x += CTRL_NAV_THRESHOLD_PX
            delta_x -= CTRL_NAV_THRESHOLD_PX
        while delta_x <= -CTRL_NAV_THRESHOLD_PX:
            self._jump_by_pages(-1)
            self._ctrl_nav_anchor_x -= CTRL_NAV_THRESHOLD_PX
            delta_x += CTRL_NAV_THRESHOLD_PX

    def _row_rect(self, index: int) -> QRect:
        """
        Returns the full-width rectangle for one annotation row.

        Args:
            index: Row index within the annotation list.

        Returns:
            QRect: Row rectangle including the label column.
        """

        top = RULER_HEIGHT + index * (ROW_HEIGHT + ROW_SPACING) + ROW_SPACING
        return QRect(0, top, self._content_width(), ROW_HEIGHT)

    def _bar_rect(self, index: int, annotation: VideoAnnotationModel) -> QRect:
        """
        Returns the draggable bar rectangle for one annotation row.

        Args:
            index: Row index within the annotation list.
            annotation: Annotation model for this row.

        Returns:
            QRect: Bar rectangle in widget coordinates.
        """

        row = self._row_rect(index)
        start_x = self._ms_to_x(annotation.start_ms)
        end_x = self._ms_to_x(annotation.end_ms)
        return QRect(start_x, row.y(), max(4, end_x - start_x), row.height())

    def paintEvent(self, _event) -> None:
        """
        Paints the ruler, playhead, and all annotation bars.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        content_width = self._content_width()
        track = self._track_area_rect()
        painter.fillRect(0, 0, content_width, RULER_HEIGHT, QColor(40, 40, 40))
        painter.setPen(QPen(QColor(150, 150, 150)))
        view_end_ms = self._view_start_ms + self._view_duration_ms
        tick_interval = self._tick_interval_ms(self._view_duration_ms)
        first_tick = (
            ((self._view_start_ms + tick_interval - 1) // tick_interval) * tick_interval
        )
        tick_ms = first_tick
        while tick_ms <= view_end_ms:
            x = self._ms_to_x(tick_ms)
            if track.x() <= x <= track.x() + track.width():
                painter.drawLine(x, RULER_HEIGHT - 6, x, RULER_HEIGHT)
                painter.drawText(x + 2, RULER_HEIGHT - 8, f"{tick_ms / 1000:.1f}s")
            tick_ms += tick_interval

        for index, annotation in enumerate(self._annotations):
            row = self._row_rect(index)
            painter.fillRect(
                QRect(0, row.y(), LABEL_WIDTH, row.height()), QColor(45, 45, 45)
            )
            label = f"{annotation.annotation_type}"
            if annotation.text:
                label += f": {annotation.text[:16]}"
            painter.setPen(QPen(QColor(220, 220, 220)))
            painter.drawText(
                QRect(6, row.y(), LABEL_WIDTH - 10, row.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label,
            )

            bar = self._bar_rect(index, annotation)
            color = list_to_color(annotation.stroke_rgba)
            fill_color = QColor(color)
            fill_color.setAlpha(140)
            painter.fillRect(bar, fill_color)
            border_color = QColor(255, 255, 255) if annotation.annotation_id == self._selected_id else color
            painter.setPen(QPen(border_color, 2))
            painter.drawRect(bar.adjusted(0, 0, -1, -1))

        playhead_x = self._ms_to_x(self._position_ms)
        painter.setPen(QPen(QColor(231, 76, 60), 2))
        painter.drawLine(playhead_x, 0, playhead_x, self.height())

    def _hit_test(self, pos) -> tuple[int, VideoAnnotationModel, str] | None:
        """
        Determines which annotation row/edge was hit by a mouse position.

        Args:
            pos: Mouse position in widget coordinates.

        Returns:
            tuple[int, VideoAnnotationModel, str] | None: Row index, annotation,
            and drag mode (move/start/end), or None when nothing was hit.
        """

        for index, annotation in enumerate(self._annotations):
            bar = self._bar_rect(index, annotation)
            if not bar.contains(pos):
                continue
            if pos.x() <= bar.x() + EDGE_HIT_PX:
                return index, annotation, DRAG_MODE_START
            if pos.x() >= bar.x() + bar.width() - EDGE_HIT_PX:
                return index, annotation, DRAG_MODE_END
            return index, annotation, DRAG_MODE_MOVE
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Starts a playhead seek or an annotation bar drag.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position().toPoint()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if pos.x() >= LABEL_WIDTH:
                self._ctrl_nav_anchor_x = pos.x()
            return

        if pos.y() < RULER_HEIGHT:
            self._drag_mode = DRAG_MODE_PLAYHEAD
            self.seek_requested.emit(self._x_to_ms(pos.x()))
            return

        hit = self._hit_test(pos)
        if hit is None:
            return
        _index, annotation, mode = hit
        self._selected_id = annotation.annotation_id
        self.annotation_selected.emit(annotation.annotation_id)
        self._drag_mode = mode
        self._drag_annotation = annotation
        self._drag_anchor_ms = self._x_to_ms(pos.x())
        self._drag_orig_start = annotation.start_ms
        self._drag_orig_end = annotation.end_ms
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Updates the playhead or drags the active annotation bar/edge.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        pos = event.position().toPoint()

        if (
            self._drag_mode == ""
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and pos.x() >= LABEL_WIDTH
        ):
            self._handle_ctrl_navigation(pos.x())
            return

        if self._drag_mode == DRAG_MODE_PLAYHEAD:
            self.seek_requested.emit(self._x_to_ms(pos.x()))
            return

        if self._drag_mode and self._drag_annotation is not None:
            current_ms = self._x_to_ms(pos.x())
            annotation = self._drag_annotation
            if self._drag_mode == DRAG_MODE_MOVE:
                delta = current_ms - self._drag_anchor_ms
                duration = self._drag_orig_end - self._drag_orig_start
                new_start = max(0, min(self._duration_ms - duration, self._drag_orig_start + delta))
                new_end = new_start + duration
            elif self._drag_mode == DRAG_MODE_START:
                new_start = max(0, min(current_ms, annotation.end_ms - MIN_ANNOTATION_DURATION_MS))
                new_end = annotation.end_ms
            else:
                new_end = min(self._duration_ms, max(current_ms, annotation.start_ms + MIN_ANNOTATION_DURATION_MS))
                new_start = annotation.start_ms

            annotation.start_ms = new_start
            annotation.end_ms = new_end
            self.annotation_time_changed.emit(annotation.annotation_id, new_start, new_end)
            self.update()
            return

        if self._ctrl_nav_anchor_x is not None:
            self._ctrl_nav_anchor_x = None

        cursor = Qt.CursorShape.ArrowCursor
        hit = self._hit_test(pos)
        if hit is not None:
            _index, _annotation, mode = hit
            if mode in (DRAG_MODE_START, DRAG_MODE_END):
                cursor = Qt.CursorShape.SizeHorCursor
            else:
                cursor = Qt.CursorShape.OpenHandCursor
        self.setCursor(cursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Ends the active drag operation.

        Args:
            event: Mouse release event.

        Returns:
            None
        """

        self._drag_mode = ""
        self._drag_annotation = None
        self._ctrl_nav_anchor_x = None
        self.unsetCursor()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Zooms with Ctrl+wheel on the track area.

        Args:
            event: Wheel event.

        Returns:
            None
        """

        pos = event.position().toPoint()
        if pos.x() < LABEL_WIDTH:
            return

        track = self._track_area_rect()
        if track.width() <= 0:
            return

        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return

        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta == 0:
            return
        factor = ZOOM_WHEEL_FACTOR if delta < 0 else 1.0 / ZOOM_WHEEL_FACTOR
        self._zoom_at_x(pos.x(), factor)
        event.accept()
