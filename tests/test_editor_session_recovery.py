"""
Regression tests for editor session recovery across mixed tab types.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

    from src.session_recovery import EditorSessionTab
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for editor session recovery tests")
class TestCollectEditorSessionTabsMixedTabs(unittest.TestCase):
    """
    Verifies _collect_editor_session_tabs persists image and video editor tabs.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_image_and_video_tabs_are_collected(self) -> None:
        """
        Ensures mixed tab strips flush both tab kinds into the session manifest.
        """

        from run import AppController

        controller = object.__new__(AppController)
        controller.editor_tabs = QTabWidget()

        image_editor = QWidget()
        image_editor.flush_recovery_snapshot = MagicMock()
        image_editor.recovery_path = MagicMock(return_value="/tmp/snappix-session/tab-image.sfp")
        image_editor.set_recovery_path = MagicMock()
        image_editor._current_project_path = ""
        controller.editor_tabs.addTab(image_editor, "Screenshot 1")

        video_editor = QWidget()
        video_editor.flush_recovery_snapshot = MagicMock()
        video_editor.recovery_path = MagicMock(return_value="/tmp/snappix-session/tab-video.sfpv")
        video_editor.set_recovery_path = MagicMock()
        video_editor._current_project_path = ""
        controller.editor_tabs.addTab(video_editor, "Recording 1")

        controller.video_editors = [video_editor]
        controller.editors = [image_editor]

        with patch("src.session_recovery.ensure_tab_recovery_path", side_effect=lambda path: path):
            tabs = controller._collect_editor_session_tabs()

        image_editor.flush_recovery_snapshot.assert_called_once()
        video_editor.flush_recovery_snapshot.assert_called_once()
        self.assertEqual(len(tabs), 2)
        self.assertEqual(tabs[0].kind, "image")
        self.assertEqual(tabs[1].kind, "video")


if __name__ == "__main__":
    unittest.main()
