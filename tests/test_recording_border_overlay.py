"""
Unit tests for the blinking recording-border overlay.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPoint, QRect

    from src.capture import (
        RECORDING_BORDER_THICKNESS,
        RECORDING_TIMER_BAND_HEIGHT,
        RecordingBorderOverlay,
    )
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for recording border overlay tests")
class TestRecordingBorderOverlay(unittest.TestCase):
    """
    Verifies the overlay is positioned entirely outside the recorded pixels.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget creation.
        """

        ensure_qapp()

    def test_geometry_surrounds_capture_rect_without_overlapping_it(self) -> None:
        """
        Ensures the overlay's outer geometry is exactly the capture rect
        expanded by the border thickness on every side, so the recorded
        pixels themselves stay untouched by the drawn border.
        """

        capture_rect = QRect(100, 200, 640, 480)
        overlay = RecordingBorderOverlay(capture_rect)
        try:
            geometry = overlay.geometry()
            self.assertEqual(geometry.x(), capture_rect.x() - RECORDING_BORDER_THICKNESS)
            self.assertEqual(
                geometry.y(),
                capture_rect.y() - RECORDING_BORDER_THICKNESS - RECORDING_TIMER_BAND_HEIGHT,
            )
            self.assertEqual(
                geometry.width(), capture_rect.width() + 2 * RECORDING_BORDER_THICKNESS
            )
            self.assertEqual(
                geometry.height(),
                capture_rect.height()
                + 2 * RECORDING_BORDER_THICKNESS
                + RECORDING_TIMER_BAND_HEIGHT,
            )
        finally:
            overlay.close()

    def test_set_paused_stops_blinking(self) -> None:
        """
        Ensures pausing freezes the border in its visible phase instead of blinking.
        """

        overlay = RecordingBorderOverlay(QRect(0, 0, 100, 100))
        try:
            overlay.set_paused(True)
            self.assertTrue(overlay._paused)  # pylint: disable=protected-access
            overlay._on_blink_tick()  # pylint: disable=protected-access
            # A paused overlay should not toggle its blink phase on tick.
            self.assertTrue(overlay._blink_on)  # pylint: disable=protected-access

            overlay.set_paused(False)
            overlay._on_blink_tick()  # pylint: disable=protected-access
            self.assertFalse(overlay._blink_on)  # pylint: disable=protected-access
        finally:
            overlay.close()

    def test_set_paused_freezes_elapsed_time(self) -> None:
        """
        Ensures pausing stops the elapsed-time counter until recording resumes.
        """

        overlay = RecordingBorderOverlay(QRect(0, 0, 100, 100))
        try:
            overlay._accumulated_ms = 5000  # pylint: disable=protected-access
            overlay._recording_active = False  # pylint: disable=protected-access
            overlay.set_paused(True)
            self.assertEqual(overlay._format_elapsed(), "0:05")

            overlay.set_paused(False)
            overlay._accumulated_ms = 5000  # pylint: disable=protected-access
            overlay._recording_active = False  # pylint: disable=protected-access
            self.assertEqual(overlay._format_elapsed(), "0:05")
        finally:
            overlay.close()

    def test_format_elapsed_shows_minutes_and_seconds(self) -> None:
        """
        Ensures elapsed time is formatted as minutes and zero-padded seconds.
        """

        overlay = RecordingBorderOverlay(QRect(0, 0, 100, 100))
        try:
            overlay._accumulated_ms = 125000  # pylint: disable=protected-access
            overlay._recording_active = False  # pylint: disable=protected-access
            self.assertEqual(overlay._format_elapsed(), "2:05")
        finally:
            overlay.close()

    def test_timer_sits_above_capture_border(self) -> None:
        """
        Ensures the elapsed-time pill is drawn above the red border, not inside the capture area.
        """

        overlay = RecordingBorderOverlay(QRect(0, 0, 100, 100))
        try:
            pill_rect = overlay._timer_pill_rect()  # pylint: disable=protected-access
            self.assertLess(pill_rect.bottom(), float(RECORDING_TIMER_BAND_HEIGHT))
        finally:
            overlay.close()

    def test_set_capture_rect_moves_overlay_without_changing_size(self) -> None:
        """
        Ensures the overlay can be repositioned while preserving capture dimensions.
        """

        overlay = RecordingBorderOverlay(QRect(100, 100, 640, 480))
        try:
            overlay.set_capture_rect(QRect(300, 220, 640, 480))
            self.assertEqual(overlay.capture_rect().size(), QRect(0, 0, 640, 480).size())
            self.assertNotEqual(overlay.capture_rect().topLeft(), QPoint(100, 100))
        finally:
            overlay.close()


if __name__ == "__main__":
    unittest.main()
