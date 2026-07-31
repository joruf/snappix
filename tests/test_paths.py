"""
Unit tests for cross-platform path helpers.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from src.paths import (
    default_autostart_path,
    os_family,
    supports_native_video_capture,
    supports_scroll_capture,
    supports_window_capture,
    user_cache_dir,
    user_config_dir,
    user_data_dir,
    venv_python_path,
)


class TestPaths(unittest.TestCase):
    """
    Verifies OS-specific path and capability helpers.
    """

    def test_linux_paths(self) -> None:
        """
        Ensures Linux uses XDG-style config and home workspace paths.
        """

        with patch("src.paths.sys.platform", "linux"):
            self.assertEqual(os_family(), "linux")
            self.assertEqual(user_config_dir().parts[-2:], (".config", "snappix"))
            self.assertEqual(user_data_dir().name, ".snappix")
            self.assertEqual(user_cache_dir().parts[-2:], (".cache", "snappix"))
            self.assertEqual(default_autostart_path().name, "snappix.desktop")
            self.assertTrue(supports_window_capture())
            self.assertTrue(supports_scroll_capture())
            self.assertTrue(supports_native_video_capture())

    def test_windows_paths(self) -> None:
        """
        Ensures Windows uses APPDATA/LOCALAPPDATA and Startup folder.
        """

        with patch("src.paths.sys.platform", "win32"), patch.dict(
            "os.environ",
            {
                "APPDATA": r"C:\Users\test\AppData\Roaming",
                "LOCALAPPDATA": r"C:\Users\test\AppData\Local",
            },
            clear=False,
        ):
            self.assertEqual(os_family(), "windows")
            self.assertEqual(
                user_config_dir(),
                Path(r"C:\Users\test\AppData\Roaming") / "snappix",
            )
            self.assertEqual(
                user_data_dir(),
                Path(r"C:\Users\test\AppData\Local") / "snappix",
            )
            self.assertTrue(str(default_autostart_path()).endswith("Snappix.bat"))
            self.assertTrue(supports_window_capture())
            self.assertTrue(supports_scroll_capture())
            self.assertTrue(supports_native_video_capture())

    def test_venv_python_path_windows(self) -> None:
        """
        Ensures Windows venv resolution prefers Scripts\\python.exe.
        """

        with patch("src.paths.sys.platform", "win32"):
            root = Path("/tmp/snappix-project")
            self.assertEqual(
                venv_python_path(root),
                root / ".venv" / "Scripts" / "python.exe",
            )
