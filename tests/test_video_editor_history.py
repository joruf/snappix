"""
Unit tests for video editor undo/redo history.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QColor

    from src.editor_canvas import Tool
    from src.video_editor_window import VideoEditorWindow
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video history tests")
class TestVideoEditorHistory(unittest.TestCase):
    """
    Verifies undo/redo history for video annotation edits.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_history_toolbar_is_present(self) -> None:
        """
        Ensures the video editor exposes the same History strip controls.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            self.assertIsNotNone(editor.history_undo_button)
            self.assertIsNotNone(editor.history_redo_button)
            self.assertIsNotNone(editor.history_list_combo)
            self.assertIn("Initial state", editor.history_list_combo.currentText())
            editor.close()

    def test_draw_rectangle_records_history_and_undo_removes_it(self) -> None:
        """
        Ensures drawing creates a named history entry and undo restores the empty state.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            canvas = editor.canvas
            canvas.set_tool(Tool.RECT)
            canvas._finalize_annotation(  # pylint: disable=protected-access
                Tool.RECT,
                10.0,
                10.0,
                40.0,
                30.0,
            )
            editor._on_canvas_content_changed()  # pylint: disable=protected-access

            self.assertEqual(len(editor._annotations), 1)  # pylint: disable=protected-access
            self.assertEqual(editor._history_labels[-1], "Draw rectangle")  # pylint: disable=protected-access
            self.assertTrue(editor.undo_action.isEnabled())

            editor.undo()
            self.assertEqual(len(editor._annotations), 0)
            self.assertFalse(editor.undo_action.isEnabled())
            self.assertTrue(editor.redo_action.isEnabled())
            editor.close()

    def test_delete_records_history(self) -> None:
        """
        Ensures deleting a selected annotation creates one undo step.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
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
            editor._reset_history()  # pylint: disable=protected-access

            item = editor.canvas._visible_items.get(annotation.annotation_id)  # pylint: disable=protected-access
            self.assertIsNotNone(item)
            item.setSelected(True)
            self.assertTrue(editor.canvas.delete_selected_annotations())
            editor.canvas._last_action_label = "Delete selection"  # pylint: disable=protected-access
            editor.canvas.annotations_removed.emit()
            editor.canvas.content_changed.emit()

            self.assertEqual(editor._history_labels[-1], "Delete selection")  # pylint: disable=protected-access
            editor.undo()
            self.assertEqual(len(editor._annotations), 1)
            editor.close()

    def test_timeline_commit_records_history_once(self) -> None:
        """
        Ensures timeline timing edits push history only when the drag finishes.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            annotation = VideoAnnotationModel(
                annotation_type="rect",
                start_ms=1000,
                end_ms=2000,
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
            editor.timeline.set_annotations(editor._annotations)  # pylint: disable=protected-access
            editor._reset_history()  # pylint: disable=protected-access

            before = len(editor._history)  # pylint: disable=protected-access
            annotation.start_ms = 1500
            annotation.end_ms = 2500
            editor.timeline.annotation_time_changed.emit(annotation.annotation_id, 1500, 2500)
            self.assertEqual(len(editor._history), before)
            editor.timeline.annotation_time_change_committed.emit(annotation.annotation_id, 1500, 2500)
            self.assertGreater(len(editor._history), before)
            self.assertEqual(editor._history_labels[-1], "Change annotation timing")  # pylint: disable=protected-access
            editor.close()

    def test_timeline_delete_removes_track_and_canvas_object(self) -> None:
        """
        Ensures Delete on a selected track bar removes both the timeline row and
        the drawn canvas object, and records one undoable step.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
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
            editor.timeline.set_annotations(editor._annotations)  # pylint: disable=protected-access
            editor._reset_history()  # pylint: disable=protected-access
            before = len(editor._history)  # pylint: disable=protected-access

            editor.timeline.annotation_delete_requested.emit(annotation.annotation_id)

            self.assertEqual(editor._annotations, [])  # pylint: disable=protected-access
            self.assertNotIn(
                annotation.annotation_id,
                editor.canvas._visible_items,  # pylint: disable=protected-access
            )
            self.assertGreater(len(editor._history), before)  # pylint: disable=protected-access
            self.assertEqual(editor._history_labels[-1], "Delete selection")  # pylint: disable=protected-access

            editor.undo()
            self.assertEqual(len(editor._annotations), 1)  # pylint: disable=protected-access
            editor.close()


if __name__ == "__main__":
    unittest.main()
