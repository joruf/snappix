"""
Unit tests for Win32 window pick helpers.
"""

from __future__ import annotations

import ctypes
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QRect

from src.win32_window import (
    RECT,
    physical_rect_to_qt,
    qt_point_to_physical,
    window_at_point,
)


class TestWin32CoordinateConversion(unittest.TestCase):
    """
    Verifies Qt logical <-> physical pixel conversion for Win32 rects.
    """

    def test_qt_point_to_physical_scales_by_device_pixel_ratio(self) -> None:
        """
        Ensures logical points are multiplied by the screen DPR.
        """

        screen = MagicMock()
        screen.devicePixelRatio.return_value = 1.5
        with patch("src.win32_window.QGuiApplication.screenAt", return_value=screen):
            self.assertEqual(qt_point_to_physical(100, 200), (150, 300))

    def test_physical_rect_to_qt_scales_down(self) -> None:
        """
        Ensures physical GetWindowRect values become logical QRect sizes.
        """

        screen = MagicMock()
        screen.devicePixelRatio.return_value = 2.0
        with patch("src.win32_window.QGuiApplication.primaryScreen", return_value=screen), patch(
            "src.win32_window.QGuiApplication.screenAt", return_value=screen
        ):
            rect = physical_rect_to_qt(100, 200, 500, 600)
        self.assertEqual(rect, QRect(50, 100, 200, 200))


class TestWin32WindowAtPoint(unittest.TestCase):
    """
    Verifies EnumWindows-based top-level hit testing with exclusions.
    """

    def test_window_at_point_skips_excluded_hwnd_and_returns_next(self) -> None:
        """
        Ensures the overlay HWND is ignored and the next hit is returned.
        """

        overlay_hwnd = 11
        target_hwnd = 22
        rects = {
            overlay_hwnd: (0, 0, 2000, 2000),
            target_hwnd: (100, 100, 500, 400),
        }

        user32 = MagicMock()
        user32.IsWindow.return_value = True
        user32.IsWindowVisible.return_value = True
        user32.GetAncestor.side_effect = lambda hwnd, _flag: hwnd
        user32.GetWindowLongW.return_value = 0

        def get_window_rect(hwnd, rect_ptr):
            key = int(getattr(hwnd, "value", hwnd) or 0)
            left, top, right, bottom = rects[key]
            rect = ctypes.cast(rect_ptr, ctypes.POINTER(RECT)).contents
            rect.left = left
            rect.top = top
            rect.right = right
            rect.bottom = bottom
            return 1

        user32.GetWindowRect.side_effect = get_window_rect

        def enum_windows(callback, _lparam):
            for hwnd in (overlay_hwnd, target_hwnd):
                keep_going = callback(hwnd, 0)
                if not keep_going:
                    break
            return True

        user32.EnumWindows.side_effect = enum_windows

        screen = MagicMock()
        screen.devicePixelRatio.return_value = 1.0
        with patch("src.win32_window.is_win32_available", return_value=True), patch(
            "src.win32_window._user32", return_value=user32
        ), patch("src.win32_window.QGuiApplication.screenAt", return_value=screen), patch(
            "src.win32_window.QGuiApplication.primaryScreen", return_value=screen
        ):
            hwnd, geometry = window_at_point(150, 150, exclude_hwnds=(overlay_hwnd,))

        self.assertEqual(int(hwnd), target_hwnd)
        self.assertEqual(geometry, QRect(100, 100, 400, 300))

    def test_window_at_point_returns_empty_when_unavailable(self) -> None:
        """
        Ensures non-Windows hosts get an empty result.
        """

        with patch("src.win32_window.is_win32_available", return_value=False):
            hwnd, geometry = window_at_point(10, 10)
        self.assertEqual(hwnd, 0)
        self.assertTrue(geometry.isNull())
