"""
Tests for editor host window size clamping to the active monitor.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.platform import clamp_window_size_to_available, fit_top_level_window_to_available


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

    def test_fit_never_uses_negative_upper_bound_for_oversized_frame(self) -> None:
        """
        Ensures an oversized frame is pinned to the work-area top, not above it.

        The previous clamp used ``available.bottom - frame.height`` which becomes
        negative when the frame is taller than the screen and pushed the title
        bar off-screen.
        """

        from PySide6.QtCore import QRect

        widget = MagicMock()
        screen = MagicMock()
        screen.availableGeometry.return_value = QRect(0, 0, 1280, 720)
        widget.screen.return_value = screen
        widget.frameGeometry.return_value = QRect(0, -40, 1280, 800)
        widget.geometry.return_value = QRect(0, 0, 1280, 760)
        widget.isVisible.return_value = True

        fit_top_level_window_to_available(widget, margin=0)
        move_calls = widget.move.call_args_list
        self.assertTrue(move_calls)
        _x, y = move_calls[-1].args
        self.assertGreaterEqual(y, 0)
