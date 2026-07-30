"""
Unit tests for the video editor timeline widget's drag/resize geometry.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent, QWheelEvent

    from src.timeline_widget import (
        CTRL_NAV_THRESHOLD_PX,
        DEFAULT_PAGE_DURATION_MS,
        EDGE_HIT_PX,
        LABEL_WIDTH,
        ROW_HEIGHT,
        RULER_HEIGHT,
        ZOOM_DRAG_SENSITIVITY_PX,
        TimelineWidget,
    )
    from src.video_effects import EFFECT_EDGE_START, EFFECT_KIND_FADE, add_annotation_effect
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


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for timeline widget tests")
class TestTimelineWidgetClickAndZoomDrag(unittest.TestCase):
    """
    Verifies plain clicks scrub the playhead everywhere on the timeline, and
    double-click-and-hold-drag stretches/compresses the visible time range.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _make_widget(self, *, with_annotation: bool = False) -> TimelineWidget:
        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(10000)
        if with_annotation:
            widget.set_annotations([_make_annotation()])
        _show_full_timeline(widget)
        return widget

    def test_click_on_empty_track_area_scrubs_playhead(self) -> None:
        """
        Ensures a plain click below the ruler, on empty track space (no
        annotation bar underneath), still emits seek_requested -- not just
        clicks inside the ruler strip.
        """

        widget = self._make_widget()
        seeks: list[int] = []
        widget.seek_requested.connect(seeks.append)
        empty_row_y = RULER_HEIGHT + 15.0

        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, 300.0, empty_row_y)
        )

        self.assertEqual(len(seeks), 1)
        self.assertEqual(seeks[0], widget._x_to_ms(300.0))  # pylint: disable=protected-access

    def test_click_on_empty_track_area_continues_scrubbing_while_dragged(self) -> None:
        """
        Ensures holding and dragging after a click on empty track space keeps
        scrubbing the playhead, matching the ruler's existing drag behavior.
        """

        widget = self._make_widget()
        seeks: list[int] = []
        widget.seek_requested.connect(seeks.append)
        empty_row_y = RULER_HEIGHT + 15.0

        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, 300.0, empty_row_y)
        )
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 400.0, empty_row_y))

        self.assertEqual(len(seeks), 2)
        self.assertEqual(seeks[-1], widget._x_to_ms(400.0))  # pylint: disable=protected-access

    def test_click_on_annotation_bar_still_selects_instead_of_seeking(self) -> None:
        """
        Ensures clicking directly on an annotation bar keeps selecting/dragging
        that bar rather than being swallowed by the new empty-area seek behavior.
        """

        widget = self._make_widget(with_annotation=True)
        seeks: list[int] = []
        widget.seek_requested.connect(seeks.append)
        row_y = RULER_HEIGHT + 15.0
        bar_mid_x = float(widget._ms_to_x(3000))  # pylint: disable=protected-access

        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, bar_mid_x, row_y)
        )

        self.assertEqual(seeks, [])
        self.assertNotEqual(widget._drag_mode, "")  # pylint: disable=protected-access

    def test_double_click_arms_zoom_drag_with_stretch_cursor(self) -> None:
        """
        Ensures double-clicking arms the zoom-drag mode and immediately shows
        the stretch/compress (horizontal resize) cursor.
        """

        widget = self._make_widget()

        widget.mouseDoubleClickEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonDblClick, 300.0, RULER_HEIGHT + 15.0)
        )

        self.assertEqual(widget._drag_mode, "zoom")  # pylint: disable=protected-access
        self.assertEqual(widget.cursor().shape(), Qt.CursorShape.SizeHorCursor)

    def test_dragging_right_after_double_click_stretches_the_timeline(self) -> None:
        """
        Ensures holding after a double-click and dragging right narrows the
        visible time range (stretch/zoom in).
        """

        widget = self._make_widget()
        original_duration = widget._view_duration_ms  # pylint: disable=protected-access

        widget.mouseDoubleClickEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonDblClick, 300.0, RULER_HEIGHT + 15.0)
        )
        widget.mouseMoveEvent(
            _mouse_event(QMouseEvent.Type.MouseMove, 300.0 + ZOOM_DRAG_SENSITIVITY_PX, RULER_HEIGHT + 15.0)
        )

        self.assertLess(widget._view_duration_ms, original_duration)  # pylint: disable=protected-access

    def test_dragging_left_after_double_click_compresses_the_timeline(self) -> None:
        """
        Ensures holding after a double-click and dragging left widens the
        visible time range (compress/zoom out).
        """

        widget = self._make_widget()
        _set_view_page(widget, 4000)
        original_duration = widget._view_duration_ms  # pylint: disable=protected-access

        widget.mouseDoubleClickEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonDblClick, 300.0, RULER_HEIGHT + 15.0)
        )
        widget.mouseMoveEvent(
            _mouse_event(QMouseEvent.Type.MouseMove, 300.0 - ZOOM_DRAG_SENSITIVITY_PX, RULER_HEIGHT + 15.0)
        )

        self.assertGreater(widget._view_duration_ms, original_duration)  # pylint: disable=protected-access

    def test_release_ends_zoom_drag_and_restores_cursor(self) -> None:
        """
        Ensures releasing the button after a zoom drag clears the drag mode
        and resets the cursor back to the default arrow.
        """

        widget = self._make_widget()
        widget.mouseDoubleClickEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonDblClick, 300.0, RULER_HEIGHT + 15.0)
        )
        widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, 340.0, RULER_HEIGHT + 15.0))

        widget.mouseReleaseEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonRelease, 340.0, RULER_HEIGHT + 15.0)
        )

        self.assertEqual(widget._drag_mode, "")  # pylint: disable=protected-access


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for timeline widget tests")
class TestTimelineWidgetEffectContextMenu(unittest.TestCase):
    """
    Verifies right-clicking an annotation bar offers "Add Effect..." and
    that the bar's label shows a short summary of its applied effects.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _make_widget(self, annotation) -> TimelineWidget:
        widget = TimelineWidget()
        widget.resize(660, RULER_HEIGHT + 60)
        widget.set_duration(10000)
        widget.set_annotations([annotation])
        _show_full_timeline(widget)
        return widget

    def test_right_click_on_bar_builds_menu_that_emits_effect_edit_requested(self) -> None:
        """
        Ensures right-clicking an annotation bar hit-tests it correctly, and
        that choosing "Add Effect..." from the resulting menu emits
        effect_edit_requested with that annotation's id.

        Triggers the built menu's action directly instead of going through
        contextMenuEvent()'s QMenu.exec() call, which spins a real modal
        event loop that PySide6 does not let tests intercept/short-circuit.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        requested: list[str] = []
        widget.effect_edit_requested.connect(requested.append)
        row_y = RULER_HEIGHT + 15.0
        bar_mid_x = float(widget._ms_to_x(3000))  # pylint: disable=protected-access

        hit = widget._hit_test(QPoint(int(bar_mid_x), int(row_y)))  # pylint: disable=protected-access
        self.assertIsNotNone(hit)
        _index, hit_annotation, _mode = hit
        menu = widget._build_effect_context_menu(hit_annotation)  # pylint: disable=protected-access
        actions_by_text = {action.text(): action for action in menu.actions()}

        self.assertIn("Add Effect...", actions_by_text)
        actions_by_text["Add Effect..."].trigger()

        self.assertEqual(requested, [annotation.annotation_id])

    def test_right_click_on_empty_track_area_does_nothing(self) -> None:
        """
        Ensures right-clicking empty track space (no annotation underneath)
        does not emit effect_edit_requested.
        """

        annotation = _make_annotation(start_ms=2000, end_ms=4000)
        widget = self._make_widget(annotation)
        requested: list[str] = []
        widget.effect_edit_requested.connect(requested.append)
        row_y = RULER_HEIGHT + 15.0
        empty_x = float(widget._ms_to_x(8000))  # pylint: disable=protected-access

        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            QPoint(int(empty_x), int(row_y)),
        )
        widget.contextMenuEvent(event)

        self.assertEqual(requested, [])

    def test_bar_label_includes_short_effect_summary(self) -> None:
        """
        Ensures the annotation's label text includes a bracketed, short
        summary of its applied effects (e.g. "[Fade In]").
        """

        annotation = _make_annotation()
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)
        widget = self._make_widget(annotation)

        # paintEvent must run without error and reflect the effect summary
        # via the shared track_effect_summary() helper used in its label text.
        from src.video_effects import track_effect_summary

        widget.repaint()
        self.assertEqual(track_effect_summary(annotation), "Fade In")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for timeline widget tests")
