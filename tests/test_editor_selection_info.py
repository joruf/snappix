"""
Unit tests for editor selection info payload and status formatting.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from PySide6.QtGui import QColor, QPixmap

    from src.annotation_shapes import TEXT_STYLE_BOX
    from src.editor_canvas import EditorCanvas
    from src.editor_window import EditorWindow, format_selection_info
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates a solid pixmap for editor window tests.

    Args:
        width: Pixmap width.
        height: Pixmap height.

    Returns:
        QPixmap: Solid pixmap.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(240, 240, 240))
    return pixmap


def _annotation_item(canvas: EditorCanvas, annotation_type: str) -> object:
    """
    Finds the first scene item for one annotation type.

    Args:
        canvas: Editor canvas instance.
        annotation_type: Annotation type key.

    Returns:
        object: Matching graphics item.
    """

    return next(
        candidate
        for candidate in canvas.scene().items()
        if str(candidate.data(1001) or "") == annotation_type
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for selection info tests")
class TestEditorSelectionInfo(unittest.TestCase):
    """
    Verifies selection payload building and status bar formatting.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics tests.
        """

        cls._app = ensure_qapp()

    def test_build_selection_payload_for_rectangle(self) -> None:
        """
        Ensures rectangle selection exposes geometry and colors.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(QPixmap(200, 150))
        canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=12.0,
                    y=18.0,
                    width=64.0,
                    height=32.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 80],
                    stroke_width=3.0,
                )
            ]
        )
        item = _annotation_item(canvas, "rect")
        item.setZValue(2.0)
        item.setSelected(True)

        payload = canvas._build_selection_payload(item)  # pylint: disable=protected-access

        self.assertEqual(payload["type"], "rect")
        self.assertEqual(payload["x"], 12.0)
        self.assertEqual(payload["y"], 18.0)
        self.assertEqual(payload["width"], 64.0)
        self.assertEqual(payload["height"], 32.0)
        self.assertEqual(payload["stroke_rgba"], [255, 0, 0, 255])
        self.assertEqual(payload["fill_rgba"], [255, 0, 0, 80])
        self.assertEqual(payload["stroke_width"], 3.0)
        self.assertEqual(payload["z_index"], 2.0)

    def test_build_selection_payload_for_step_and_styled_text(self) -> None:
        """
        Ensures step badges and styled text expose type-specific fields.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(QPixmap(220, 160))
        canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="step",
                    x=4.0,
                    y=5.0,
                    width=36.0,
                    height=36.0,
                    stroke_rgba=[255, 255, 255, 255],
                    fill_rgba=[231, 76, 60, 255],
                    stroke_width=2.0,
                    text="3",
                    payload={"step_number": 3},
                ),
                AnnotationModel(
                    annotation_type="text",
                    x=50.0,
                    y=20.0,
                    width=80.0,
                    height=30.0,
                    stroke_rgba=[20, 20, 20, 255],
                    fill_rgba=[255, 255, 255, 230],
                    stroke_width=2.0,
                    text="Callout text",
                    font_size=18,
                    font_family="Arial",
                    font_bold=True,
                    payload={"text_style": TEXT_STYLE_BOX},
                ),
            ]
        )

        step_payload = canvas._build_selection_payload(_annotation_item(canvas, "step"))  # pylint: disable=protected-access
        text_payload = canvas._build_selection_payload(_annotation_item(canvas, "text"))  # pylint: disable=protected-access

        self.assertEqual(step_payload["type"], "step")
        self.assertEqual(step_payload["step_number"], 3)
        self.assertEqual(text_payload["type"], "text")
        self.assertEqual(text_payload["text_preview"], "Callout text")
        self.assertEqual(text_payload["text_style"], TEXT_STYLE_BOX)
        self.assertEqual(text_payload["font_size"], 18)
        self.assertEqual(text_payload["font_family"], "Arial")
        self.assertTrue(text_payload["font_bold"])

    def test_format_selection_info_for_rectangle(self) -> None:
        """
        Ensures rectangle details render as a compact status summary.
        """

        summary = format_selection_info(
            {
                "type": "rect",
                "x": 12.0,
                "y": 18.0,
                "width": 64.0,
                "height": 32.0,
                "stroke_rgba": [255, 0, 0, 255],
                "fill_rgba": [255, 0, 0, 80],
                "stroke_width": 3.0,
                "z_index": 2.0,
            }
        )

        self.assertIn("Rectangle", summary)
        self.assertIn("64×32", summary)
        self.assertIn("@ 12, 18", summary)
        self.assertIn("Stroke #FF0000", summary)
        self.assertIn("Fill rgba(255,0,0,80)", summary)
        self.assertIn("3px", summary)
        self.assertIn("Layer 2", summary)

    def test_format_selection_info_multi_select_and_step(self) -> None:
        """
        Ensures multi-select count and step details appear in the summary.
        """

        multi_summary = format_selection_info(
            {
                "type": "rect",
                "x": 1.0,
                "y": 2.0,
                "width": 10.0,
                "height": 8.0,
                "count": 3,
            }
        )
        step_summary = format_selection_info(
            {
                "type": "step",
                "x": 4.0,
                "y": 5.0,
                "width": 36.0,
                "height": 36.0,
                "step_number": 7,
                "stroke_rgba": [255, 255, 255, 255],
                "fill_rgba": [231, 76, 60, 255],
                "stroke_width": 2.0,
            }
        )

        self.assertIn("Rectangle (+2 more)", multi_summary)
        self.assertIn("Step 7", step_summary)
        self.assertIn("Step", step_summary)

    def test_format_selection_info_empty_when_cleared(self) -> None:
        """
        Ensures an empty type payload produces an empty status summary.
        """

        self.assertEqual(format_selection_info({"type": ""}), "")
        self.assertEqual(format_selection_info({}), "")

    def test_format_document_info_includes_size_and_zoom(self) -> None:
        """
        Ensures document payloads render size, zoom, and annotation count.
        """

        summary = format_selection_info(
            {
                "type": "document",
                "width": 1920.0,
                "height": 1080.0,
                "zoom": 125,
                "annotation_count": 3,
            }
        )
        self.assertIn("Document", summary)
        self.assertIn("1920×1080 px", summary)
        self.assertIn("Zoom 125%", summary)
        self.assertIn("3 annotations", summary)

    def test_refresh_selection_info_emits_payload(self) -> None:
        """
        Ensures selecting an item emits a populated selection payload.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(QPixmap(200, 150))
        canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="arrow",
                    x=5.0,
                    y=6.0,
                    width=40.0,
                    height=20.0,
                    stroke_rgba=[0, 128, 255, 255],
                    fill_rgba=[0, 0, 0, 0],
                    stroke_width=2.0,
                    payload={"stroke_style": "dash"},
                )
            ]
        )
        item = _annotation_item(canvas, "arrow")
        received: list[dict] = []
        canvas.selection_style_changed.connect(received.append)
        item.setSelected(True)
        received.clear()
        canvas._refresh_selection_info()  # pylint: disable=protected-access

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["type"], "arrow")
        self.assertEqual(received[0]["stroke_style"], "dash")
        self.assertIn("Dashed", format_selection_info(received[0]))

    def test_refresh_selection_info_reports_multi_select_count(self) -> None:
        """
        Ensures multi-selection payloads include a selected item count.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(QPixmap(200, 150))
        canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=10.0,
                    y=10.0,
                    width=20.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 80],
                    stroke_width=2.0,
                ),
                AnnotationModel(
                    annotation_type="rect",
                    x=40.0,
                    y=10.0,
                    width=20.0,
                    height=20.0,
                    stroke_rgba=[0, 255, 0, 255],
                    fill_rgba=[0, 255, 0, 80],
                    stroke_width=2.0,
                ),
            ]
        )
        items = [
            candidate
            for candidate in canvas.scene().items()
            if str(candidate.data(1001) or "") == "rect"
        ]
        for item in items:
            item.setSelected(True)

        received: list[dict] = []
        canvas.selection_style_changed.connect(received.append)
        received.clear()
        canvas._refresh_selection_info()  # pylint: disable=protected-access

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["count"], 2)
        self.assertIn("(+1 more)", format_selection_info(received[0]))

    def test_selection_style_sync_does_not_recurse(self) -> None:
        """
        Ensures toolbar sync from selection does not loop through canvas updates.
        """

        window = EditorWindow(_solid_pixmap(120, 90))
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=10.0,
                    y=12.0,
                    width=30.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 80],
                    stroke_width=2.0,
                )
            ]
        )
        item = _annotation_item(window.canvas, "rect")
        emit_count = 0

        def _count_style_emits(_payload: dict) -> None:
            nonlocal emit_count
            emit_count += 1

        window.canvas.selection_style_changed.connect(_count_style_emits)
        item.setSelected(True)

        self.assertGreaterEqual(emit_count, 1)
        self.assertLess(emit_count, 5)
        self.assertIn("Rectangle", window._selection_info_label.text())  # pylint: disable=protected-access

    def test_on_selection_style_changed_does_not_apply_style_to_canvas(self) -> None:
        """
        Ensures selection-driven toolbar sync does not write back to the canvas.
        """

        window = EditorWindow(_solid_pixmap(120, 90))
        payload = {
            "type": "rect",
            "x": 1.0,
            "y": 2.0,
            "width": 10.0,
            "height": 8.0,
            "stroke_rgba": [255, 0, 0, 255],
            "fill_rgba": [255, 0, 0, 80],
            "stroke_width": 2.0,
        }

        with patch.object(window.canvas, "set_style") as set_style_mock:
            window._on_selection_style_changed(payload)  # pylint: disable=protected-access

        set_style_mock.assert_not_called()
        self.assertIn("Rectangle", window._selection_info_label.text())  # pylint: disable=protected-access

    def test_clear_selection_shows_document_footer(self) -> None:
        """
        Ensures deselecting annotations shows document size in the footer.
        """

        window = EditorWindow(_solid_pixmap(120, 90))
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=10.0,
                    y=12.0,
                    width=30.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 80],
                    stroke_width=2.0,
                )
            ]
        )
        item = _annotation_item(window.canvas, "rect")
        item.setSelected(True)
        self.assertIn("Rectangle", window._selection_info_label.text())  # pylint: disable=protected-access

        window.canvas.scene().clearSelection()
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        footer = window._selection_info_label.text()  # pylint: disable=protected-access
        self.assertIn("Document", footer)
        self.assertIn("120×90 px", footer)
        self.assertIn("1 annotation", footer)
        window.close()

    def test_document_deselect_restores_text_tool_defaults(self) -> None:
        """
        Ensures clearing the selection restores Text-tool popup defaults.
        """

        window = EditorWindow(_solid_pixmap(100, 80))
        window._text_bold_enabled = True  # pylint: disable=protected-access
        window.text_bold_button.setChecked(False)
        window._on_selection_style_changed(  # pylint: disable=protected-access
            {
                "type": "document",
                "pixel_width": 100,
                "pixel_height": 80,
                "zoom": 100,
                "annotation_count": 0,
            }
        )
        self.assertTrue(window.text_bold_button.isChecked())
        self.assertIn("Document", window._selection_info_label.text())  # pylint: disable=protected-access
        window.close()

    def test_document_payload_emitted_without_selection(self) -> None:
        """
        Ensures an empty selection emits document metadata for the footer.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(QPixmap(320, 200))
        received: list[dict] = []
        canvas.selection_style_changed.connect(received.append)
        received.clear()
        canvas._refresh_selection_info()  # pylint: disable=protected-access
        self.assertEqual(len(received), 1)
        payload = received[0]
        self.assertEqual(payload["type"], "document")
        self.assertEqual(payload["width"], 320.0)
        self.assertEqual(payload["height"], 200.0)
        self.assertEqual(payload["annotation_count"], 0)
        self.assertIn("Zoom", format_selection_info(payload))

    def test_set_style_refreshes_footer_without_recursion(self) -> None:
        """
        Ensures style updates refresh footer info without recursive selection events.
        """

        window = EditorWindow(_solid_pixmap(140, 100))
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=10.0,
                    y=12.0,
                    width=30.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 80],
                    stroke_width=2.0,
                )
            ]
        )
        item = _annotation_item(window.canvas, "rect")
        item.setSelected(True)

        style_emit_count = 0

        def _count_style_emits(_payload: dict) -> None:
            nonlocal style_emit_count
            style_emit_count += 1

        window.canvas.selection_style_changed.connect(_count_style_emits)
        style_emit_count = 0

        window.canvas.set_style(stroke_color=QColor(0, 255, 0))

        self.assertLess(style_emit_count, 5)
        self.assertIn("Stroke #00FF00", window._selection_info_label.text())  # pylint: disable=protected-access


if __name__ == "__main__":
    unittest.main()
