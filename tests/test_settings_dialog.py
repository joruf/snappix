"""
Unit tests for the application settings dialog.
"""

from __future__ import annotations

import unittest

try:
    from src.config import (
        AppConfig,
        EDITOR_LAST_TAB_CLOSE_WINDOW,
        POST_CAPTURE_CLIPBOARD,
    )
    from src.settings_dialog import SettingsDialog
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for settings dialog tests")
class TestSettingsDialog(unittest.TestCase):
    """
    Verifies settings dialog field mapping to AppConfig.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_build_config_normalizes_hotkeys_and_post_capture(self) -> None:
        """
        Ensures dialog fields produce normalized configuration values.
        """

        dialog = SettingsDialog(
            AppConfig(
                hotkeys_enabled=True,
                hotkey_capture_region="ctrl+shift+a",
                hotkey_capture_window="ctrl+shift+w",
                hotkey_capture_fullscreen="ctrl+shift+f",
                post_capture_action="editor",
                capture_save_directory="/tmp/snappix",
            )
        )
        dialog.hotkey_region_edit.setText("Ctrl+Shift+A")
        dialog.hotkey_window_edit.setText(" CTRL + shift + w ")
        dialog.hotkey_fullscreen_edit.setText("Ctrl+Shift+F1")
        dialog.post_capture_combo.setCurrentIndex(
            dialog.post_capture_combo.findData(POST_CAPTURE_CLIPBOARD)
        )
        dialog.editor_last_tab_combo.setCurrentIndex(
            dialog.editor_last_tab_combo.findData(EDITOR_LAST_TAB_CLOSE_WINDOW)
        )
        dialog.save_directory_edit.setText("  /home/user/Pictures  ")

        config = dialog.build_config()
        self.assertTrue(config.hotkeys_enabled)
        self.assertEqual(config.hotkey_capture_region, "ctrl+shift+a")
        self.assertEqual(config.hotkey_capture_window, "ctrl+shift+w")
        self.assertEqual(config.hotkey_capture_fullscreen, "ctrl+shift+f1")
        self.assertEqual(config.post_capture_action, POST_CAPTURE_CLIPBOARD)
        self.assertEqual(config.capture_save_directory, "/home/user/Pictures")
        self.assertEqual(config.editor_last_tab_behavior, EDITOR_LAST_TAB_CLOSE_WINDOW)

    def test_build_config_preserves_autostart_and_theme(self) -> None:
        """
        Ensures autostart and theme values are carried over unchanged.
        """

        dialog = SettingsDialog(
            AppConfig(
                autostart_enabled=True,
                theme="light",
            )
        )
        config = dialog.build_config()
        self.assertTrue(config.autostart_enabled)
        self.assertEqual(config.theme, "light")
