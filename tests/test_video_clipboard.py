"""
Unit tests for video canvas/editor copy-paste of drawn objects.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QGuiApplication

    from src.editor_canvas import Tool
    from src.video_canvas import VideoCanvas
    from src.video_editor_window import _VIDEO_ANNOTATIONS_CLIPBOARD_MIME, VideoEditorWindow
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _sample_annotation(x: float, y: float, start_ms: int, end_ms: int) -> VideoAnnotationModel:
    """
    Builds one rectangle annotation for clipboard tests.

    Args:
        x: Left position in video-pixel coordinates.
        y: Top position in video-pixel coordinates.
        start_ms: Timeline start position.
        end_ms: Timeline end position.

    Returns:
        VideoAnnotationModel: Sample annotation model.
    """

    return VideoAnnotationModel(
        annotation_type=Tool.RECT,
        start_ms=start_ms,
        end_ms=end_ms,
        x=x,
        y=y,
        width=40.0,
        height=30.0,
        stroke_rgba=[231, 76, 60, 255],
        fill_rgba=[231, 76, 60, 70],
        stroke_width=3.0,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video clipboard tests")
class TestVideoCanvasClipboard(unittest.TestCase):
    """
    Verifies canvas-level selection copy/paste primitives.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for graphics view tests.
        """

        cls._app = ensure_qapp()

    def test_collect_selected_annotations_returns_only_selected(self) -> None:
        """
        Ensures only the selected annotation is serialized for copying.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        first = _sample_annotation(10.0, 10.0, 0, 1000)
        second = _sample_annotation(100.0, 10.0, 0, 1000)
        canvas.set_annotations([first, second])

        self.assertFalse(canvas.has_selected_annotations())
        canvas._visible_items[first.annotation_id].setSelected(True)  # pylint: disable=protected-access
        self.assertTrue(canvas.has_selected_annotations())

        selected = canvas.collect_selected_annotations()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].annotation_id, first.annotation_id)

    def test_merge_annotations_payload_preserves_relative_offset_and_duration(self) -> None:
        """
        Ensures pasted annotations keep relative spatial/time spacing and land
        at the current playhead.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        canvas.set_annotations([])
        canvas._on_duration_changed(10_000)  # pylint: disable=protected-access
        canvas._position_ms = 4000  # pylint: disable=protected-access

        source = [
            _sample_annotation(10.0, 10.0, 0, 1000),
            _sample_annotation(50.0, 10.0, 500, 1500),
        ]
        self.assertTrue(canvas.merge_annotations_payload(source))

        pasted = sorted(canvas.annotations(), key=lambda item: item.start_ms)
        self.assertEqual(len(pasted), 2)
        self.assertEqual(pasted[0].start_ms, 4000)
        self.assertEqual(pasted[0].end_ms, 5000)
        self.assertEqual(pasted[1].start_ms, 4500)
        self.assertEqual(pasted[1].end_ms, 5500)
        delta_x = pasted[1].x - pasted[0].x
        self.assertAlmostEqual(delta_x, 40.0, delta=0.5)
        for item in canvas._visible_items.values():  # pylint: disable=protected-access
            self.assertTrue(item.isSelected())

    def test_merge_annotations_payload_rejects_empty_selection(self) -> None:
        """
        Ensures pasting an empty selection is a no-op.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        self.assertFalse(canvas.merge_annotations_payload([]))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video clipboard tests")
