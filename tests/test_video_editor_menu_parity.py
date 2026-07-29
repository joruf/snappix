"""
Unit tests for Video editor menu parity with the Image editor: Settings,
Help (About/Manual), Theme submenu, and an explicit Close action.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtWidgets import QDialog, QMessageBox

    from src.theme import THEME_DARK, THEME_SEPIA
    from src.video_editor_window import VideoEditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _make_silent_video(path: Path) -> None:
    """
    Renders a tiny silent test clip with ffmpeg for video editor tests.

    Args:
        path: Destination file path for the generated video.

    Returns:
        None
    """

    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:d=1",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _menu_map(editor: "VideoEditorWindow") -> dict:
    """
    Builds a {top-level menu title: [item labels]} map from the menu bar.

    Args:
        editor: Video editor window to inspect.

    Returns:
        dict: Menu title to ordered item-label list (separators as "---").
    """

    result = {}
    for action in editor.menuBar().actions():
        menu = action.menu()
        if menu is None:
            continue
        result[action.text()] = [item.text() or "---" for item in menu.actions()]
    return result


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video editor menu tests")
class TestVideoEditorMenuParity(unittest.TestCase):
    """
    Verifies the video editor menu bar exposes Help/Settings/Theme/Close.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _make_editor(self) -> "VideoEditorWindow":
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        source_video = Path(tmp_dir) / "source.mp4"
        _make_silent_video(source_video)
        editor = VideoEditorWindow(str(source_video), 320, 240)
        self.addCleanup(editor.close)
        return editor

    def test_help_menu_exists_with_about_and_manual(self) -> None:
        """
        Ensures a Help menu with About and Manual exists, matching the Image editor.
        """

        editor = self._make_editor()
        menus = _menu_map(editor)
        self.assertIn("Help", menus)
        self.assertEqual(menus["Help"], ["About", "Manual"])

    def test_view_menu_has_theme_submenu_and_settings(self) -> None:
        """
        Ensures the View menu exposes the Theme submenu and Settings action.
        """

        editor = self._make_editor()
        menus = _menu_map(editor)
        self.assertIn("Theme", menus["View"])
        self.assertIn("Settings...", menus["View"])

    def test_file_menu_has_explicit_close_action(self) -> None:
        """
        Ensures the File menu exposes an explicit Close action for the tab.
        """

        editor = self._make_editor()
        menus = _menu_map(editor)
        self.assertIn("Close", menus["File"])

    def test_theme_action_emits_theme_changed(self) -> None:
        """
        Ensures picking a theme from the menu emits theme_changed with the
        selected theme id.
        """

        editor = self._make_editor()
        spy = MagicMock()
        editor.theme_changed.connect(spy)

        editor.theme_dark_action.trigger()

        spy.assert_called_once_with(THEME_DARK)

    def test_settings_action_emits_settings_requested(self) -> None:
        """
        Ensures the Settings... action emits settings_requested.
        """

        editor = self._make_editor()
        spy = MagicMock()
        editor.settings_requested.connect(spy)

        for action in editor.findChildren(type(editor.theme_dark_action)):
            if action.text() == "Settings...":
                action.trigger()
                break

        spy.assert_called_once()

    def test_set_theme_selection_checks_matching_theme_action(self) -> None:
        """
        Ensures set_theme_selection checks exactly the matching theme action
        without emitting further theme_changed signals.
        """

        editor = self._make_editor()
        spy = MagicMock()
        editor.theme_changed.connect(spy)

        editor.set_theme_selection(THEME_SEPIA)

        self.assertTrue(editor.theme_sepia_action.isChecked())
        self.assertFalse(editor.theme_dark_action.isChecked())
        spy.assert_not_called()

    def test_show_about_and_manual_do_not_raise(self) -> None:
        """
        Ensures both Help dialogs build and exec without error.
        """

        editor = self._make_editor()
        with patch.object(QMessageBox, "exec", return_value=0):
            editor.show_about()
        with patch.object(QDialog, "exec", return_value=0):
            editor.show_manual()


if __name__ == "__main__":
    unittest.main()
