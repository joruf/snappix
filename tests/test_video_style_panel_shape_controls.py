"""
Tests for the Video editor's Style panel Thickness/Style/Radius controls --
the video-editor mirror of tests/test_style_panel_shape_controls.py.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from src.annotation_items import STROKE_STYLE_DASH
    from src.editor_canvas import Tool
    from src.video_editor_window import VideoEditorWindow
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _rect_annotation(**overrides) -> "VideoAnnotationModel":
    """
    Builds one rectangle video annotation, with any field overridden.

    Args:
        overrides: Field values to override on the default rectangle model.

    Returns:
        VideoAnnotationModel: Sample annotation model.
    """

    defaults = dict(
        annotation_type=Tool.RECT,
        start_ms=0,
        end_ms=5000,
        x=10.0,
        y=10.0,
        width=40.0,
        height=20.0,
        stroke_rgba=[255, 0, 0, 255],
        fill_rgba=[255, 0, 0, 80],
        stroke_width=6.0,
        payload={"corner_radius": 8.0, "stroke_style": STROKE_STYLE_DASH},
    )
    defaults.update(overrides)
    return VideoAnnotationModel(**defaults)


def _line_annotation(**overrides) -> "VideoAnnotationModel":
    """
    Builds one line video annotation, with any field overridden.

    Args:
        overrides: Field values to override on the default line model.

    Returns:
        VideoAnnotationModel: Sample annotation model.
    """

    defaults = dict(
        annotation_type=Tool.LINE,
        start_ms=0,
        end_ms=5000,
        x=10.0,
        y=20.0,
        width=60.0,
        height=0.0,
        stroke_rgba=[0, 0, 255, 255],
        fill_rgba=[0, 0, 0, 0],
        stroke_width=3.0,
    )
    defaults.update(overrides)
    return VideoAnnotationModel(**defaults)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video style panel tests")
class TestVideoStylePanelShapeControls(unittest.TestCase):
    """
    Verifies the video Style tab's shape controls show/hide/sync/apply,
    mirroring the Image editor's Style panel behavior.
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

    def _select_only(self, editor, annotation) -> None:
        editor.canvas._visible_items[annotation.annotation_id].setSelected(  # pylint: disable=protected-access
            True
        )
        editor.canvas._refresh_selection_style()  # pylint: disable=protected-access

    def test_no_selection_hides_style_tab_and_resets_controls(self) -> None:
        """
        Ensures an empty selection hides the Style tab and resets shape controls.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        annotation = _rect_annotation()
        editor.canvas.set_annotations([annotation])
        self._select_only(editor, annotation)
        editor.canvas._visible_items[annotation.annotation_id].setSelected(False)  # pylint: disable=protected-access
        editor.canvas._refresh_selection_style()  # pylint: disable=protected-access

        self.assertFalse(toolbar._property_tabs.isTabVisible(0))  # pylint: disable=protected-access
        self.assertEqual(toolbar.style_thickness_slider.value(), 0)

    def test_no_selection_collapses_the_panel_not_just_its_tab(self) -> None:
        """
        Ensures the empty Style panel gives its height back to the video.

        Style is this tab widget's only tab, so hiding the tab header alone left
        an empty framed block above the canvas in the editor's default state.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        annotation = _rect_annotation()
        editor.canvas.set_annotations([annotation])
        self._select_only(editor, annotation)
        editor.canvas._visible_items[annotation.annotation_id].setSelected(False)  # pylint: disable=protected-access
        editor.canvas._refresh_selection_style()  # pylint: disable=protected-access

        self.assertTrue(toolbar._property_tabs.isHidden())  # pylint: disable=protected-access

    def test_selecting_a_shape_shows_the_panel_again(self) -> None:
        """
        Ensures the collapsed panel comes back when there is something to show.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        annotation = _rect_annotation()
        editor.canvas.set_annotations([annotation])
        self._select_only(editor, annotation)

        self.assertFalse(toolbar._property_tabs.isHidden())  # pylint: disable=protected-access

    def test_selecting_a_rect_shows_thickness_style_and_radius(self) -> None:
        """
        Ensures selecting a rectangle populates all three shape controls.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        annotation = _rect_annotation()
        editor.canvas.set_annotations([annotation])
        self._select_only(editor, annotation)

        self.assertTrue(toolbar._property_tabs.isTabVisible(0))  # pylint: disable=protected-access
        self.assertFalse(toolbar.style_thickness_slider.isHidden())
        self.assertFalse(toolbar.style_stroke_style_combo.isHidden())
        self.assertFalse(toolbar.style_radius_slider.isHidden())
        self.assertEqual(toolbar.style_thickness_slider.value(), 6)
        self.assertEqual(toolbar.style_stroke_style_combo.currentData(), STROKE_STYLE_DASH)
        self.assertEqual(toolbar.style_radius_slider.value(), 8)

    def test_selecting_a_line_hides_radius_but_shows_thickness_and_style(self) -> None:
        """
        Ensures a shape type without corner radius (line) hides the Radius
        control while still showing Thickness and Style.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        annotation = _line_annotation()
        editor.canvas.set_annotations([annotation])
        self._select_only(editor, annotation)

        self.assertFalse(toolbar.style_thickness_slider.isHidden())
        self.assertFalse(toolbar.style_stroke_style_combo.isHidden())
        self.assertTrue(toolbar.style_radius_slider.isHidden())

    def test_multi_selection_hides_the_entire_style_tab(self) -> None:
        """
        Ensures selecting two or more objects hides the Style tab entirely.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        first = _rect_annotation(x=10.0)
        second = _rect_annotation(x=60.0)
        editor.canvas.set_annotations([first, second])
        for annotation in (first, second):
            editor.canvas._visible_items[annotation.annotation_id].setSelected(True)  # pylint: disable=protected-access
        editor.canvas._refresh_selection_style()  # pylint: disable=protected-access

        self.assertFalse(toolbar._property_tabs.isTabVisible(0))  # pylint: disable=protected-access

    def test_thickness_slider_edits_only_the_selected_rect(self) -> None:
        """
        Ensures dragging the Style panel's Thickness slider changes only the
        selected rectangle's stroke width.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        annotation = _rect_annotation(stroke_width=6.0)
        editor.canvas.set_annotations([annotation])
        self._select_only(editor, annotation)

        toolbar._style_thickness_changed(24)  # pylint: disable=protected-access

        item = editor.canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        self.assertEqual(int(item.pen().widthF()), 24)

    def test_radius_spin_edits_only_the_selected_rect_and_not_tool_default(self) -> None:
        """
        Ensures the Style panel's Radius spin changes only the selected
        rectangle's corner radius, leaving the Rect tool's own default
        radius untouched.
        """

        editor = self._make_editor()
        toolbar = editor._vector_toolbar  # pylint: disable=protected-access
        toolbar._rect_corner_radius = 2.0  # pylint: disable=protected-access
        annotation = _rect_annotation(payload={"corner_radius": 2.0})
        editor.canvas.set_annotations([annotation])
        self._select_only(editor, annotation)

        toolbar._style_corner_radius_changed(16.0)  # pylint: disable=protected-access

        item = editor.canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        self.assertAlmostEqual(item.corner_radius(), 16.0)
        self.assertAlmostEqual(toolbar._rect_corner_radius, 2.0)  # pylint: disable=protected-access


if __name__ == "__main__":
    unittest.main()
