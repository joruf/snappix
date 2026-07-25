"""
Regression tests for editor session recovery across mixed tab types.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
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

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            image_path = tmp_root / "tab-image.sfp"
            video_path = tmp_root / "tab-video.sfpv"
            image_path.write_bytes(b"image")
            video_path.write_bytes(b"video")

            controller = object.__new__(AppController)
            controller.editor_tabs = QTabWidget()

            image_editor = QWidget()
            image_editor.flush_recovery_snapshot = MagicMock()
            image_editor.recovery_path = MagicMock(return_value=str(image_path))
            image_editor.set_recovery_path = MagicMock()
            image_editor._current_project_path = ""
            controller.editor_tabs.addTab(image_editor, "Screenshot 1")

            video_editor = QWidget()
            video_editor.flush_recovery_snapshot = MagicMock()
            video_editor.recovery_path = MagicMock(return_value=str(video_path))
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

    def test_collect_persists_video_tab_when_recovery_file_is_written(self) -> None:
        """
        Ensures mixed session collection writes and keeps video tabs with .sfpv files.
        """

        from run import AppController
        from src.video_editor_window import VideoEditorWindow

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            source_video.write_bytes(b"video-bytes")
            recovery_path = tmp_root / "tab-video.sfpv"

            controller = object.__new__(AppController)
            controller.editor_tabs = QTabWidget()
            controller.video_editors = []

            editor = VideoEditorWindow(str(source_video), 320, 240)
            editor.set_recovery_path(str(recovery_path))
            editor._cached_duration_ms = 1500
            editor.canvas.duration_ms = MagicMock(return_value=1500)
            controller.editor_tabs.addTab(editor, "Recording")

            with patch("src.session_recovery.ensure_tab_recovery_path", side_effect=lambda path: path):
                tabs = controller._collect_editor_session_tabs()

            self.assertEqual(len(tabs), 1)
            self.assertEqual(tabs[0].kind, "video")
            self.assertTrue(Path(tabs[0].recovery_path).is_file())


if __name__ == "__main__":
    unittest.main()
