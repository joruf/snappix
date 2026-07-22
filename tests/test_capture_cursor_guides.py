"""
Unit tests for capture overlay cursor guide helpers.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

    from src.capture import RegionCaptureOverlay, draw_cursor_edge_guides
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for capture overlay tests")
class TestCaptureCursorGuides(unittest.TestCase):
    """
    Verifies Capture Area cursor edge guides.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_draw_cursor_edge_guides_paints_without_error(self) -> None:
        """
        Ensures guide drawing runs for an in-bounds cursor point.
        """

        image = QImage(80, 60, QImage.Format.Format_ARGB32)
        image.fill(QColor(30, 30, 30))
        painter = QPainter(image)
        draw_cursor_edge_guides(painter, QRect(0, 0, 80, 60), QPoint(40, 30))
        painter.end()
        # Center and arms should not stay the original fill color everywhere.
        self.assertNotEqual(image.pixelColor(40, 30), QColor(30, 30, 30))

    def test_region_overlay_tracks_cursor_before_drag(self) -> None:
        """
        Ensures Capture Area updates cursor guides while hovering.
        """

        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF

        screenshot = QPixmap(100, 80)
        screenshot.fill(QColor(40, 40, 40))
        overlay = RegionCaptureOverlay(screenshot, QRect(0, 0, 100, 80))
        self.assertTrue(overlay.hasMouseTracking())
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(25.0, 35.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(event)
        self.assertEqual(overlay._cursor_point, QPoint(25, 35))  # pylint: disable=protected-access
        overlay.close()


if __name__ == "__main__":
    unittest.main()
