"""
Tests for locating the window under a screen coordinate.

The regression these guard against: the X11 path asked
``xdotool getmouselocation``, which can only ever answer for the real pointer.
The ``global_pos`` argument was accepted, documented, and then ignored, so every
point returned the same window -- and once resolved upward, usually the desktop.
On screen that reads as "the window highlight is missing", because a highlight
frame around the whole screen looks like no highlight at all.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect

from src import capture
from tests.qt_test_utils import ensure_qapp

# Two windows side by side, plus a full-screen desktop underneath them.
_DESKTOP = ("100", QRect(0, 0, 3840, 2160))
_LEFT = ("200", QRect(0, 0, 1920, 1080))
_RIGHT = ("300", QRect(1920, 0, 1920, 1080))
_GEOMETRY = dict([_DESKTOP, _LEFT, _RIGHT])


def _fake_geometry(window_id: str) -> QRect:
    """
    Returns the canned geometry for one test window id.

    Args:
        window_id: Window id to look up.

    Returns:
        QRect: Geometry, or a null rect for unknown ids.
    """

    return _GEOMETRY.get(str(window_id), QRect())


class PointBasedDetectionTests(unittest.TestCase):
    """
    Class PointBasedDetectionTests

    Covers the detection actually honouring the coordinate it is handed.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()

    def _detect(self, x: int, y: int) -> str:
        """
        Runs point detection against the canned window layout.

        Args:
            x: Global x coordinate.
            y: Global y coordinate.

        Returns:
            str: Detected window id.
        """

        # Stacking order is bottom-to-top: desktop first, windows above it.
        with patch.object(capture, "_x11_stacking_order", return_value=["100", "200", "300"]), \
             patch.object(capture, "_window_geometry_from_id", side_effect=_fake_geometry):
            return capture._x11_window_id_at_point(QPoint(x, y))

    def test_different_points_resolve_to_different_windows(self) -> None:
        """
        The whole defect in one assertion: two points far apart must not report
        the same window.

        Returns:
            None
        """

        left = self._detect(500, 500)
        right = self._detect(2500, 500)
        self.assertNotEqual(left, right)

    def test_point_on_the_left_window(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(self._detect(500, 500), "200")

    def test_point_on_the_right_window(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(self._detect(2500, 500), "300")

    def test_topmost_window_wins_over_the_desktop_below_it(self) -> None:
        """
        The desktop covers every point, so a bottom-up walk would always return
        it -- which is exactly the full-screen rectangle that looked like a
        missing highlight.

        Returns:
            None
        """

        self.assertNotEqual(self._detect(500, 500), "100")

    def test_point_covered_only_by_the_desktop_returns_it(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(self._detect(500, 1500), "100")

    def test_point_outside_every_window_returns_nothing(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(self._detect(5000, 5000), "")

    def test_windows_without_geometry_are_skipped(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(capture, "_x11_stacking_order", return_value=["999", "200"]), \
             patch.object(capture, "_window_geometry_from_id", side_effect=_fake_geometry):
            self.assertEqual(capture._x11_window_id_at_point(QPoint(500, 500)), "200")

    def test_empty_stacking_order_returns_nothing(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(capture, "_x11_stacking_order", return_value=[]):
            self.assertEqual(capture._x11_window_id_at_point(QPoint(500, 500)), "")


class StackingOrderTests(unittest.TestCase):
    """
    Class StackingOrderTests

    Covers parsing the window manager's stacking hint.
    """

    def test_hex_ids_are_parsed_to_decimal(self) -> None:
        """
        Returns:
            None
        """

        output = "_NET_CLIENT_LIST_STACKING(WINDOW): window id # 0x2c03484, 0x7e00012\n"

        class Result:
            """Stand-in for a completed subprocess."""

            stdout = output

        with patch("subprocess.run", return_value=Result()):
            self.assertEqual(capture._x11_stacking_order(), [str(0x2C03484), str(0x7E00012)])

    def test_missing_xprop_is_reported_as_no_windows(self) -> None:
        """
        A window manager without the hint must not raise; the caller falls back.

        Returns:
            None
        """

        with patch("subprocess.run", side_effect=OSError("no xprop")):
            self.assertEqual(capture._x11_stacking_order(), [])


class DetectWindowAtPointTests(unittest.TestCase):
    """
    Class DetectWindowAtPointTests

    Covers the public entry point preferring point detection over the pointer.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()

    def test_pointer_lookup_is_not_used_when_the_point_resolves(self) -> None:
        """
        Falling through to the pointer would reintroduce the defect for any
        caller asking about somewhere other than the cursor.

        Returns:
            None
        """

        with patch.object(capture, "is_wayland_session", return_value=False), \
             patch.object(capture, "has_xdotool_and_xwininfo", return_value=True), \
             patch.object(capture, "_x11_window_id_at_point", return_value="200"), \
             patch.object(capture, "_window_geometry_from_id", side_effect=_fake_geometry), \
             patch("subprocess.run", side_effect=AssertionError("pointer lookup must not run")):
            window_id, geometry = capture.detect_window_at_point(QPoint(500, 500))

        self.assertEqual(window_id, "200")
        self.assertEqual(geometry, _LEFT[1])


if __name__ == "__main__":
    unittest.main()
