"""
Unit tests for VideoEditorWindow._on_effect_edit_requested: wiring the
Effects dialog result back onto the target annotation, refreshing the
canvas/timeline, and recording undo history.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtWidgets import QDialog

    from src.editor_canvas import Tool
    from src.effects_dialog import EffectsDialog
    from src.video_editor_window import VideoEditorWindow
    from src.video_effects import (
        EFFECT_EDGE_START,
        EFFECT_KIND_FADE,
        add_annotation_effect,
        get_annotation_effects,
    )
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _sample_annotation() -> "VideoAnnotationModel":
    """
    Builds one rectangle annotation for effects-integration tests.

    Returns:
        VideoAnnotationModel: Sample annotation model.
    """

    return VideoAnnotationModel(
        annotation_type=Tool.RECT,
        start_ms=0,
        end_ms=2000,
        x=10.0,
        y=10.0,
        width=40.0,
        height=30.0,
        stroke_rgba=[231, 76, 60, 255],
        fill_rgba=[231, 76, 60, 70],
        stroke_width=3.0,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for effects integration tests")
class TestVideoEditorEffectEditRequested(unittest.TestCase):
    """
    Verifies the editor applies, or discards, Effects dialog results.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _make_editor(self) -> "VideoEditorWindow":
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source_video = Path(tmp_dir.name) / "source.mp4"
        source_video.write_bytes(b"not-a-real-video")
        return VideoEditorWindow(str(source_video), 320, 240)

    def test_accepting_the_dialog_applies_new_effects_and_records_history(self) -> None:
        """
        Ensures accepting the dialog writes its effect list onto the
        annotation, refreshes the canvas/timeline, and pushes an undo step.
        """

        editor = self._make_editor()
        annotation = _sample_annotation()
        editor._annotations.append(annotation)  # pylint: disable=protected-access
        editor.canvas.set_annotations(editor._annotations)  # pylint: disable=protected-access

        def fake_exec(self):
            self._effects.append(  # pylint: disable=protected-access
                {"id": "new-effect", "kind": EFFECT_KIND_FADE, "edge": EFFECT_EDGE_START, "duration_ms": 300}
            )
            return QDialog.DialogCode.Accepted

        history_before = len(editor._history)  # pylint: disable=protected-access
        with patch.object(EffectsDialog, "exec", fake_exec):
            editor._on_effect_edit_requested(annotation.annotation_id)  # pylint: disable=protected-access

        effects = get_annotation_effects(annotation)
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]["id"], "new-effect")
        self.assertGreater(len(editor._history), history_before)  # pylint: disable=protected-access

    def test_cancelling_the_dialog_leaves_effects_unchanged(self) -> None:
        """
        Ensures rejecting the dialog does not touch the annotation's effects.
        """

        editor = self._make_editor()
        annotation = _sample_annotation()
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)
        editor._annotations.append(annotation)  # pylint: disable=protected-access
        editor.canvas.set_annotations(editor._annotations)  # pylint: disable=protected-access
        original_effects = get_annotation_effects(annotation)

        with patch.object(EffectsDialog, "exec", lambda self: QDialog.DialogCode.Rejected):
            editor._on_effect_edit_requested(annotation.annotation_id)  # pylint: disable=protected-access

        self.assertEqual(get_annotation_effects(annotation), original_effects)

    def test_unknown_annotation_id_is_a_no_op(self) -> None:
        """
        Ensures requesting effects for a missing annotation id does nothing.
        """

        editor = self._make_editor()
        with patch.object(EffectsDialog, "__init__", MagicMock(side_effect=AssertionError("should not open"))):
            editor._on_effect_edit_requested("missing-id")  # pylint: disable=protected-access


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for effects integration tests")
class TestExportCutPoints(unittest.TestCase):
    """
    Verifies the export slices effect windows finely enough to animate them,
    instead of burning one static overlay per visibility segment.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _make_editor(self) -> "VideoEditorWindow":
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source_video = Path(tmp_dir.name) / "source.mp4"
        source_video.write_bytes(b"not-a-real-video")
        return VideoEditorWindow(str(source_video), 320, 240)

    def test_annotation_without_effects_only_cuts_at_its_edges(self) -> None:
        """
        Ensures an effect-free timeline keeps the original coarse segmentation.
        """

        editor = self._make_editor()
        annotation = _sample_annotation()
        editor._annotations.append(annotation)  # pylint: disable=protected-access

        cuts = editor.export_cut_points(5000)

        self.assertEqual(cuts, [0, 2000, 5000])

    def test_fade_in_window_is_sliced_into_steps(self) -> None:
        """
        Ensures a Fade In produces intermediate cuts across its window only.
        """

        editor = self._make_editor()
        annotation = _sample_annotation()
        add_annotation_effect(
            annotation,
            kind=EFFECT_KIND_FADE,
            edge=EFFECT_EDGE_START,
            duration_ms=1000,
        )
        editor._annotations.append(annotation)  # pylint: disable=protected-access

        cuts = editor.export_cut_points(5000)

        inside_window = [cut for cut in cuts if 0 < cut < 1000]
        self.assertGreater(len(inside_window), 1)
        # Nothing between the fade window's end and the annotation's end.
        self.assertEqual([cut for cut in cuts if 1000 < cut < 2000], [])
        self.assertEqual(cuts, sorted(set(cuts)))

    def test_slice_count_stays_bounded_for_long_effects(self) -> None:
        """
        Ensures a maximum-length effect cannot explode the ffmpeg filter graph.
        """

        editor = self._make_editor()
        annotation = _sample_annotation()
        annotation.end_ms = 30_000
        add_annotation_effect(
            annotation,
            kind=EFFECT_KIND_FADE,
            edge=EFFECT_EDGE_START,
            duration_ms=5000,
        )
        editor._annotations.append(annotation)  # pylint: disable=protected-access

        cuts = editor.export_cut_points(30_000)

        inside_window = [cut for cut in cuts if 0 < cut < 5000]
        self.assertLessEqual(len(inside_window), 24)

    def test_effect_overlays_differ_across_the_fade_window(self) -> None:
        """
        Ensures the baked overlays actually change, i.e. the fade is animated
        rather than rendered at one constant opacity.
        """

        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        editor = self._make_editor()
        annotation = _sample_annotation()
        add_annotation_effect(
            annotation,
            kind=EFFECT_KIND_FADE,
            edge=EFFECT_EDGE_START,
            duration_ms=1000,
        )

        def _alpha_sum_at(position_ms: int) -> int:
            image = QImage(320, 240, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            editor._paint_annotation_for_export(  # pylint: disable=protected-access
                painter,
                QStyleOptionGraphicsItem(),
                annotation,
                position_ms,
            )
            painter.end()
            return sum(
                image.pixelColor(x, y).alpha()
                for y in range(0, 240, 4)
                for x in range(0, 320, 4)
            )

        early = _alpha_sum_at(100)
        late = _alpha_sum_at(900)

        self.assertLess(early, late)


if __name__ == "__main__":
    unittest.main()
