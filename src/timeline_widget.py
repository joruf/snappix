"""
Timeline widget: scrub bar and draggable/resizable annotation bars for the
Snappix video editor.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygon,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QMenu, QScrollBar, QSizePolicy, QWidget

from src.annotation_items import list_to_color
from src.color_contrast import ensure_min_contrast
from src.theme import get_theme_colors
from src.video_effects import track_effect_summary
from src.video_models import VideoAnnotationModel

LABEL_WIDTH = 160
RULER_HEIGHT = 28
ROW_HEIGHT = 20
ROW_SPACING = 4
SCROLLBAR_WIDTH = 14
EDGE_HIT_PX = 6
MIN_ANNOTATION_DURATION_MS = 100
MIN_VIEW_DURATION_MS = 500
DEFAULT_PAGE_DURATION_MS = 20_000
# Cap on how many pages the initial 20s view may split a video into. Without it
# a 30-minute recording would open as 90 pages of arrow-button paging.
MAX_DEFAULT_PAGES = 12
ZOOM_WHEEL_FACTOR = 1.15
CTRL_NAV_THRESHOLD_PX = 48
DRAG_AUTO_PAN_EDGE_PX = 24

# Playhead is drawn twice: a wide halo, then a narrower core on top. Whichever
# of the two opposes the bar underneath carries the separation.
PLAYHEAD_HALO_WIDTH_PX = 4
PLAYHEAD_CORE_WIDTH_PX = 2
PLAYHEAD_HANDLE_PX = 6
# Selected bars get a thicker accent outline instead of a white one.
SELECTED_BAR_BORDER_PX = 3
# Bars are a tint of the annotation's own color, not a solid block.
BAR_FILL_ALPHA = 140
# Effect summaries are written inside the bar, which is far wider than the
# fixed label column on the left.
EFFECT_LABEL_PADDING_PX = 6
EFFECT_LABEL_MIN_WIDTH_PX = 24

DRAG_MODE_PLAYHEAD = "playhead"
DRAG_MODE_MOVE = "move"
DRAG_MODE_START = "start"
DRAG_MODE_END = "end"
DRAG_MODE_ZOOM = "zoom"

# Pixels of double-click-and-hold horizontal drag needed for one e-fold
# (~2.72x) change in the visible time range. Smaller values make the
# stretch/compress gesture more sensitive.
ZOOM_DRAG_SENSITIVITY_PX = 160.0


class TimelineWidget(QWidget):
    """
    Displays a scrub ruler and one row per video annotation, each shown as a
    draggable/resizable time-range bar.
    """

    seek_requested = Signal(int)
    annotation_time_changed = Signal(str, int, int)
    annotation_time_change_committed = Signal(str, int, int)
    annotation_selected = Signal(str)
    annotation_delete_requested = Signal(str)
    effect_edit_requested = Signal(str)

    def __init__(self) -> None:
        """
        Initializes the timeline with an empty annotation list.
        """

        super().__init__()
        self.setMinimumHeight(RULER_HEIGHT + ROW_HEIGHT + ROW_SPACING)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        # Click focus lets Delete reach this widget after a track bar was picked.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self._zoom_drag_anchor_x = 0
        self._zoom_drag_last_x = 0
        self._scroll_y = 0
        self._vscroll = QScrollBar(Qt.Orientation.Vertical, self)
        self._vscroll.setVisible(False)
        self._vscroll.valueChanged.connect(self._on_vertical_scroll)
        self._updating_scroll = False

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
        self._sync_vertical_scroll()
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

    def next_annotation_start_ms(self) -> int | None:
        """
        Returns the start of the first annotation beginning after the playhead.

        Returns:
            int | None: Timeline position in milliseconds, or None when the
            playhead is already at or past the last annotation start.
        """

        later = [
            annotation.start_ms
            for annotation in self._annotations
            if annotation.start_ms > self._position_ms
        ]
        return min(later) if later else None

    def previous_annotation_start_ms(self) -> int | None:
        """
        Returns the start of the last annotation beginning before the playhead.

        Returns:
            int | None: Timeline position in milliseconds, or None when no
            annotation starts earlier.
        """

        earlier = [
            annotation.start_ms
            for annotation in self._annotations
            if annotation.start_ms < self._position_ms
        ]
        return max(earlier) if earlier else None

    def jump_to_next_annotation(self) -> bool:
        """
        Moves the playhead to the next annotation start and reveals it.

        Returns:
            bool: True when a later annotation existed to jump to.
        """

        return self._jump_to_position(self.next_annotation_start_ms())

    def jump_to_previous_annotation(self) -> bool:
        """
        Moves the playhead to the previous annotation start and reveals it.

        Returns:
            bool: True when an earlier annotation existed to jump to.
        """

        return self._jump_to_position(self.previous_annotation_start_ms())

    def _jump_to_position(self, target_ms: int | None) -> bool:
        """
        Seeks to one timeline position, scrolling it into view when off-screen.

        Args:
            target_ms: Destination in milliseconds, or None for "nothing to do".

        Returns:
            bool: True when a seek was performed.
        """

        if target_ms is None:
            return False

        view_end = self._view_start_ms + self._view_duration_ms
        if not self._view_start_ms <= target_ms <= view_end:
            self._view_start_ms = target_ms - self._view_duration_ms // 2
            self._clamp_view()

        self._position_ms = target_ms
        self.seek_requested.emit(target_ms)
        self.update()
        return True

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
        self._sync_vertical_scroll()
        self.update()

    def refresh(self) -> None:
        """
        Syncs vertical scroll and repaints after annotations changed in place elsewhere.

        Returns:
            None
        """

        self._sync_vertical_scroll()
        self.update()

    def selected_annotation_id(self) -> str:
        """
        Returns the currently selected annotation id.

        Returns:
            str: Selected annotation id, or empty string when none selected.
        """

        return self._selected_id

    def clear_selection(self) -> None:
        """
        Drops the current track bar selection and repaints.

        Returns:
            None
        """

        if not self._selected_id:
            return
        self._selected_id = ""
        self.update()

    def _default_page_duration_ms(self) -> int:
        """
        Returns the default visible time range when a video is loaded.

        Short clips (20 seconds or less) use the full duration. Longer videos
        start on a fixed 20-second page so a 100-second clip spans five pages.
        Very long videos widen the page instead, so paging never exceeds
        :data:`MAX_DEFAULT_PAGES` steps (a 30-minute video opens on 2.5-minute
        pages rather than 90 twenty-second ones).

        Returns:
            int: Visible duration in milliseconds.
        """

        if self._duration_ms <= DEFAULT_PAGE_DURATION_MS:
            return self._duration_ms
        return max(DEFAULT_PAGE_DURATION_MS, self._duration_ms // MAX_DEFAULT_PAGES)

    def _rows_content_height(self) -> int:
        """
        Returns the pixel height needed for every annotation row.

        Returns:
            int: Content height below the ruler.
        """

        row_count = len(self._annotations)
        if row_count <= 0:
            return ROW_HEIGHT + ROW_SPACING
        return row_count * (ROW_HEIGHT + ROW_SPACING) + ROW_SPACING

    def _rows_viewport_height(self) -> int:
        """
        Returns the visible height available for annotation rows.

        Returns:
            int: Viewport height below the sticky ruler.
        """

        return max(0, self.height() - RULER_HEIGHT)

    def _max_scroll_y(self) -> int:
        """
        Returns the maximum vertical scroll offset in pixels.

        Returns:
            int: Max scroll value (0 when all rows fit).
        """

        return max(0, self._rows_content_height() - self._rows_viewport_height())

    def _scrollbar_width(self) -> int:
        """
        Returns the reserved width for the vertical scrollbar when needed.

        Returns:
            int: Scrollbar width in pixels, or 0 when hidden.
        """

        return SCROLLBAR_WIDTH if self._max_scroll_y() > 0 else 0

    def _sync_vertical_scroll(self) -> None:
        """
        Updates scrollbar range/visibility and clamps the scroll offset.

        Returns:
            None
        """

        max_scroll = self._max_scroll_y()
        self._scroll_y = max(0, min(self._scroll_y, max_scroll))
        needs_bar = max_scroll > 0
        self._updating_scroll = True
        try:
            self._vscroll.setVisible(needs_bar)
            self._vscroll.setRange(0, max_scroll)
            self._vscroll.setPageStep(max(1, self._rows_viewport_height()))
            self._vscroll.setSingleStep(ROW_HEIGHT + ROW_SPACING)
            self._vscroll.setValue(self._scroll_y)
        finally:
            self._updating_scroll = False
        self._layout_scrollbar()

    def _layout_scrollbar(self) -> None:
        """
        Positions the vertical scrollbar beside the row viewport.

        Returns:
            None
        """

        if not self._vscroll.isVisible():
            return
        self._vscroll.setGeometry(
            self.width() - SCROLLBAR_WIDTH,
            RULER_HEIGHT,
            SCROLLBAR_WIDTH,
            max(0, self.height() - RULER_HEIGHT),
        )

    def _on_vertical_scroll(self, value: int) -> None:
        """
        Applies scrollbar-driven vertical offset.

        Args:
            value: New scroll offset in pixels.

        Returns:
            None
        """

        if self._updating_scroll:
            return
        self._scroll_y = max(0, min(int(value), self._max_scroll_y()))
        self.update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        Keeps vertical scroll bounds and scrollbar layout in sync.

        Args:
            event: Resize event.

        Returns:
            None
        """

        super().resizeEvent(event)
        self._sync_vertical_scroll()

    def _content_width(self) -> int:
        """
        Returns the horizontal extent used for timeline rendering.

        Returns:
            int: Total widget content width in pixels excluding the scrollbar.
        """

        return max(LABEL_WIDTH + 1, self.width() - self._scrollbar_width())

    def _track_area_rect(self) -> QRect:
        """
        Returns the rectangle available for the ms-to-pixel track area.

        Returns:
            QRect: Track area, excluding the left label column and scrollbar.
        """

        return QRect(
            LABEL_WIDTH,
            0,
            max(1, self._content_width() - LABEL_WIDTH),
            self.height(),
        )

    def _row_rect(self, index: int) -> QRect:
        """
        Returns the full-width rectangle for one annotation row.

        Args:
            index: Row index within the annotation list.

        Returns:
            QRect: Row rectangle including the label column.
        """

        top = (
            RULER_HEIGHT
            + index * (ROW_HEIGHT + ROW_SPACING)
            + ROW_SPACING
            - self._scroll_y
        )
        return QRect(0, top, self._content_width(), ROW_HEIGHT)

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

    def _grid_interval_ms(self) -> int:
        """
        Returns the snap/grid interval for the current zoom level.

        Returns:
            int: Grid spacing in milliseconds.
        """

        return self._tick_interval_ms(self._view_duration_ms)

    def _snap_ms(self, ms: int) -> int:
        """
        Snaps a timeline position onto the nearest grid line or playhead.

        Args:
            ms: Unsnapped position in milliseconds.

        Returns:
            int: Snapped position clamped to ``[0, duration]``.
        """

        interval = max(1, self._grid_interval_ms())
        grid = int(round(float(ms) / float(interval)) * interval)
        grid = max(0, min(self._duration_ms, grid))
        playhead = max(0, min(self._duration_ms, int(self._position_ms)))
        # Prefer whichever magnet is closer so bars can share a start with the
        # red playhead even when it sits between grid lines.
        if abs(ms - playhead) <= abs(ms - grid):
            return playhead
        return grid

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

        return self._ms_from_track_x(x)

    def _ms_from_track_x(self, x: int) -> int:
        """
        Maps one track x coordinate to timeline milliseconds.

        Values outside the visible track extrapolate to earlier/later times and
        are clamped only to the full video duration.

        Args:
            x: Pixel x coordinate in widget space.

        Returns:
            int: Timeline position in milliseconds within [0, duration].
        """

        track = self._track_area_rect()
        ratio = (x - track.x()) / max(1, track.width())
        ms = self._view_start_ms + ratio * self._view_duration_ms
        return int(max(0, min(self._duration_ms, ms)))

    def _auto_pan_view_during_drag(self, pos_x: int) -> None:
        """
        Pans the visible timeline range while dragging an annotation near an edge.

        Args:
            pos_x: Current mouse x coordinate in widget space.

        Returns:
            None
        """

        if self._drag_mode in ("", DRAG_MODE_PLAYHEAD):
            return

        track = self._track_area_rect()
        max_start = max(0, self._duration_ms - self._view_duration_ms)
        old_start = self._view_start_ms

        if pos_x < track.x() + DRAG_AUTO_PAN_EDGE_PX and self._view_start_ms > 0:
            overflow = track.x() + DRAG_AUTO_PAN_EDGE_PX - pos_x
            pan_ms = max(
                100,
                int(overflow / max(1, track.width()) * self._view_duration_ms),
            )
            self._view_start_ms = max(0, self._view_start_ms - pan_ms)
        elif (
            pos_x > track.x() + track.width() - DRAG_AUTO_PAN_EDGE_PX
            and self._view_start_ms < max_start
        ):
            overflow = pos_x - (track.x() + track.width() - DRAG_AUTO_PAN_EDGE_PX)
            pan_ms = max(
                100,
                int(overflow / max(1, track.width()) * self._view_duration_ms),
            )
            self._view_start_ms = min(max_start, self._view_start_ms + pan_ms)

        if self._view_start_ms == old_start:
            return

        if self._drag_mode == DRAG_MODE_MOVE:
            self._drag_anchor_ms += self._view_start_ms - old_start

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

        colors = get_theme_colors()
        content_width = self._content_width()
        track = self._track_area_rect()
        # Paint the track surface explicitly rather than inheriting whatever the
        # global stylesheet happens to set, so the widget is themed on its own.
        painter.fillRect(self.rect(), QColor(colors.window_bg))
        painter.fillRect(0, 0, content_width, RULER_HEIGHT, QColor(colors.surface_alt))
        view_end_ms = self._view_start_ms + self._view_duration_ms
        tick_interval = self._grid_interval_ms()
        first_tick = (
            ((self._view_start_ms + tick_interval - 1) // tick_interval) * tick_interval
        )

        # Vertical snap grid across the track (ruler + rows).
        painter.setPen(QPen(QColor(colors.border)))
        tick_ms = first_tick
        while tick_ms <= view_end_ms:
            x = self._ms_to_x(tick_ms)
            if track.x() <= x <= track.x() + track.width():
                painter.drawLine(x, 0, x, self.height())
            tick_ms += tick_interval

        painter.setPen(QPen(QColor(colors.text_muted)))
        tick_ms = first_tick
        while tick_ms <= view_end_ms:
            x = self._ms_to_x(tick_ms)
            if track.x() <= x <= track.x() + track.width():
                painter.drawLine(x, RULER_HEIGHT - 6, x, RULER_HEIGHT)
                painter.drawText(x + 2, RULER_HEIGHT - 8, f"{tick_ms / 1000:.1f}s")
            tick_ms += tick_interval

        painter.save()
        painter.setClipRect(
            0,
            RULER_HEIGHT,
            content_width,
            max(0, self.height() - RULER_HEIGHT),
        )
        for index, annotation in enumerate(self._annotations):
            row = self._row_rect(index)
            if row.bottom() < RULER_HEIGHT or row.top() > self.height():
                continue
            painter.fillRect(
                QRect(0, row.y(), LABEL_WIDTH, row.height()), QColor(colors.surface)
            )
            label = f"{annotation.annotation_type}"
            if annotation.text:
                label += f": {annotation.text[:16]}"
            painter.setPen(QPen(QColor(colors.text)))
            painter.drawText(
                QRect(6, row.y(), LABEL_WIDTH - 10, row.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label,
            )

            bar = self._bar_rect(index, annotation)
            # An annotation's own color can sit right on top of the track color
            # -- a text object's dark navy vanishes on the dark themes and reads
            # as disabled. Lift it just far enough to stay a distinct object.
            # The tint alpha has to be applied *before* measuring, or the
            # blend drags the guaranteed contrast back below the threshold.
            track_bg = QColor(colors.window_bg)
            raw_color = list_to_color(annotation.stroke_rgba)
            fill_color = QColor(raw_color)
            fill_color.setAlpha(BAR_FILL_ALPHA)
            fill_color = ensure_min_contrast(fill_color, track_bg)
            painter.fillRect(bar, fill_color)
            color = ensure_min_contrast(QColor(raw_color), track_bg)
            is_selected = annotation.annotation_id == self._selected_id
            # Selection reads as the app's accent, not white: a white outline
            # vanishes on the light and sepia themes.
            border_color = QColor(colors.accent) if is_selected else color
            painter.setPen(QPen(border_color, SELECTED_BAR_BORDER_PX if is_selected else 2))
            painter.drawRect(bar.adjusted(0, 0, -1, -1))
            self._paint_bar_effect_summary(painter, bar, annotation, colors)
        painter.restore()

        self._paint_playhead(painter, colors)

    def _paint_bar_effect_summary(
        self,
        painter: QPainter,
        bar: QRect,
        annotation: VideoAnnotationModel,
        colors,
    ) -> None:
        """
        Writes the effect summary right-aligned inside the annotation's bar.

        The bar is far wider than the fixed label column, so "Fade In, Zoom Out"
        fits there without truncating the annotation's own name.

        Args:
            painter: Active painter, already clipped to the row area.
            bar: The annotation's bar rectangle.
            annotation: Annotation being drawn.
            colors: Resolved theme color tokens.

        Returns:
            None
        """

        summary = track_effect_summary(annotation)
        if not summary:
            return

        text_rect = bar.adjusted(EFFECT_LABEL_PADDING_PX, 0, -EFFECT_LABEL_PADDING_PX, 0)
        if text_rect.width() < EFFECT_LABEL_MIN_WIDTH_PX:
            return

        metrics = painter.fontMetrics()
        elided = metrics.elidedText(
            summary,
            Qt.TextElideMode.ElideRight,
            text_rect.width(),
        )
        painter.save()
        painter.setPen(QPen(ensure_min_contrast(QColor(colors.text), QColor(colors.window_bg))))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            elided,
        )
        painter.restore()

    def _paint_playhead(self, painter: QPainter, colors) -> None:
        """
        Draws the playhead as a haloed line with a handle in the ruler.

        The halo is what makes this readable: every hue in the drawing palette
        belongs to user content, so a colored line would sooner or later sit on
        a bar of its own color. A light core over a dark outline (inverted on
        light themes) separates from any background without competing with the
        annotations for saturation.

        Args:
            painter: Active painter on this widget.
            colors: Resolved theme color tokens.

        Returns:
            None
        """

        playhead_x = self._ms_to_x(self._position_ms)
        core = QColor(colors.timeline_playhead)
        halo = QColor(colors.timeline_playhead_halo)

        painter.setPen(QPen(halo, PLAYHEAD_HALO_WIDTH_PX))
        painter.drawLine(playhead_x, 0, playhead_x, self.height())
        painter.setPen(QPen(core, PLAYHEAD_CORE_WIDTH_PX))
        painter.drawLine(playhead_x, 0, playhead_x, self.height())

        handle = QPolygon(
            [
                QPoint(playhead_x - PLAYHEAD_HANDLE_PX, 0),
                QPoint(playhead_x + PLAYHEAD_HANDLE_PX, 0),
                QPoint(playhead_x, PLAYHEAD_HANDLE_PX + 2),
            ]
        )
        painter.setPen(QPen(halo, 1))
        painter.setBrush(core)
        painter.drawPolygon(handle)
        painter.setBrush(Qt.BrushStyle.NoBrush)

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
            if bar.bottom() < RULER_HEIGHT or bar.top() > self.height():
                continue
            # Ignore the portion scrolled under the sticky ruler.
            visible = bar.intersected(
                QRect(0, RULER_HEIGHT, self._content_width(), self._rows_viewport_height())
            )
            if not visible.contains(pos):
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
            # A plain click on empty track space also scrubs the playhead,
            # matching the ruler's click-to-seek behavior.
            self._drag_mode = DRAG_MODE_PLAYHEAD
            self.seek_requested.emit(self._x_to_ms(pos.x()))
            return
        _index, annotation, mode = hit
        self._selected_id = annotation.annotation_id
        self.annotation_selected.emit(annotation.annotation_id)
        self._drag_mode = mode
        self._drag_annotation = annotation
        self._drag_anchor_ms = self._x_to_ms(pos.x())
        self._drag_orig_start = annotation.start_ms
        self._drag_orig_end = annotation.end_ms
        self.grabMouse()
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """
        Arms a stretch/compress zoom drag anchored at the double-click point.

        Holding the button after the second click and dragging left or right
        compresses or stretches the visible time range around this anchor;
        releasing ends the gesture. The anchor stays fixed under the cursor
        for the whole drag, like a pinch-zoom gesture.

        Args:
            event: Mouse double-click event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        self._drag_mode = DRAG_MODE_ZOOM
        self._zoom_drag_anchor_x = pos.x()
        self._zoom_drag_last_x = pos.x()
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.grabMouse()

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

        if self._drag_mode == DRAG_MODE_ZOOM:
            delta_x = pos.x() - self._zoom_drag_last_x
            if delta_x != 0:
                factor = math.exp(-delta_x / ZOOM_DRAG_SENSITIVITY_PX)
                self._zoom_at_x(self._zoom_drag_anchor_x, factor)
                self._zoom_drag_last_x = pos.x()
            return

        if self._drag_mode and self._drag_annotation is not None:
            self._auto_pan_view_during_drag(pos.x())
            current_ms = self._ms_from_track_x(pos.x())
            annotation = self._drag_annotation
            if self._drag_mode == DRAG_MODE_MOVE:
                delta = current_ms - self._drag_anchor_ms
                duration = self._drag_orig_end - self._drag_orig_start
                raw_start = self._drag_orig_start + delta
                new_start = self._snap_ms(raw_start)
                new_start = max(0, min(self._duration_ms - duration, new_start))
                new_end = new_start + duration
            elif self._drag_mode == DRAG_MODE_START:
                snapped = self._snap_ms(current_ms)
                new_start = max(0, min(snapped, annotation.end_ms - MIN_ANNOTATION_DURATION_MS))
                new_end = annotation.end_ms
            else:
                snapped = self._snap_ms(current_ms)
                new_end = min(
                    self._duration_ms,
                    max(snapped, annotation.start_ms + MIN_ANNOTATION_DURATION_MS),
                )
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

        if (
            self._drag_mode in {DRAG_MODE_MOVE, DRAG_MODE_START, DRAG_MODE_END}
            and self._drag_annotation is not None
        ):
            annotation = self._drag_annotation
            if (
                annotation.start_ms != self._drag_orig_start
                or annotation.end_ms != self._drag_orig_end
            ):
                self.annotation_time_change_committed.emit(
                    annotation.annotation_id,
                    annotation.start_ms,
                    annotation.end_ms,
                )

        self._drag_mode = ""
        self._drag_annotation = None
        self._ctrl_nav_anchor_x = None
        if self.mouseGrabber() == self:
            self.releaseMouse()
        self.unsetCursor()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        Deletes the selected track bar and its canvas object on Delete.

        Args:
            event: Key press event.

        Returns:
            None
        """

        if event.key() == Qt.Key.Key_Delete and self._selected_id:
            annotation_id = self._selected_id
            # Hand the selection to the preceding row so repeated Delete walks
            # up the track list instead of stranding the keyboard.
            self._selected_id = self._neighbour_annotation_id(annotation_id, -1)
            self.annotation_delete_requested.emit(annotation_id)
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self._annotations:
            step = -1 if event.key() == Qt.Key.Key_Up else 1
            if self.select_relative_row(step):
                event.accept()
                return

        super().keyPressEvent(event)

    def _row_index_of(self, annotation_id: str) -> int:
        """
        Returns the row index of one annotation id.

        Args:
            annotation_id: Annotation to locate.

        Returns:
            int: Row index, or -1 when the id is not present.
        """

        for index, annotation in enumerate(self._annotations):
            if annotation.annotation_id == annotation_id:
                return index
        return -1

    def _neighbour_annotation_id(self, annotation_id: str, step: int) -> str:
        """
        Returns the id of the row next to one annotation.

        Args:
            annotation_id: Reference annotation.
            step: -1 for the previous row, 1 for the next.

        Returns:
            str: Neighbouring annotation id, or empty when there is none.
        """

        index = self._row_index_of(annotation_id)
        if index < 0:
            return ""
        neighbour = index + step
        if 0 <= neighbour < len(self._annotations):
            return self._annotations[neighbour].annotation_id
        # Deleting the first row hands selection to what becomes the new first.
        if step < 0 and len(self._annotations) > 1:
            return self._annotations[1].annotation_id
        return ""

    def select_relative_row(self, step: int) -> bool:
        """
        Moves the track selection up or down by one row.

        With nothing selected yet, the first row is selected so the keyboard
        has somewhere to start.

        Args:
            step: -1 for the previous row, 1 for the next.

        Returns:
            bool: True when the selection changed.
        """

        if not self._annotations:
            return False

        current = self._row_index_of(self._selected_id)
        if current < 0:
            target = 0 if step > 0 else len(self._annotations) - 1
        else:
            target = current + step
            if not 0 <= target < len(self._annotations):
                return False

        annotation = self._annotations[target]
        if annotation.annotation_id == self._selected_id:
            return False
        self._selected_id = annotation.annotation_id
        self._scroll_row_into_view(target)
        self.annotation_selected.emit(self._selected_id)
        self.update()
        return True

    def _scroll_row_into_view(self, index: int) -> None:
        """
        Scrolls the row list so one row is fully visible.

        Args:
            index: Row index to reveal.

        Returns:
            None
        """

        row_stride = ROW_HEIGHT + ROW_SPACING
        row_top = index * row_stride + ROW_SPACING
        row_bottom = row_top + ROW_HEIGHT
        viewport = self._rows_viewport_height()
        if row_top < self._scroll_y:
            self._scroll_y = max(0, row_top - ROW_SPACING)
        elif row_bottom > self._scroll_y + viewport:
            self._scroll_y = max(0, row_bottom - viewport)
        self._sync_vertical_scroll()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Shows an "Add Effect..." context menu when right-clicking one
        annotation's track bar.

        Args:
            event: Context menu event.

        Returns:
            None
        """

        pos = event.pos()
        hit = self._hit_test(pos)
        if hit is None:
            return
        _index, annotation, _mode = hit
        self._selected_id = annotation.annotation_id
        self.annotation_selected.emit(annotation.annotation_id)
        self.update()

        menu = self._build_effect_context_menu(annotation)
        menu.exec(event.globalPos())

    def _build_effect_context_menu(self, annotation: VideoAnnotationModel) -> QMenu:
        """
        Builds the right-click menu for one annotation's track bar.

        Kept separate from :meth:`contextMenuEvent` so tests can trigger its
        actions directly without spinning a real modal ``QMenu.exec`` loop.

        Args:
            annotation: Annotation the menu applies to.

        Returns:
            QMenu: Menu with an "Add Effect..." action wired up.
        """

        menu = QMenu(self)
        effect_action = menu.addAction("Add Effect...")
        effect_action.triggered.connect(
            lambda: self.effect_edit_requested.emit(annotation.annotation_id)
        )
        return menu

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Scrolls rows vertically, or zooms with Ctrl+wheel on the track area.

        Args:
            event: Wheel event.

        Returns:
            None
        """

        pos = event.position().toPoint()
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta == 0:
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if pos.x() < LABEL_WIDTH:
                return
            track = self._track_area_rect()
            if track.width() <= 0:
                return
            factor = ZOOM_WHEEL_FACTOR if delta < 0 else 1.0 / ZOOM_WHEEL_FACTOR
            self._zoom_at_x(pos.x(), factor)
            event.accept()
            return

        if self._max_scroll_y() <= 0:
            return
        # Positive wheel delta scrolls up (toward earlier rows).
        step = ROW_HEIGHT + ROW_SPACING
        steps = max(1, abs(delta) // 120)
        self._scroll_y = max(
            0,
            min(
                self._max_scroll_y(),
                self._scroll_y + (-steps * step if delta > 0 else steps * step),
            ),
        )
        self._updating_scroll = True
        try:
            self._vscroll.setValue(self._scroll_y)
        finally:
            self._updating_scroll = False
        self.update()
        event.accept()
