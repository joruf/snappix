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
        from PySide6.QtGui import QKeySequence

        dialog.save_directory_edit.setText("  /home/user/Pictures  ")
        dialog.auto_crop_on_shrink_checkbox.setChecked(False)
        dialog.resize_handle_size_spin.setValue(12)
        dialog.resize_handle_position_combo.setCurrentIndex(
            dialog.resize_handle_position_combo.findData("inside")
        )
        dialog._shortcut_edits["copy"].setKeySequence(  # pylint: disable=protected-access
            QKeySequence("F7")
        )

        config = dialog.build_config()
        self.assertTrue(config.hotkeys_enabled)
        self.assertEqual(config.hotkey_capture_region, "ctrl+shift+a")
        self.assertEqual(config.hotkey_capture_window, "ctrl+shift+w")
        self.assertEqual(config.hotkey_capture_fullscreen, "ctrl+shift+f1")
        self.assertEqual(config.hotkey_measure_box, "ctrl+shift+m")
        self.assertEqual(config.post_capture_action, POST_CAPTURE_CLIPBOARD)
        self.assertEqual(config.capture_save_directory, "/home/user/Pictures")
        self.assertEqual(config.editor_last_tab_behavior, EDITOR_LAST_TAB_CLOSE_WINDOW)
        self.assertFalse(config.auto_crop_on_shrink)
        self.assertEqual(config.resize_handle_size, 12)
        self.assertEqual(config.resize_handle_position, "inside")
        self.assertEqual(config.editor_shortcuts.get("copy"), "F7")

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

    def test_measure_box_tab_persists_hotkey_and_appearance(self) -> None:
        """
        Ensures the MeasureBox tab updates hotkey and appearance settings.
        """

        from src.measurebox.settings import MeasureBoxSettings

        dialog = SettingsDialog(
            AppConfig(hotkey_measure_box="ctrl+shift+m"),
            measure_box_settings=MeasureBoxSettings(
                line_rgba=(1, 2, 3, 4),
                fill_rgba=(5, 6, 7, 8),
                ruler_enabled=False,
                ruler_outside=False,
                crosshair_enabled=True,
            ),
        )
        dialog.hotkey_measure_box_edit.setText("Ctrl+Shift+B")
        dialog.measure_ruler_checkbox.setChecked(True)
        dialog.measure_ruler_outside_checkbox.setChecked(True)
        dialog.measure_crosshair_checkbox.setChecked(False)
        dialog._measure_line_rgba = (10, 20, 30, 40)  # pylint: disable=protected-access
        dialog._measure_fill_rgba = (50, 60, 70, 80)  # pylint: disable=protected-access

        config = dialog.build_config()
        measure = dialog.build_measure_box_settings()
        self.assertEqual(config.hotkey_measure_box, "ctrl+shift+b")
        self.assertEqual(measure.line_rgba, (10, 20, 30, 40))
        self.assertEqual(measure.fill_rgba, (50, 60, 70, 80))
        self.assertTrue(measure.ruler_enabled)
        self.assertTrue(measure.ruler_outside)
        self.assertFalse(measure.crosshair_enabled)


if __name__ == "__main__":
    unittest.main()
