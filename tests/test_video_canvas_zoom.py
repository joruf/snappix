"""
Unit tests for VideoCanvas zoom controls.
"""

from __future__ import annotations

import unittest

try:
    from src.video_canvas import VideoCanvas
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video canvas tests")
class TestVideoCanvasZoom(unittest.TestCase):
    """
    Verifies zoom_in/zoom_out/set_zoom_factor/reset_zoom behave like the image editor's canvas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget creation.
        """

        ensure_qapp()

    def test_zoom_in_increases_zoom_factor(self) -> None:
        """
        Ensures zoom_in multiplies the tracked zoom factor by the zoom step.
        """

        canvas = VideoCanvas()
        canvas.zoom_in()
        self.assertAlmostEqual(canvas._zoom_factor, VideoCanvas.ZOOM_STEP)

    def test_zoom_out_decreases_zoom_factor(self) -> None:
        """
        Ensures zoom_out divides the tracked zoom factor by the zoom step.
        """

        canvas = VideoCanvas()
        canvas.zoom_out()
        self.assertAlmostEqual(canvas._zoom_factor, 1.0 / VideoCanvas.ZOOM_STEP)

    def test_zoom_in_stops_at_max(self) -> None:
        """
        Ensures repeated zoom_in calls never exceed ZOOM_MAX.
        """

        canvas = VideoCanvas()
        for _ in range(200):
            canvas.zoom_in()
        self.assertLessEqual(canvas._zoom_factor, VideoCanvas.ZOOM_MAX)

    def test_zoom_out_stops_at_min(self) -> None:
        """
        Ensures repeated zoom_out calls never go below ZOOM_MIN.
        """

        canvas = VideoCanvas()
        for _ in range(200):
            canvas.zoom_out()
        self.assertGreaterEqual(canvas._zoom_factor, VideoCanvas.ZOOM_MIN)

    def test_set_zoom_factor_applies_absolute_value_and_emits_signal(self) -> None:
        """
        Ensures set_zoom_factor sets the exact bounded value and emits zoom_changed.
        """

        canvas = VideoCanvas()
        received: list[float] = []
        canvas.zoom_changed.connect(received.append)

        canvas.set_zoom_factor(2.5)

        self.assertAlmostEqual(canvas._zoom_factor, 2.5)
        self.assertAlmostEqual(received[-1], 2.5)

    def test_set_zoom_factor_clamps_out_of_range_values(self) -> None:
        """
        Ensures set_zoom_factor clamps values outside [ZOOM_MIN, ZOOM_MAX].
        """

        canvas = VideoCanvas()
        canvas.set_zoom_factor(50.0)
        self.assertAlmostEqual(canvas._zoom_factor, VideoCanvas.ZOOM_MAX)

        canvas.set_zoom_factor(0.001)
        self.assertAlmostEqual(canvas._zoom_factor, VideoCanvas.ZOOM_MIN)

    def test_reset_zoom_marks_initial_view_pending(self) -> None:
        """
        Ensures reset_zoom re-arms the auto-fit-on-resize behavior.
        """

        canvas = VideoCanvas()
        canvas.zoom_in()
        self.assertFalse(canvas._initial_view_pending)

        canvas.reset_zoom()

        self.assertTrue(canvas._initial_view_pending)


if __name__ == "__main__":
    unittest.main()
