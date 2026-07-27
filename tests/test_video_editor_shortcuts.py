"""
Unit tests for configurable keyboard shortcuts in the video editor.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QKeySequence

    from src.video_editor_window import VideoEditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video editor shortcut tests")
class TestVideoEditorShortcuts(unittest.TestCase):
    """
    Verifies the video editor's Copy/Paste/Undo/Redo/Zoom actions respect
    the same user-configurable shortcut system as the image editor.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget creation.
        """

        ensure_qapp()

    def _make_editor(self) -> VideoEditorWindow:
        """
        Builds one video editor window backed by a throwaway fake video file.

        Returns:
            VideoEditorWindow: Editor window ready for shortcut tests.
        """

        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source_video = Path(tmp_dir.name) / "source.mp4"
        source_video.write_bytes(b"not-a-real-video")
        return VideoEditorWindow(str(source_video), 320, 240)

    def test_default_shortcuts_match_editor_defaults(self) -> None:
        """
        Ensures registered actions get the default Copy/Undo key sequences.
        """

        editor = self._make_editor()
        copy_action = editor._shortcut_actions["copy"]  # pylint: disable=protected-access
        self.assertIn(QKeySequence("Ctrl+C"), copy_action.shortcuts())
        self.assertIn(QKeySequence("Ctrl+Z"), editor.undo_action.shortcuts())

    def test_custom_override_rebinds_registered_action(self) -> None:
        """
        Ensures a custom shortcut override rebinds the actual QAction.
        """

        editor = self._make_editor()
        editor.apply_editor_shortcuts({"copy": "Ctrl+Alt+C"})

        copy_action = editor._shortcut_actions["copy"]  # pylint: disable=protected-access
        self.assertIn(QKeySequence("Ctrl+Alt+C"), copy_action.shortcuts())
        self.assertNotIn(QKeySequence("Ctrl+C"), copy_action.shortcuts())


if __name__ == "__main__":
    unittest.main()
