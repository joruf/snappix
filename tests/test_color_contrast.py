"""
Unit tests for the WCAG contrast helpers used to keep chrome readable.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QColor

    from src.color_contrast import (
        MIN_UI_CONTRAST,
        blend_over,
        contrast_ratio,
        ensure_min_contrast,
        relative_luminance,
    )

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for color contrast tests")
class TestContrastMath(unittest.TestCase):
    """
    Verifies luminance and contrast against the values WCAG defines.
    """

    def test_luminance_of_black_and_white(self) -> None:
        """
        Pins the two anchors of the luminance scale.
        """

        self.assertAlmostEqual(relative_luminance(QColor(0, 0, 0)), 0.0, places=6)
        self.assertAlmostEqual(relative_luminance(QColor(255, 255, 255)), 1.0, places=6)

    def test_black_on_white_is_the_maximum_ratio(self) -> None:
        """
        Ensures the ratio matches WCAG's documented 21:1 maximum.
        """

        ratio = contrast_ratio(QColor(0, 0, 0), QColor(255, 255, 255))
        self.assertAlmostEqual(ratio, 21.0, places=2)

    def test_identical_colors_have_no_contrast(self) -> None:
        """
        Ensures a color against itself reports 1:1 -- the invisible case.
        """

        red = QColor(231, 76, 60)
        self.assertAlmostEqual(contrast_ratio(red, QColor(red)), 1.0, places=6)

    def test_contrast_is_symmetric(self) -> None:
        """
        Ensures argument order does not change the result.
        """

        first, second = QColor(20, 30, 40), QColor(200, 190, 180)
        self.assertAlmostEqual(
            contrast_ratio(first, second),
            contrast_ratio(second, first),
            places=9,
        )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for color contrast tests")
class TestBlendOver(unittest.TestCase):
    """
    Verifies flattening a translucent color onto a backdrop.
    """

    def test_opaque_color_is_unchanged(self) -> None:
        """
        Ensures a fully opaque color ignores the backdrop.
        """

        result = blend_over(QColor(10, 20, 30, 255), QColor(200, 200, 200))
        self.assertEqual((result.red(), result.green(), result.blue()), (10, 20, 30))

    def test_fully_transparent_color_becomes_the_background(self) -> None:
        """
        Ensures zero alpha yields the backdrop exactly.
        """

        result = blend_over(QColor(10, 20, 30, 0), QColor(200, 100, 50))
        self.assertEqual((result.red(), result.green(), result.blue()), (200, 100, 50))

    def test_half_alpha_lands_between_the_two(self) -> None:
        """
        Ensures a mid alpha composites toward the midpoint.
        """

        result = blend_over(QColor(0, 0, 0, 128), QColor(255, 255, 255))
        self.assertTrue(100 <= result.red() <= 155, result.red())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for color contrast tests")
class TestEnsureMinContrast(unittest.TestCase):
    """
    Verifies colors are lifted only as far as they need to be.
    """

    def test_already_readable_color_is_returned_unchanged(self) -> None:
        """
        Ensures a passing color keeps its exact hue.
        """

        background = QColor("#1f2430")
        color = QColor(231, 76, 60)
        result = ensure_min_contrast(color, background)
        self.assertEqual(result.name(), color.name())

    def test_color_matching_the_background_is_lifted(self) -> None:
        """
        Ensures the worst case -- annotation color equals the track -- separates.
        """

        background = QColor("#1f2430")
        result = ensure_min_contrast(QColor("#1f2430"), background)
        self.assertGreaterEqual(
            contrast_ratio(blend_over(result, background), background),
            MIN_UI_CONTRAST,
        )

    def test_dark_navy_on_a_dark_track_becomes_readable(self) -> None:
        """
        Ensures the real case: a text annotation's dark navy on the dark theme.
        """

        background = QColor("#1f2430")
        result = ensure_min_contrast(QColor(44, 62, 80), background)
        self.assertGreaterEqual(
            contrast_ratio(blend_over(result, background), background),
            MIN_UI_CONTRAST,
        )

    def test_light_background_pushes_colors_darker(self) -> None:
        """
        Ensures the adjustment direction follows the backdrop.
        """

        background = QColor("#ffffff")
        result = ensure_min_contrast(QColor("#fdfdfd"), background)
        self.assertLess(relative_luminance(result), relative_luminance(background))

    def test_alpha_is_preserved(self) -> None:
        """
        Ensures lifting a color does not silently make it opaque.
        """

        background = QColor("#1f2430")
        result = ensure_min_contrast(QColor(31, 36, 48, 140), background)
        self.assertEqual(result.alpha(), 140)


if __name__ == "__main__":
    unittest.main()