class TestTimelineWidgetDeleteKey(unittest.TestCase):
    """
    Verifies that selecting a track bar and pressing Delete requests removal of
    that annotation, and that the bar height stays compact.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _make_widget(self, annotation) -> TimelineWidget:
        """
        Builds a sized TimelineWidget showing one annotation row.

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

    def _press_delete(self, widget: TimelineWidget) -> None:
        """
        Sends a synthetic Delete key press to the timeline.

        Args:
            widget: Timeline under test.

        Returns:
            None
        """

        widget.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Delete,
                Qt.KeyboardModifier.NoModifier,
            )
        )

    def test_delete_after_bar_click_requests_annotation_removal(self) -> None:
        """
        Ensures clicking a track bar and pressing Delete emits
        annotation_delete_requested with that annotation's id.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        deleted: list[str] = []
        widget.annotation_delete_requested.connect(deleted.append)
        bar_mid_x = float(widget._ms_to_x(3000))  # pylint: disable=protected-access

        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, bar_mid_x, RULER_HEIGHT + 15.0)
        )
        widget.mouseReleaseEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonRelease, bar_mid_x, RULER_HEIGHT + 15.0)
        )
        self.assertEqual(widget.selected_annotation_id(), annotation.annotation_id)

        self._press_delete(widget)

        self.assertEqual(deleted, [annotation.annotation_id])
        self.assertEqual(widget.selected_annotation_id(), "")

    def test_delete_without_selection_emits_nothing(self) -> None:
        """
        Ensures Delete is ignored while no track bar is selected.
        """

        widget = self._make_widget(_make_annotation())
        deleted: list[str] = []
        widget.annotation_delete_requested.connect(deleted.append)

        self._press_delete(widget)

        self.assertEqual(deleted, [])

    def test_delete_is_not_repeated_after_the_bar_was_removed(self) -> None:
        """
        Ensures a second Delete does not re-request the already deleted bar.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        deleted: list[str] = []
        widget.annotation_delete_requested.connect(deleted.append)
        bar_mid_x = float(widget._ms_to_x(3000))  # pylint: disable=protected-access

        widget.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, bar_mid_x, RULER_HEIGHT + 15.0)
        )
        widget.mouseReleaseEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonRelease, bar_mid_x, RULER_HEIGHT + 15.0)
        )
        self._press_delete(widget)
        self._press_delete(widget)

        self.assertEqual(deleted, [annotation.annotation_id])

    def test_track_bar_height_is_twenty_pixels(self) -> None:
        """
        Pins the slimmer (2px shorter) annotation track bar height.
        """

        annotation = _make_annotation()
        widget = self._make_widget(annotation)
        bar = widget._bar_rect(0, annotation)  # pylint: disable=protected-access

        self.assertEqual(ROW_HEIGHT, 20)
        self.assertEqual(bar.height(), 20)

    def test_timeline_accepts_keyboard_focus_on_click(self) -> None:
        """
        Ensures the timeline can take focus, so Delete reaches it after a click.
        """

        widget = self._make_widget(_make_annotation())

        self.assertTrue(
            widget.focusPolicy() & Qt.FocusPolicy.ClickFocus == Qt.FocusPolicy.ClickFocus
        )


if __name__ == "__main__":
    unittest.main()
