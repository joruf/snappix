"""
Unit tests for the video editor timeline widget's drag/resize geometry.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QWheelEvent

    from src.timeline_widget import (
        CTRL_NAV_THRESHOLD_PX,
        DEFAULT_PAGE_DURATION_MS,
        EDGE_HIT_PX,
        LABEL_WIDTH,
        RULER_HEIGHT,
        TimelineWidget,
    )
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _make_annotation(start_ms: int = 2000, end_ms: int = 4000) -> "VideoAnnotationModel":
    """
    Builds one test annotation spanning a known time range.

    Args:
        start_ms: Annotation start time in milliseconds.
        end_ms: Annotation end time in milliseconds.

    Returns:
        VideoAnnotationModel: Test annotation.
    """

    return VideoAnnotationModel(
        annotation_type="rect",
        start_ms=start_ms,
        end_ms=end_ms,
        x=0.0,
        y=0.0,
        width=10.0,
        height=10.0,
        stroke_rgba=[255, 0, 0, 255],
        fill_rgba=[255, 0, 0, 70],
        stroke_width=2.0,
    )


def _mouse_event(
    event_type,
    x: float,
    y: float,
    *,
    ctrl: bool = False,
) -> "QMouseEvent":
    """
    Builds a synthetic left-button mouse event at one widget-local position.

    Args:
        event_type: QMouseEvent.Type value.
        x: Local x coordinate.
        y: Local y coordinate.
        ctrl: Whether the Ctrl modifier is held.

    Returns:
        QMouseEvent: Constructed event.
    """

    point = QPointF(x, y)
    modifiers = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    buttons = Qt.MouseButton.LeftButton
    if event_type == QMouseEvent.Type.MouseMove:
        buttons = Qt.MouseButton.LeftButton
    elif event_type == QMouseEvent.Type.MouseButtonRelease:
        buttons = Qt.MouseButton.NoButton
    return QMouseEvent(
        event_type,
        point,
        point,
        buttons,
        buttons,
        modifiers,
    )


def _set_view_page(widget: TimelineWidget, page_ms: int) -> None:
    """
    Narrows the visible timeline range for paging/zoom interaction tests.

    Args:
        widget: Timeline under test.
        page_ms: Visible duration in milliseconds.

    Returns:
        None
    """

    widget._view_start_ms = 0  # pylint: disable=protected-access
    widget._view_duration_ms = page_ms  # pylint: disable=protected-access
    widget._clamp_view()  # pylint: disable=protected-access


def _show_full_timeline(widget: TimelineWidget) -> None:
    """
    Expands the test timeline view to the full duration.

    Args:
        widget: Timeline under test.

    Returns:
        None
    """

    widget._view_start_ms = 0  # pylint: disable=protected-access
    widget._view_duration_ms = widget._duration_ms  # pylint: disable=protected-access
    widget._clamp_view()  # pylint: disable=protected-access


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for timeline widget tests")
class TestTimelineWidgetDragging(unittest.TestCase):
    """
    Verifies playhead seeking and body/edge drag math on the timeline widget.

    Uses a fixed track width of 500px representing 10000ms (20ms/px) when the
    full timeline is visible, and a test annotation spanning [2000, 4000]ms
    which maps to bar x=[260, 360].
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget creation.
        """

        ensure_qapp()

    def _make_widget(self, annotation) -> TimelineWidget:
        """
        Builds a sized TimelineWidget with one annotation row.

        Args:
            annotation: Annotation to display as the single timeline row.

        Returns:
            TimelineWidget: Configured widget.
        """

        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(10000)
        widget.set_annotations([annotation])
        _show_full_timeline(widget)
        return widget

    def _row_mid_y(self) -> float:
        """
        Returns the vertical center of the first annotation row.

        Returns:
            float: Y coordinate within the first row.
        """

        return RULER_HEIGHT + 15.0

    def test_body_drag_moves_both_start_and_end(self) -> None:
        """
        Ensures dragging the bar body shifts start/end together, preserving duration.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        row_y = self._row_mid_y()

        widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, 300.0, row_y))
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 400.0, row_y))
        widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, 400.0, row_y))

        self.assertEqual(annotation.start_ms, 4000)
        self.assertEqual(annotation.end_ms, 6000)

    def test_left_edge_drag_changes_only_start(self) -> None:
        """
        Ensures dragging the left edge changes only start_ms.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        row_y = self._row_mid_y()

        press_x = 260.0 + (EDGE_HIT_PX / 2.0)
        widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, press_x, row_y))
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 310.0, row_y))
        widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, 310.0, row_y))

        self.assertEqual(annotation.start_ms, 3000)
        self.assertEqual(annotation.end_ms, 4000)

    def test_right_edge_drag_changes_only_end(self) -> None:
        """
        Ensures dragging the right edge changes only end_ms.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        row_y = self._row_mid_y()

        press_x = 360.0 - (EDGE_HIT_PX / 2.0)
        widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, press_x, row_y))
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 450.0, row_y))
        widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, 450.0, row_y))

        self.assertEqual(annotation.start_ms, 2000)
        self.assertEqual(annotation.end_ms, 6000)

    def test_body_drag_clamps_to_duration_bounds(self) -> None:
        """
        Ensures a body drag cannot push the annotation past the timeline bounds.
        """

        annotation = _make_annotation(start_ms=8000, end_ms=9500)
        widget = self._make_widget(annotation)
        row_y = self._row_mid_y()

        widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, 600.0, row_y))
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 660.0, row_y))
        widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, 660.0, row_y))

        duration = 1500
        self.assertEqual(annotation.end_ms - annotation.start_ms, duration)
        self.assertLessEqual(annotation.end_ms, 10000)

    def test_ruler_click_emits_seek_requested(self) -> None:
        """
        Ensures clicking the ruler area emits a seek request instead of dragging a bar.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        seeks: list[int] = []
        widget.seek_requested.connect(seeks.append)

        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, 410.0, RULER_HEIGHT - 5.0)
        )

        self.assertEqual(seeks, [5000])
        self.assertEqual(annotation.start_ms, 2000)
        self.assertEqual(annotation.end_ms, 4000)

    def test_body_drag_can_move_beyond_visible_view(self) -> None:
        """
        Ensures annotation drags are not limited to the currently visible time page.
        """

        annotation = _make_annotation(start_ms=6500, end_ms=7500)
        widget = TimelineWidget()
        widget.resize(1200, RULER_HEIGHT + 60)
        widget.set_duration(10000)
        widget.set_annotations([annotation])
        _set_view_page(widget, 2000)
        widget._view_start_ms = 6000  # pylint: disable=protected-access
        widget._clamp_view()  # pylint: disable=protected-access
        row_y = RULER_HEIGHT + 15.0

        widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, 500.0, row_y))
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 1540.0, row_y))
        widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, 1540.0, row_y))

        self.assertEqual(annotation.start_ms, 8400)
        self.assertEqual(annotation.end_ms, 9400)

    def test_start_edge_drag_clamps_at_zero(self) -> None:
        """
        Ensures dragging the start edge cannot move earlier than 0 ms.
        """

        annotation = _make_annotation(start_ms=500, end_ms=2500)
        widget = TimelineWidget()
        widget.resize(1200, RULER_HEIGHT + 60)
        widget.set_duration(10000)
        widget.set_annotations([annotation])
        _set_view_page(widget, 2000)
        row_y = RULER_HEIGHT + 15.0
        press_x = widget._ms_to_x(500) + (EDGE_HIT_PX / 2.0)  # pylint: disable=protected-access

        widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, press_x, row_y))
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 0.0, row_y))
        widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, 0.0, row_y))

        self.assertEqual(annotation.start_ms, 0)
        self.assertEqual(annotation.end_ms, 2500)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for timeline widget tests")
class TestTimelineWidgetNavigation(unittest.TestCase):
    """
    Verifies fixed-width paging and Ctrl navigation on the timeline widget.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget creation.
        """

        ensure_qapp()

    def _make_widget(self) -> TimelineWidget:
        """
        Builds a sized TimelineWidget with a 10s duration.

        Returns:
            TimelineWidget: Configured widget.
        """

        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(10000)
        return widget

    def _wheel_event(self, x: float, y: float, delta_y: int, *, ctrl: bool = False) -> QWheelEvent:
        """
        Builds a synthetic wheel event at one widget-local position.

        Args:
            x: Local x coordinate.
            y: Local y coordinate.
            delta_y: Vertical wheel delta.
            ctrl: Whether the Ctrl modifier is held.

        Returns:
            QWheelEvent: Constructed event.
        """

        point = QPointF(x, y)
        modifiers = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
        return QWheelEvent(
            point,
            point,
            QPoint(0, 0),
            QPoint(0, delta_y),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    def test_track_area_uses_available_widget_width(self) -> None:
        """
        Ensures the timeline track grows with the widget width.
        """

        widget = self._make_widget()
        widget.resize(900, RULER_HEIGHT + 60)
        track = widget._track_area_rect()  # pylint: disable=protected-access
        self.assertEqual(track.width(), 900 - LABEL_WIDTH)
        self.assertEqual(track.x(), LABEL_WIDTH)

    def test_default_view_shows_full_duration_for_short_clips(self) -> None:
        """
        Ensures clips of 20 seconds or less fill the timeline width.
        """

        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(5000)
        self.assertEqual(widget._view_start_ms, 0)  # pylint: disable=protected-access
        self.assertEqual(widget._view_duration_ms, 5000)  # pylint: disable=protected-access

        widget.set_duration(10000)
        self.assertEqual(widget._view_duration_ms, 10000)  # pylint: disable=protected-access

    def test_default_view_shows_twenty_second_page_for_long_clips(self) -> None:
        """
        Ensures longer clips start on a 20-second page (100s -> five pages).
        """

        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(100_000)
        self.assertEqual(widget._view_start_ms, 0)  # pylint: disable=protected-access
        self.assertEqual(widget._view_duration_ms, DEFAULT_PAGE_DURATION_MS)  # pylint: disable=protected-access
        self.assertTrue(widget.can_pan_right())

    def test_pan_buttons_jump_full_pages(self) -> None:
        """
        Ensures arrow buttons jump by one visible page at a time.
        """

        widget = self._make_widget()
        _set_view_page(widget, 2000)
        page_ms = widget._view_duration_ms  # pylint: disable=protected-access
        widget.pan_right()
        self.assertEqual(widget._view_start_ms, page_ms)  # pylint: disable=protected-access
        widget.pan_right()
        self.assertEqual(widget._view_start_ms, page_ms * 2)  # pylint: disable=protected-access
        widget.pan_left()
        self.assertEqual(widget._view_start_ms, page_ms)  # pylint: disable=protected-access

    def test_zoom_in_shows_smaller_time_range(self) -> None:
        """
        Ensures Ctrl+wheel zoom narrows the visible timeline span.
        """

        widget = self._make_widget()
        initial_duration = widget._view_duration_ms  # pylint: disable=protected-access
        widget.wheelEvent(self._wheel_event(410.0, 10.0, 120, ctrl=True))
        self.assertLess(widget._view_duration_ms, initial_duration)  # pylint: disable=protected-access

    def test_seek_after_zoom_maps_cursor_to_visible_time(self) -> None:
        """
        Ensures seeking still resolves to the correct ms after zooming in.
        """

        widget = self._make_widget()
        _set_view_page(widget, 2000)
        widget.wheelEvent(self._wheel_event(410.0, 10.0, 120, ctrl=True))
        seeks: list[int] = []
        widget.seek_requested.connect(seeks.append)
        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, 410.0, RULER_HEIGHT - 5.0)
        )
        self.assertEqual(len(seeks), 1)
        self.assertGreater(seeks[0], 400)
        self.assertLess(seeks[0], 1600)

    def test_ctrl_mouse_move_jumps_pages(self) -> None:
        """
        Ensures Ctrl+horizontal mouse movement jumps timeline pages.
        """

        widget = self._make_widget()
        _set_view_page(widget, 2000)
        page_ms = widget._view_duration_ms  # pylint: disable=protected-access
        start_x = 300.0
        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, start_x, 10.0, ctrl=True)
        )
        widget.mouseMoveEvent(
            _mouse_event(
                QMouseEvent.Type.MouseMove,
                start_x + CTRL_NAV_THRESHOLD_PX,
                10.0,
                ctrl=True,
            )
        )
        self.assertEqual(widget._view_start_ms, page_ms)  # pylint: disable=protected-access
        widget.mouseMoveEvent(
            _mouse_event(
                QMouseEvent.Type.MouseMove,
                start_x,
                10.0,
                ctrl=True,
            )
        )
        self.assertEqual(widget._view_start_ms, 0)  # pylint: disable=protected-access


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for timeline GUI tests")
class TestTimelineWidgetVerticalScroll(unittest.TestCase):
    """
    Verifies vertical scrolling when annotation rows exceed the widget height.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_overflow_rows_enable_vertical_scrollbar(self) -> None:
        """
        Ensures many annotation rows require a vertical scroll range.
        """

        from src.timeline_widget import ROW_HEIGHT, ROW_SPACING, RULER_HEIGHT

        widget = TimelineWidget()
        widget.resize(640, RULER_HEIGHT + 2 * (ROW_HEIGHT + ROW_SPACING))
        widget.set_duration(10_000)
        annotations = [
            _make_annotation(start_ms=i * 100, end_ms=i * 100 + 500) for i in range(12)
        ]
        widget.set_annotations(annotations)
        widget._sync_vertical_scroll()  # pylint: disable=protected-access

        self.assertGreater(widget._max_scroll_y(), 0)  # pylint: disable=protected-access
        self.assertFalse(widget._vscroll.isHidden())  # pylint: disable=protected-access

    def test_vertical_scroll_moves_row_geometry(self) -> None:
        """
        Ensures scrolling shifts row positions so lower bars become reachable.
        """

        from src.timeline_widget import ROW_HEIGHT, ROW_SPACING, RULER_HEIGHT

        widget = TimelineWidget()
        widget.resize(640, RULER_HEIGHT + 2 * (ROW_HEIGHT + ROW_SPACING))
        widget.set_duration(10_000)
        annotations = [
            _make_annotation(start_ms=i * 100, end_ms=i * 100 + 500) for i in range(10)
        ]
        widget.set_annotations(annotations)
        widget._sync_vertical_scroll()  # pylint: disable=protected-access

        before = widget._row_rect(9)  # pylint: disable=protected-access
        self.assertGreater(before.y(), widget.height())

        widget._scroll_y = widget._max_scroll_y()  # pylint: disable=protected-access
        widget._updating_scroll = True  # pylint: disable=protected-access
        widget._vscroll.setValue(widget._scroll_y)  # pylint: disable=protected-access
        widget._updating_scroll = False  # pylint: disable=protected-access

        after = widget._row_rect(9)  # pylint: disable=protected-access
        self.assertLess(after.y(), before.y())
        self.assertLess(after.y(), widget.height())
        self.assertGreaterEqual(after.bottom(), RULER_HEIGHT)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for timeline GUI tests")
