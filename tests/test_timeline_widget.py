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
        DEFAULT_VISIBLE_PAGES,
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
        self.assertEqual(annotation.end_ms, 5800)

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

    def test_default_view_shows_one_page_of_duration(self) -> None:
        """
        Ensures a 100s video initially shows one fifth of its duration.
        """

        widget = self._make_widget()
        self.assertEqual(widget._view_start_ms, 0)  # pylint: disable=protected-access
        self.assertEqual(
            widget._view_duration_ms,  # pylint: disable=protected-access
            10000 // DEFAULT_VISIBLE_PAGES,
        )

    def test_pan_buttons_jump_full_pages(self) -> None:
        """
        Ensures arrow buttons jump from 0-20s to 20-40s and back.
        """

        widget = self._make_widget()
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


if __name__ == "__main__":
    unittest.main()
