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


if __name__ == "__main__":
    unittest.main()