class TestTimelineWidgetGridSnap(unittest.TestCase):
    """
    Verifies vertical grid snapping for aligned annotation starts/ends.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        ensure_qapp()

    def test_snap_ms_rounds_to_grid_interval(self) -> None:
        """
        Ensures times snap onto the current zoom grid.
        """

        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(10_000)
        _show_full_timeline(widget)
        # Full 10s view uses a 1000ms grid.
        self.assertEqual(widget._grid_interval_ms(), 1000)  # pylint: disable=protected-access
        self.assertEqual(widget._snap_ms(1499), 1000)  # pylint: disable=protected-access
        self.assertEqual(widget._snap_ms(1500), 2000)  # pylint: disable=protected-access
        self.assertEqual(widget._snap_ms(2000), 2000)  # pylint: disable=protected-access

    def test_snap_ms_prefers_playhead_when_closer(self) -> None:
        """
        Ensures dragging can dock to the red playhead between grid lines.
        """

        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(10_000)
        _show_full_timeline(widget)
        widget.set_position(1234)
        # Closer to playhead 1234 than to grid 1000 or 2000.
        self.assertEqual(widget._snap_ms(1300), 1234)  # pylint: disable=protected-access
        # Closer to grid 2000 than to playhead 1234.
        self.assertEqual(widget._snap_ms(1800), 2000)  # pylint: disable=protected-access

    def test_body_drag_snaps_start_to_shared_grid(self) -> None:
        """
        Ensures moved bars land on the same grid line for aligned starts.
        """

        from src.timeline_widget import ROW_HEIGHT, ROW_SPACING

        first = _make_annotation(start_ms=1000, end_ms=2500)
        second = _make_annotation(start_ms=2200, end_ms=3700)
        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 90)
        widget.set_duration(10_000)
        widget.set_annotations([first, second])
        _show_full_timeline(widget)

        # Second row body drag: move so the unsnapped start is near 1000ms.
        row_y = RULER_HEIGHT + ROW_SPACING + ROW_HEIGHT + ROW_SPACING + (ROW_HEIGHT / 2.0)
        press_x = float(widget._ms_to_x(2950))  # pylint: disable=protected-access
        move_x = float(widget._ms_to_x(1750))  # pylint: disable=protected-access
        widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, press_x, row_y))
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, move_x, row_y))
        widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, move_x, row_y))

        self.assertEqual(second.start_ms, first.start_ms)
        self.assertEqual(second.end_ms - second.start_ms, 1500)


if __name__ == "__main__":
    unittest.main()
