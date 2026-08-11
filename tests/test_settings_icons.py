"""
Unit tests for settings dialog icons.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtWidgets import QLabel, QTabWidget

    from src.config import AppConfig
    from src.settings_dialog import SettingsDialog
    from src.settings_icons import build_settings_icon
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


_SETTINGS_ICON_IDS = (
    "tab_general",
    "tab_measure_box",
    "tab_shortcuts",
    "hotkeys",
    "capture_area",
    "capture_window",
    "capture_fullscreen",
    "capture_screen",
    "capture_same_area",
    "capture_video",
    "pause_resume",
    "stop_recording",
    "after_capture",
    "language",
    "screenshot_source",
    "last_tab",
    "canvas",
    "handle_size",
    "handle_position",
    "save_folder",
    "file_name",
    "workspace_folder",
    "measure_hotkey",
    "line_color",
    "fill_color",
    "ruler",
    "ruler_outside",
    "crosshair",
)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for settings icon tests")
class TestSettingsIcons(unittest.TestCase):
    """
    Verifies settings icons render and are attached in the dialog.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for icon creation.
        """

        ensure_qapp()

    def test_build_settings_icon_returns_icons_for_all_keys(self) -> None:
        """
        Ensures each settings icon id produces a non-empty pixmap.
        """

        for icon_id in _SETTINGS_ICON_IDS:
            with self.subTest(icon_id=icon_id):
                icon = build_settings_icon(icon_id)
                self.assertFalse(icon.isNull())
                self.assertFalse(icon.pixmap(18, 18).isNull())

    def test_unknown_settings_icon_is_null(self) -> None:
        """
        Ensures unknown icon ids do not raise and return a null icon.
        """

        self.assertTrue(build_settings_icon("not-a-real-icon").isNull())

    def test_settings_dialog_tabs_and_labels_carry_icons(self) -> None:
        """
        Ensures tabs and option labels in the settings dialog show icons.
        """

        from unittest.mock import patch

        with patch(
            "src.settings_dialog.GlobalHotkeyManager.is_supported",
            return_value=True,
        ):
            dialog = SettingsDialog(AppConfig())

        tabs = dialog.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        assert tabs is not None
        self.assertEqual(tabs.count(), 3)
        for index in range(tabs.count()):
            with self.subTest(tab=index):
                self.assertFalse(tabs.tabIcon(index).isNull())

        language_labels = [
            label
            for label in dialog.findChildren(QLabel)
            if label.text() in {"Language:", "Sprache:"}
        ]
        self.assertTrue(language_labels)
        icon_siblings = [
            sibling
            for label in language_labels
            for sibling in label.parent().findChildren(QLabel)
            if sibling is not label and not sibling.pixmap().isNull()
        ]
        self.assertTrue(icon_siblings)
        self.assertFalse(dialog.hotkeys_enabled_checkbox.icon().isNull())


if __name__ == "__main__":
    unittest.main()
