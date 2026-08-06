"""
Regression tests for the window-capture highlight frame.

The overlay draws a green frame around the window that would be captured. On X11
the overlay is click-through, but X11 still lists it in ``_NET_CLIENT_LIST_STACKING``
and it covers the whole virtual desktop -- so it won every hit-test, the highlight
was drawn around the entire desktop, and the frame effectively disappeared onto
the outermost screen edge. These tests pin both halves down: the hit-test must
skip Snappix's own windows, and the overlay must actually paint the frame.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QImage, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

HIGHLIGHT_COLOR = (46, 204, 113)


def _desktop_pixmap(width: int, height: int) -> QPixmap:
    """
    Builds a neutral desktop screenshot.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Filled pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(40, 44, 52))
    return QPixmap.fromImage(image)


def _highlight_bounds(image: QImage) -> QRect:
    """
    Returns the bounding box of highlight-colored pixels in a rendered overlay.

    Args:
        image: Rendered overlay image.

    Returns:
        QRect: Bounding box, null when the highlight color is absent.
    """

    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if (
                abs(color.red() - HIGHLIGHT_COLOR[0]) < 30
                and abs(color.green() - HIGHLIGHT_COLOR[1]) < 30
                and abs(color.blue() - HIGHLIGHT_COLOR[2]) < 30
            ):
                xs.append(x)
                ys.append(y)
    if not xs:
        return QRect()
    return QRect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for window highlight tests")
class TestX11HitTestSkipsOwnWindows(unittest.TestCase):
    """
    Verifies the X11 hit-test never returns one of Snappix's own windows.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for QRect/QPoint use.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Clears the window owner cache between tests.
        """

        import src.capture as capture

        capture._X11_WINDOW_PID_CACHE.clear()

    def _hit_test(self, stacking, geometries, pids, point=QPoint(500, 500), exclude=frozenset()):
        """
        Runs the hit-test against a synthetic window stack.

        Args:
            stacking: Window ids bottom to top.
            geometries: Mapping of window id to geometry.
            pids: Mapping of window id to owning process id.
            point: Point to hit-test.
            exclude: Explicitly excluded ids.

        Returns:
            str: Detected window id.
        """

        import src.capture as capture

        with patch.object(capture, "_x11_stacking_order", return_value=stacking), patch.object(
            capture, "_window_geometry_from_id", side_effect=lambda wid: geometries[wid]
        ), patch.object(capture, "_x11_window_pid", side_effect=lambda wid: pids.get(wid, 4321)):
            return capture._x11_window_id_at_point(point, exclude)

    def test_own_overlay_on_top_is_skipped(self) -> None:
        """
        Ensures the reported bug is gone: the full-desktop overlay on top no
        longer shadows the window the user is pointing at.
        """

        detected = self._hit_test(
            stacking=["target", "own_overlay"],
            geometries={
                "target": QRect(0, 32, 2560, 1408),
                "own_overlay": QRect(0, 0, 5120, 1440),
            },
            pids={"target": 4321, "own_overlay": os.getpid()},
        )
        self.assertEqual(detected, "target")

    def test_topmost_foreign_window_still_wins(self) -> None:
        """
        Ensures normal stacking is untouched: the topmost window under the point
        is returned.
        """

        detected = self._hit_test(
            stacking=["below", "above"],
            geometries={
                "below": QRect(0, 0, 2560, 1440),
                "above": QRect(400, 400, 800, 600),
            },
            pids={"below": 1111, "above": 2222},
        )
        self.assertEqual(detected, "above")

    def test_explicitly_excluded_id_is_skipped(self) -> None:
        """
        Ensures the Windows-style id exclusion is honored on X11 too.
        """

        detected = self._hit_test(
            stacking=["target", "overlay"],
            geometries={
                "target": QRect(0, 0, 2560, 1440),
                "overlay": QRect(0, 0, 5120, 1440),
            },
            pids={"target": 1111, "overlay": 2222},
            exclude=frozenset({"overlay"}),
        )
        self.assertEqual(detected, "target")

    def test_windows_outside_the_point_are_ignored(self) -> None:
        """
        Ensures geometry still decides which window is under the cursor.
        """

        detected = self._hit_test(
            stacking=["left", "right"],
            geometries={
                "left": QRect(0, 0, 400, 400),
                "right": QRect(2000, 0, 400, 400),
            },
            pids={"left": 1111, "right": 2222},
            point=QPoint(100, 100),
        )
        self.assertEqual(detected, "left")

    def test_only_own_windows_yields_nothing(self) -> None:
        """
        Ensures an all-Snappix stack reports no target instead of returning the
        overlay itself.
        """

        detected = self._hit_test(
            stacking=["own_a", "own_b"],
            geometries={
                "own_a": QRect(0, 0, 5120, 1440),
                "own_b": QRect(0, 0, 5120, 1440),
            },
            pids={"own_a": os.getpid(), "own_b": os.getpid()},
        )
        self.assertEqual(detected, "")

    def test_window_ids_normalize_from_int_decimal_and_hex(self) -> None:
        """
        Ensures caller-supplied ids match the decimal form X11 reports.
        """

        from src.capture import _normalize_window_ids

        self.assertEqual(
            _normalize_window_ids([130023444, "130023445", "0x7C0016", "nonsense", None]),
            frozenset({"130023444", "130023445", str(0x7C0016)}),
        )

    def test_owner_cache_is_bounded(self) -> None:
        """
        Ensures the owner cache cannot grow without limit, since X recycles ids.
        """

        import src.capture as capture

        capture._X11_WINDOW_PID_CACHE.update(
            {str(index): 1 for index in range(capture._X11_WINDOW_PID_CACHE_LIMIT + 5)}
        )
        with patch.object(capture.subprocess, "run") as run:
            run.return_value.stdout = "_NET_WM_PID(CARDINAL) = 4242\n"
            pid = capture._x11_window_pid("999999")
        self.assertEqual(pid, 4242)
        self.assertLessEqual(
            len(capture._X11_WINDOW_PID_CACHE), capture._X11_WINDOW_PID_CACHE_LIMIT + 1
        )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for window highlight tests")
