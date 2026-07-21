"""
Unit tests for image effect helpers.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


class TestImageEffects(unittest.TestCase):
    """
    Verifies screenshot image effect helpers.
    """

    def test_pixelate_qimage_region_changes_target_area(self) -> None:
        """
        Ensures pixelation modifies pixels inside the selected region.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for image effect tests")

        from PySide6.QtCore import QRect
        from PySide6.QtGui import QImage, QColor

        from src.image_effects import pixelate_qimage_region

        image = QImage(40, 40, QImage.Format.Format_RGBA8888)
        for x_index in range(40):
            for y_index in range(40):
                color = QColor(255, 0, 0) if (x_index + y_index) % 2 == 0 else QColor(0, 0, 255)
                image.setPixelColor(x_index, y_index, color)

        result = pixelate_qimage_region(image, QRect(10, 10, 20, 20), block_size=8)
        self.assertFalse(result.isNull())
        self.assertNotEqual(image.pixelColor(15, 15).red(), image.pixelColor(15, 16).red())
        self.assertEqual(result.pixelColor(15, 15).red(), result.pixelColor(15, 16).red())
