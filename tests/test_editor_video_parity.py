"""
Cross-editor parity guards: catches drift between the Image editor
(src/editor_window.py) and the Video editor (src/video_vector_toolbar.py) for
shared draw-tool / drawn-object behavior. If one editor's Style-panel shape
targets or defaults-only tool popups change without a matching change to the
other, these tests fail -- per the project rule that shared editor behavior
must stay in sync between the two.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QColor, QPixmap

    import src.editor_window as editor_window
    import src.video_vector_toolbar as video_vector_toolbar
    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from src.video_editor_window import VideoEditorWindow
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

# Shape types that intentionally differ between editors, with the reason why.
# "round_rect" only exists as a legacy image-editor annotation type; the video
# vector toolbar never introduced it.
_IMAGE_ONLY_SHAPE_TYPES = frozenset({"round_rect"})


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for parity tests")
class TestStyleShapeTargetParity(unittest.TestCase):
    """
    Verifies the Style panel's shape-control eligibility sets (which
    selection types show Thickness/Style/Radius) stay the same between
    editors, aside from the documented image-only exception.
    """

    def test_thickness_selection_types_match_between_editors(self) -> None:
        image_types = editor_window._SHAPE_THICKNESS_SELECTION_TYPES  # pylint: disable=protected-access
        video_types = video_vector_toolbar._SHAPE_THICKNESS_SELECTION_TYPES  # pylint: disable=protected-access
        self.assertEqual(image_types - _IMAGE_ONLY_SHAPE_TYPES, video_types)

    def test_style_selection_types_match_between_editors(self) -> None:
        # Both editors build this set directly from the shared
        # STYLE_AWARE_TOOLS config constant (which includes "round_rect"
        # even though only the Image editor draws that shape), so no
        # image-only exception applies here.
        image_types = editor_window._SHAPE_STYLE_SELECTION_TYPES  # pylint: disable=protected-access
        video_types = video_vector_toolbar._SHAPE_STYLE_SELECTION_TYPES  # pylint: disable=protected-access
        self.assertEqual(image_types, video_types)

    def test_radius_selection_types_match_between_editors(self) -> None:
        image_types = editor_window._SHAPE_RADIUS_SELECTION_TYPES  # pylint: disable=protected-access
        video_types = video_vector_toolbar._SHAPE_RADIUS_SELECTION_TYPES  # pylint: disable=protected-access
        self.assertEqual(image_types, video_types)

    def test_both_editors_expose_the_same_style_panel_control_attribute_names(self) -> None:
        """
        Ensures both editors name their Style-panel shape controls identically,
        so shared tests/tooling can address either editor the same way.
        """

        pixmap = QPixmap(120, 90)
        pixmap.fill(QColor(230, 230, 230))
        image_window = EditorWindow(pixmap)

        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source_video = Path(tmp_dir.name) / "source.mp4"
        source_video.write_bytes(b"not-a-real-video")
        video_window = VideoEditorWindow(str(source_video), 320, 240)
        video_toolbar = video_window._vector_toolbar  # pylint: disable=protected-access

        for attr in (
            "style_thickness_slider",
            "style_thickness_label",
            "style_stroke_style_combo",
            "style_radius_slider",
            "style_radius_label",
        ):
            self.assertTrue(hasattr(image_window, attr), f"EditorWindow missing {attr}")
            self.assertTrue(hasattr(video_toolbar, attr), f"VideoVectorToolbar missing {attr}")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for parity tests")
class TestDefaultsOnlyPopupParity(unittest.TestCase):
    """
    Verifies neither editor's tool popup edits a live selection: for every
    shape/line tool both editors share, changing that tool's popup default
    while an object of that type is selected must leave the selection's
    rendered stroke width untouched in both editors.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    _SHARED_WIDTH_TOOLS = (
        Tool.RECT,
        Tool.ELLIPSE,
        Tool.TRIANGLE,
        Tool.STAR,
        Tool.LINE,
        Tool.ARROW,
        Tool.DOUBLE_ARROW,
    )
    # Tool.POLYLINE / Tool.BENT_ARROW are excluded: they render from an
    # explicit list of points in the payload, not a simple x/y/width/height
    # box, so they need dedicated point-list test fixtures instead.

    def test_image_editor_popup_never_touches_a_selected_shape(self) -> None:
        pixmap = QPixmap(140, 100)
        pixmap.fill(QColor(230, 230, 230))
        for tool in self._SHARED_WIDTH_TOOLS:
            window = EditorWindow(pixmap)
            window.canvas.load_annotations(
                [
                    AnnotationModel(
                        annotation_type=tool,
                        x=10.0,
                        y=10.0,
                        width=40.0,
                        height=20.0,
                        stroke_rgba=[255, 0, 0, 255],
                        fill_rgba=[255, 0, 0, 80],
                        stroke_width=5.0,
                    )
                ]
            )
            item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
            item.setSelected(True)

            window._apply_tool_stroke_width(30, tool=tool, persist=False)  # pylint: disable=protected-access

            self.assertEqual(
                int(item.pen().widthF()),
                5,
                msg=f"Image editor popup changed selection width for tool {tool!r}",
            )
            window.close()

    def test_video_editor_popup_never_touches_a_selected_shape(self) -> None:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source_video = Path(tmp_dir.name) / "source.mp4"
        source_video.write_bytes(b"not-a-real-video")

        for tool in self._SHARED_WIDTH_TOOLS:
            editor = VideoEditorWindow(str(source_video), 320, 240)
            toolbar = editor._vector_toolbar  # pylint: disable=protected-access
            annotation = VideoAnnotationModel(
                annotation_type=tool,
                start_ms=0,
                end_ms=5000,
                x=10.0,
                y=10.0,
                width=40.0,
                height=20.0,
                stroke_rgba=[255, 0, 0, 255],
                fill_rgba=[255, 0, 0, 80],
                stroke_width=5.0,
            )
            editor.canvas.set_annotations([annotation])
            editor.canvas._visible_items[annotation.annotation_id].setSelected(  # pylint: disable=protected-access
                True
            )

            slider = toolbar._tool_width_sliders.get(tool)  # pylint: disable=protected-access
            self.assertIsNotNone(slider, f"Video toolbar missing a width slider for tool {tool!r}")
            slider.setValue(30)

            item = editor.canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
            self.assertEqual(
                int(item.pen().widthF()),
                5,
                msg=f"Video editor popup changed selection width for tool {tool!r}",
            )


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for parity tests")
class TestEditPanelParity(unittest.TestCase):
    """
    Verifies the reworked Edit panel and selection footer behave identically in
    both editors, so a change in one cannot silently drift from the other.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _image_editor(self):
        from PySide6.QtGui import QColor, QPixmap

        from src.editor_window import EditorWindow

        pixmap = QPixmap(320, 240)
        pixmap.fill(QColor(255, 255, 255))
        window = EditorWindow(pixmap)
        self.addCleanup(window.close)
        return window

    def _video_editor(self):
        import tempfile
        from pathlib import Path

        from src.video_editor_window import VideoEditorWindow

        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source = Path(tmp_dir.name) / "source.mp4"
        source.write_bytes(b"not-a-real-video")
        editor = VideoEditorWindow(str(source), 320, 240)
        self.addCleanup(editor.close)
        return editor

    def test_both_name_the_panel_edit(self) -> None:
        """
        Ensures the tab rename reached both editors.
        """

        image_tabs = self._image_editor()._property_tabs  # pylint: disable=protected-access
        video_tabs = self._video_editor()._vector_toolbar._property_tabs  # pylint: disable=protected-access

        self.assertEqual(image_tabs.tabText(0), "Edit")
        self.assertEqual(video_tabs.tabText(0), "Edit")

    def test_both_expose_the_same_radius_range(self) -> None:
        """
        Ensures the corner radius is a 0-180 degree slider on both sides.
        """

        image = self._image_editor()
        video = self._video_editor()._vector_toolbar  # pylint: disable=protected-access

        self.assertEqual(
            (image.style_radius_slider.minimum(), image.style_radius_slider.maximum()),
            (video.style_radius_slider.minimum(), video.style_radius_slider.maximum()),
        )

    def test_both_render_the_same_footer_text(self) -> None:
        """
        Ensures one formatter drives both footers.
        """

        from src.editor_window import format_selection_info

        payload = {"type": "rect", "x": 30.0, "y": 20.4, "width": 10.0, "height": 10.0}
        expected = format_selection_info(payload)

        video = self._video_editor()
        video._on_selection_info_changed(payload)  # pylint: disable=protected-access

        self.assertEqual(video._selection_info_label.text(), expected)  # pylint: disable=protected-access
        self.assertIn("size(x/y):10x10px", expected)

    def test_video_editor_has_a_selection_footer(self) -> None:
        """
        Ensures the video editor gained the footer the image editor always had.
        """

        image = self._image_editor()
        video = self._video_editor()

        self.assertIsNotNone(image._selection_info_label)  # pylint: disable=protected-access
        self.assertIsNotNone(video._selection_info_label)  # pylint: disable=protected-access
        self.assertEqual(
            video._selection_info_label.objectName(),  # pylint: disable=protected-access
            image._selection_info_label.objectName(),  # pylint: disable=protected-access
        )

    def test_video_selection_payload_carries_geometry(self) -> None:
        """
        Ensures the video canvas reports the geometry the footer needs.

        Without it the video footer would silently render an empty summary.
        """

        from src.editor_canvas import Tool
        from src.video_models import VideoAnnotationModel

        editor = self._video_editor()
        annotation = VideoAnnotationModel(
            annotation_type=Tool.RECT,
            start_ms=0,
            end_ms=5000,
            x=30.0,
            y=20.0,
            width=10.0,
            height=10.0,
            stroke_rgba=[231, 76, 60, 255],
            fill_rgba=[231, 76, 60, 80],
            stroke_width=3.0,
        )
        editor.canvas.set_annotations([annotation])
        editor.canvas._visible_items[annotation.annotation_id].setSelected(True)  # pylint: disable=protected-access
        editor.canvas._refresh_selection_style()  # pylint: disable=protected-access

        text = editor._selection_info_label.text()  # pylint: disable=protected-access
        self.assertIn("size(x/y):10x10px", text)
        self.assertIn("pos(x/y):30x20px", text)

    def test_vertex_editing_is_shared_by_both_editors(self) -> None:
        """
        Ensures both editors build the same vertex-editable item class.

        Polyline/polygon/bent arrow come from one shared PolyPathItem, so
        vertex dragging cannot exist in one editor and not the other.
        """

        from PySide6.QtCore import QPointF

        from src.shape_items import PolyPathItem
        from src.video_canvas import build_annotation_item
        from src.video_models import VideoAnnotationModel

        annotation = VideoAnnotationModel(
            annotation_type="polyline",
            start_ms=0,
            end_ms=1000,
            x=0.0,
            y=0.0,
            width=50.0,
            height=20.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=2.0,
            payload={"points": [[0.0, 0.0], [50.0, 20.0]]},
        )
        item = build_annotation_item(annotation)

        self.assertIsInstance(item, PolyPathItem)
        self.assertEqual(item.vertex_at(QPointF(0.0, 0.0)), 0)