class TestWindowCaptureOverlayFrame(unittest.TestCase):
    """
    Verifies the overlay paints a visible frame around the target window.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget rendering.
        """

        cls._app = ensure_qapp()

    def _overlay(self):
        """
        Builds an overlay over a synthetic 800x600 desktop.

        Returns:
            WindowCaptureOverlay: Overlay instance.
        """

        from src.capture import WindowCaptureOverlay

        geometry = QRect(0, 0, 800, 600)
        overlay = WindowCaptureOverlay(_desktop_pixmap(800, 600), geometry)
        self.addCleanup(overlay.close)
        return overlay

    def test_frame_is_drawn_outside_the_captured_area(self) -> None:
        """
        Ensures the frame surrounds the target window without covering it: the
        highlight must not sit on pixels the capture will contain.
        """

        overlay = self._overlay()
        target = QRect(200, 150, 300, 200)
        overlay._hover_rect = target
        overlay._hover_label = "X:200 Y:150 W:300 H:200"
        image = overlay.grab().toImage()
        bounds = _highlight_bounds(image)

        self.assertFalse(bounds.isNull(), "highlight frame was not painted")
        self.assertTrue(
            bounds.contains(target),
            f"frame {bounds} does not surround target {target}",
        )
        for y in range(target.y(), target.bottom() + 1):
            for x in range(target.x(), target.right() + 1):
                color = image.pixelColor(x, y)
                is_highlight = (
                    abs(color.red() - HIGHLIGHT_COLOR[0]) < 30
                    and abs(color.green() - HIGHLIGHT_COLOR[1]) < 30
                    and abs(color.blue() - HIGHLIGHT_COLOR[2]) < 30
                )
                self.assertFalse(
                    is_highlight, f"frame pixel at {x},{y} lies inside the capture area"
                )

    def test_frame_stays_visible_for_a_window_flush_against_the_edge(self) -> None:
        """
        Ensures a maximized window still gets a visible frame: there is no room
        outside it, so the frame is pulled back on screen rather than clipped away.
        """

        overlay = self._overlay()
        overlay._hover_rect = QRect(0, 0, 800, 600)
        bounds = _highlight_bounds(overlay.grab().toImage())
        self.assertFalse(bounds.isNull(), "frame vanished for an edge-to-edge window")

    def test_label_is_placed_outside_the_captured_area(self) -> None:
        """
        Ensures the geometry label does not cover the target either, on both
        sides: above when there is room, below when there is not.
        """

        overlay = self._overlay()
        label_height = 24
        with_room = overlay._label_y_outside(QRect(100, 200, 300, 200), label_height)
        self.assertLessEqual(with_room + label_height, 200)

        at_top = overlay._label_y_outside(QRect(100, 0, 300, 200), label_height)
        self.assertGreaterEqual(at_top, 200)
        self.assertLessEqual(at_top + label_height, overlay.height())

    def test_frame_is_absent_without_a_target(self) -> None:
        """
        Ensures nothing is drawn before a window is detected.
        """

        overlay = self._overlay()
        overlay._hover_rect = QRect()
        self.assertTrue(_highlight_bounds(overlay.grab().toImage()).isNull())

    def test_hover_poll_uses_the_detected_window(self) -> None:
        """
        Ensures the polled geometry reaches the frame, and that a repaint is
        requested -- a silently updated rectangle would never become visible.
        """

        import src.capture as capture

        overlay = self._overlay()
        with patch.object(
            capture, "detect_window_geometry", return_value=QRect(100, 100, 200, 200)
        ), patch.object(overlay, "update") as update:
            overlay._update_hover_from_cursor()

        self.assertEqual(overlay._hover_rect, QRect(100, 100, 200, 200))
        self.assertIn("W:200", overlay._hover_label)
        update.assert_called_once()

    def test_hover_poll_excludes_the_overlay_itself(self) -> None:
        """
        Ensures the overlay passes its own window id into the hit-test, so a
        platform that honors id exclusion cannot highlight the overlay.
        """

        import src.capture as capture

        overlay = self._overlay()
        overlay.show()
        self._app.processEvents()
        with patch.object(
            capture, "detect_window_geometry", return_value=QRect(10, 10, 50, 50)
        ) as detect:
            overlay._update_hover_from_cursor()

        excluded = detect.call_args.kwargs["exclude_hwnds"]
        self.assertTrue(excluded)
        self.assertIn(int(overlay.winId()), excluded)


if __name__ == "__main__":
    unittest.main()