class TestVideoEditorWindowClipboard(unittest.TestCase):
    """
    Verifies the video editor's Copy/Paste actions round-trip through the
    system clipboard, matching the cross-tab behavior of the image editor.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget/media-player creation.
        """

        cls._app = ensure_qapp()

    def _make_editor(self) -> VideoEditorWindow:
        """
        Builds one video editor window backed by a throwaway fake video file.

        Returns:
            VideoEditorWindow: Editor window ready for annotation tests.
        """

        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source_video = Path(tmp_dir.name) / "source.mp4"
        source_video.write_bytes(b"not-a-real-video")
        return VideoEditorWindow(str(source_video), 320, 240)

    def test_copy_without_selection_is_a_no_op(self) -> None:
        """
        Ensures Copy with nothing selected does not touch the clipboard.
        """

        editor = self._make_editor()
        editor.canvas.set_annotations([_sample_annotation(10.0, 10.0, 0, 1000)])
        QGuiApplication.clipboard().clear()

        editor.copy_selected_annotations_to_clipboard()

        mime = QGuiApplication.clipboard().mimeData()
        self.assertFalse(mime is not None and mime.hasFormat(_VIDEO_ANNOTATIONS_CLIPBOARD_MIME))

    def test_copy_then_paste_round_trips_into_another_editor_window(self) -> None:
        """
        Ensures a copied object pastes into a different editor window/workspace,
        mirroring the image editor's cross-tab clipboard transfer.
        """

        source_editor = self._make_editor()
        annotation = _sample_annotation(10.0, 10.0, 0, 1000)
        source_editor.canvas.set_annotations([annotation])
        source_editor.canvas._visible_items[annotation.annotation_id].setSelected(  # pylint: disable=protected-access
            True
        )

        source_editor.copy_selected_annotations_to_clipboard()
        mime = QGuiApplication.clipboard().mimeData()
        self.assertTrue(mime.hasFormat(_VIDEO_ANNOTATIONS_CLIPBOARD_MIME))
        payload = json.loads(bytes(mime.data(_VIDEO_ANNOTATIONS_CLIPBOARD_MIME)).decode("utf-8"))
        self.assertEqual(len(payload.get("annotations") or []), 1)

        target_editor = self._make_editor()
        target_editor.paste_annotations_from_clipboard()

        self.assertEqual(len(target_editor.canvas.annotations()), 1)
        pasted = target_editor.canvas.annotations()[0]
        self.assertEqual(pasted.annotation_type, annotation.annotation_type)
        self.assertNotEqual(pasted.annotation_id, annotation.annotation_id)

    def test_copy_drawing_area_ignores_selection_and_copies_everything(self) -> None:
        """
        Ensures "Copy Drawing Area" copies every annotation in the tab, not
        just the selected ones, mirroring the Image editor's equivalent action.
        """

        source_editor = self._make_editor()
        selected = _sample_annotation(10.0, 10.0, 0, 1000)
        unselected = _sample_annotation(60.0, 10.0, 0, 1000)
        source_editor.canvas.set_annotations([selected, unselected])
        source_editor.canvas._visible_items[selected.annotation_id].setSelected(  # pylint: disable=protected-access
            True
        )

        source_editor.copy_drawing_area_to_clipboard()

        mime = QGuiApplication.clipboard().mimeData()
        self.assertTrue(mime.hasFormat(_VIDEO_ANNOTATIONS_CLIPBOARD_MIME))
        payload = json.loads(bytes(mime.data(_VIDEO_ANNOTATIONS_CLIPBOARD_MIME)).decode("utf-8"))
        self.assertEqual(len(payload.get("annotations") or []), 2)

        target_editor = self._make_editor()
        target_editor.paste_annotations_from_clipboard()
        self.assertEqual(len(target_editor.canvas.annotations()), 2)

    def test_copy_drawing_area_with_no_annotations_is_a_no_op(self) -> None:
        """
        Ensures "Copy Drawing Area" does nothing when the tab has no annotations.
        """

        editor = self._make_editor()
        QGuiApplication.clipboard().clear()

        editor.copy_drawing_area_to_clipboard()

        mime = QGuiApplication.clipboard().mimeData()
        self.assertFalse(mime is not None and mime.hasFormat(_VIDEO_ANNOTATIONS_CLIPBOARD_MIME))

    def test_copy_also_publishes_a_picture_for_other_applications(self) -> None:
        """
        Ensures copying a drawn object puts a real image on the clipboard too,
        so it can be pasted into any other program on the machine.
        """

        editor = self._make_editor()
        annotation = _sample_annotation(10.0, 10.0, 0, 1000)
        editor.canvas.set_annotations([annotation])
        editor.canvas._visible_items[annotation.annotation_id].setSelected(  # pylint: disable=protected-access
            True
        )

        editor.copy_selected_annotations_to_clipboard()

        mime = QGuiApplication.clipboard().mimeData()
        self.assertTrue(mime.hasImage())
        image = mime.imageData()
        self.assertIsNotNone(image)
        self.assertGreater(image.width(), 0)
        self.assertGreater(image.height(), 0)
        # The in-app payload must still be present so internal paste keeps its
        # full fidelity instead of degrading to a flat picture.
        self.assertTrue(mime.hasFormat(_VIDEO_ANNOTATIONS_CLIPBOARD_MIME))

    def test_copied_picture_is_not_blank(self) -> None:
        """
        Ensures the published picture actually contains the drawn object.
        """

        editor = self._make_editor()
        annotation = _sample_annotation(10.0, 10.0, 0, 1000)
        editor.canvas.set_annotations([annotation])
        editor.canvas._visible_items[annotation.annotation_id].setSelected(  # pylint: disable=protected-access
            True
        )

        editor.copy_selected_annotations_to_clipboard()

        image = QGuiApplication.clipboard().mimeData().imageData()
        opaque = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0
        )
        self.assertGreater(opaque, 0)

    def test_copy_drawing_area_also_publishes_a_picture(self) -> None:
        """
        Ensures "Copy Drawing Area" carries a picture too, matching the image
        editor's equivalent action.
        """

        editor = self._make_editor()
        editor.canvas.set_annotations(
            [_sample_annotation(10.0, 10.0, 0, 1000), _sample_annotation(60.0, 10.0, 0, 1000)]
        )

        editor.copy_drawing_area_to_clipboard()

        self.assertTrue(QGuiApplication.clipboard().mimeData().hasImage())


if __name__ == "__main__":
    unittest.main()
