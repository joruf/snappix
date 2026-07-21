"""
Unit tests for crop selection geometry behavior.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF, QRectF

    from src.crop_item import CropSelectionItem
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for crop GUI tests")
class TestCropSelectionItem(unittest.TestCase):
    """
    Verifies crop handle hit-testing and resize constraints.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics items.
        """

        cls._app = ensure_qapp()

    def test_scene_rect_reflects_position_and_size(self) -> None:
        """
        Ensures scene_rect returns correct scene coordinates.
        """

        item = CropSelectionItem(QRectF(10.0, 20.0, 100.0, 80.0))
        scene_rect = item.scene_rect()
        self.assertEqual(scene_rect.x(), 10.0)
        self.assertEqual(scene_rect.y(), 20.0)
        self.assertEqual(scene_rect.width(), 100.0)
        self.assertEqual(scene_rect.height(), 80.0)

    def test_border_handle_detection_returns_expected_handle(self) -> None:
        """
        Ensures border-near positions map to the correct handle.
        """

        item = CropSelectionItem(QRectF(0.0, 0.0, 100.0, 80.0))
        handle = item._border_handle_at(QPointF(50.0, 1.0))  # pylint: disable=protected-access
        self.assertEqual(handle, "top")
        self.assertIsNone(item._border_handle_at(QPointF(50.0, 40.0)))  # pylint: disable=protected-access

    def test_resize_enforces_min_size(self) -> None:
        """
        Ensures resizing cannot shrink below minimum dimensions.
        """

        item = CropSelectionItem(QRectF(0.0, 0.0, 40.0, 30.0))
        item._resize_from_handle("left", QPointF(38.0, 0.0))  # pylint: disable=protected-access
        resized = item.scene_rect()
        self.assertGreaterEqual(resized.width(), item.MIN_SIZE)

        item._resize_from_handle("top", QPointF(0.0, 28.0))  # pylint: disable=protected-access
        resized_again = item.scene_rect()
        self.assertGreaterEqual(resized_again.height(), item.MIN_SIZE)

    def test_shift_resize_preserves_starting_aspect_ratio(self) -> None:
        """
        Ensures crop resize with Shift keeps the width/height ratio from resize start.
        """

        item = CropSelectionItem(QRectF(0.0, 0.0, 200.0, 100.0))
        item.set_aspect_ratio_lock_enabled(True)
        item._resize_aspect_ratio = 2.0  # pylint: disable=protected-access

        item._resize_from_handle(  # pylint: disable=protected-access
            "bottom_right",
            QPointF(260.0, 160.0),
            lock_aspect_ratio=True,
        )
        resized = item.scene_rect()
        self.assertAlmostEqual(resized.width() / resized.height(), 2.0, places=4)

    def test_free_resize_without_shift_allows_independent_dimensions(self) -> None:
        """
        Ensures crop resize without Shift can change width and height independently.
        """

        item = CropSelectionItem(QRectF(0.0, 0.0, 200.0, 100.0))
        item.set_aspect_ratio_lock_enabled(True)

        item._resize_from_handle(  # pylint: disable=protected-access
            "bottom_right",
            QPointF(260.0, 160.0),
            lock_aspect_ratio=False,
        )
        resized = item.scene_rect()
        self.assertAlmostEqual(resized.width(), 260.0, delta=0.5)
        self.assertAlmostEqual(resized.height(), 160.0, delta=0.5)

