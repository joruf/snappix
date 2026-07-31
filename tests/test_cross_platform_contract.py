"""
Cross-platform contract tests for Linux and Windows Snappix behavior.

These tests must stay green on both CI runners. They mock each OS family so
Linux hosts still verify Windows contracts and vice versa.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.os_compatibility import (
    LINUX_X11_FULL,
    WINDOWS,
    PlatformContext,
    SupportLevel,
    current_os_family,
    evaluate_capabilities,
    region_capture_route,
)
from src.paths import (
    default_autostart_path,
    os_family,
    supports_native_video_capture,
    supports_scroll_capture,
    supports_window_capture,
    user_config_dir,
    user_data_dir,
    venv_python_path,
)
from src.win32_window import is_win32_available


class TestCrossPlatformContract(unittest.TestCase):
    """
    Verifies the shared platform API contract for Linux and Windows.
    """

    def test_runtime_os_family_is_linux_or_windows(self) -> None:
        """
        Ensures CI and local hosts report a supported OS family.
        """

        self.assertIn(current_os_family(), {"linux", "windows"})
        self.assertIn(os_family(), {"linux", "windows"})

    def test_linux_path_and_capability_contract(self) -> None:
        """
        Ensures Linux uses XDG paths and enables capture capabilities.
        """

        with patch("src.paths.sys.platform", "linux"):
            self.assertEqual(user_config_dir().parts[-2:], (".config", "snappix"))
            self.assertEqual(user_data_dir().name, ".snappix")
            self.assertEqual(default_autostart_path().name, "snappix.desktop")
            self.assertEqual(
                venv_python_path(Path("/project")),
                Path("/project/.venv/bin/python"),
            )
            self.assertTrue(supports_window_capture())
            self.assertTrue(supports_scroll_capture())
            self.assertTrue(supports_native_video_capture())

    def test_windows_path_and_capability_contract(self) -> None:
        """
        Ensures Windows uses APPDATA paths and enables capture capabilities.
        """

        with patch("src.paths.sys.platform", "win32"), patch.dict(
            "os.environ",
            {
                "APPDATA": r"C:\Users\ci\AppData\Roaming",
                "LOCALAPPDATA": r"C:\Users\ci\AppData\Local",
            },
            clear=False,
        ):
            self.assertEqual(
                user_config_dir(),
                Path(r"C:\Users\ci\AppData\Roaming") / "snappix",
            )
            self.assertEqual(
                user_data_dir(),
                Path(r"C:\Users\ci\AppData\Local") / "snappix",
            )
            self.assertTrue(str(default_autostart_path()).endswith("Snappix.bat"))
            self.assertEqual(
                venv_python_path(Path(r"C:\snappix")),
                Path(r"C:\snappix") / ".venv" / "Scripts" / "python.exe",
            )
            self.assertTrue(supports_window_capture())
            self.assertTrue(supports_scroll_capture())
            self.assertTrue(supports_native_video_capture())

    def test_region_capture_routing_contract(self) -> None:
        """
        Ensures region capture routes match the documented platform backends.
        """

        self.assertEqual(region_capture_route(LINUX_X11_FULL), "qt_overlay")
        self.assertEqual(region_capture_route(WINDOWS), "qt_overlay")
        self.assertEqual(
            region_capture_route(
                PlatformContext(
                    os_family="linux",
                    is_wayland=True,
                    available_tools=frozenset({"grim", "slurp"}),
                )
            ),
            "grim_slurp",
        )
        self.assertEqual(
            region_capture_route(PlatformContext(os_family="darwin")),
            "unavailable",
        )

    def test_video_command_backends_contract(self) -> None:
        """
        Ensures Linux uses x11grab and Windows uses gdigrab for region video.
        """

        from PySide6.QtCore import QRect

        from src.video_recorder import build_record_command

        rect = QRect(10, 20, 640, 480)
        with patch("src.paths.is_windows", return_value=False):
            linux_cmd = build_record_command(
                rect, Path("/tmp/out.mp4"), record_microphone=False
            )
        self.assertIn("x11grab", linux_cmd)
        self.assertNotIn("gdigrab", linux_cmd)

        with patch("src.paths.is_windows", return_value=True):
            windows_cmd = build_record_command(
                rect, Path(r"C:\tmp\out.mp4"), record_microphone=False
            )
        self.assertIn("gdigrab", windows_cmd)
        self.assertIn("desktop", windows_cmd)
        self.assertNotIn("x11grab", windows_cmd)

    def test_capability_matrix_supports_both_desktops(self) -> None:
        """
        Ensures Linux X11 and Windows profiles remain launchable for capture.
        """

        linux = evaluate_capabilities(LINUX_X11_FULL)
        windows = evaluate_capabilities(WINDOWS)
        self.assertEqual(linux["app_launch"].level, SupportLevel.FULL)
        self.assertIn(
            windows["app_launch"].level,
            {SupportLevel.FULL, SupportLevel.PARTIAL},
        )
        self.assertEqual(linux["fullscreen_capture"].level, SupportLevel.FULL)
        self.assertEqual(windows["fullscreen_capture"].level, SupportLevel.FULL)
        self.assertEqual(linux["video_capture"].level, SupportLevel.FULL)
        self.assertEqual(windows["video_capture"].level, SupportLevel.FULL)

    def test_win32_module_imports_safely_on_non_windows(self) -> None:
        """
        Ensures win32 helpers import without requiring native Windows APIs.
        """

        if sys.platform == "win32":
            self.assertTrue(is_win32_available())
        else:
            self.assertFalse(is_win32_available())
            hwnd, geometry = __import__(
                "src.win32_window", fromlist=["window_at_point"]
            ).window_at_point(1, 1)
            self.assertEqual(hwnd, 0)
            self.assertTrue(geometry.isNull())


if __name__ == "__main__":
    unittest.main()
