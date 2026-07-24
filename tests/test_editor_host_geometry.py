"""
Tests for editor host window size clamping to the active monitor.
"""

from __future__ import annotations

import unittest

from src.platform import clamp_window_size_to_available


class TestEditorHostGeometryClamp(unittest.TestCase):
    """
    Verifies the editor never prefers a size larger than the monitor work area.
    """

    def test_large_preferred_size_is_clamped_to_small_screen(self) -> None:
        """
        Ensures a 1240x860 preference shrinks on a 1024x768 work area.
        """

        width, height = clamp_window_size_to_available(1240, 860, 1024, 768)
        self.assertLessEqual(width, 1024 - 24)
        self.assertLessEqual(height, 768 - 24)

    def test_tiny_screen_keeps_minimum_usable_bounds(self) -> None:
        """
        Ensures extremely small work areas still yield positive clamped sizes.
        """

        width, height = clamp_window_size_to_available(1240, 860, 400, 300)
        self.assertEqual((width, height), (480, 360))

    def test_large_screen_keeps_preferred_size(self) -> None:
        """
        Ensures a large monitor keeps the preferred editor size.
        """

        width, height = clamp_window_size_to_available(1240, 860, 1920, 1080)
        self.assertEqual((width, height), (1240, 860))
