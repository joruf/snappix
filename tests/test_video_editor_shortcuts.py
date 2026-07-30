"""
Unit tests for configurable keyboard shortcuts in the video editor.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QKeySequence

    from src.editor_canvas import Tool
    from src.video_editor_window import VideoEditorWindow
    from src.video_models import VideoAnnotationModel
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

    def _send_key_to_window(self, editor: VideoEditorWindow, key) -> None:
        """
        Delivers one key press to the window, as an unhandled child key would.

        Args:
            editor: Editor window under test.
            key: Qt key constant to send.

        Returns:
            None
        """

        editor.keyPressEvent(
            QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        )

    def test_enter_reaches_canvas_while_timeline_holds_focus(self) -> None:
        """
        Ensures a pending polygon can still be finalized after the timeline took
        click focus, which it needs for its own Delete handling.
        """

        editor = self._make_editor()
        editor.canvas.set_tool(Tool.POLYGON)
        editor.canvas._poly_points = [  # pylint: disable=protected-access
            QPointF(10, 10),
            QPointF(50, 50),
            QPointF(80, 20),
        ]

        self._send_key_to_window(editor, Qt.Key.Key_Return)

        self.assertEqual(editor.canvas._poly_points, [])  # pylint: disable=protected-access

    def test_escape_reaches_canvas_while_timeline_holds_focus(self) -> None:
        """
        Ensures Escape still cancels a pending polygon draw after a timeline click.
        """

        editor = self._make_editor()
        editor.canvas.set_tool(Tool.POLYGON)
        editor.canvas._poly_points = [  # pylint: disable=protected-access
            QPointF(10, 10),
            QPointF(50, 50),
        ]

        self._send_key_to_window(editor, Qt.Key.Key_Escape)

        self.assertEqual(editor.canvas._poly_points, [])  # pylint: disable=protected-access

    def test_delete_falls_back_to_canvas_selection(self) -> None:
        """
        Ensures Delete still removes the canvas selection when no timeline track
        bar is selected.
        """

        editor = self._make_editor()
        annotation = VideoAnnotationModel(
            annotation_type="rect",
            start_ms=0,
            end_ms=1000,
            x=12.0,
            y=12.0,
            width=24.0,
            height=18.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        editor._annotations.append(annotation)  # pylint: disable=protected-access
        editor.canvas.set_annotations(editor._annotations)  # pylint: disable=protected-access
        item = editor.canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        item.setSelected(True)

        self._send_key_to_window(editor, Qt.Key.Key_Delete)

        self.assertEqual(editor._annotations, [])  # pylint: disable=protected-access


if __name__ == "__main__":
    unittest.main()
