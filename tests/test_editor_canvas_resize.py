"""
Unit tests for selected element resize behavior.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.editor_canvas import EditorCanvas, Tool
    from src.storage import pixmap_to_base64_png
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates a solid screenshot pixmap used by canvas tests.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Created pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 255, 255, 255))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for canvas resize tests")
class TestEditorCanvasResize(unittest.TestCase):
    """
    Verifies geometry resize behavior for selected annotations.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics tests.
        """

        cls._app = ensure_qapp()

    def _canvas_with_item(self, annotation: AnnotationModel):
        """
        Creates a canvas with one loaded annotation.

        Args:
            annotation: Annotation to load.

        Returns:
            tuple[EditorCanvas, object]: Canvas and first scene item.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_solid_pixmap(300, 200))
        canvas.load_annotations([annotation])
        scene_item = None
        for candidate in canvas.scene().items():
            if str(candidate.data(1001) or ""):
                scene_item = candidate
                break
        self.assertIsNotNone(scene_item)
        return canvas, scene_item

    def test_resize_selected_rectangle_updates_geometry(self) -> None:
        """
        Ensures rectangle width and height change after resize.
        """

        annotation = AnnotationModel(
            annotation_type="rect",
            x=40.0,
            y=50.0,
            width=60.0,
            height=40.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas, item = self._canvas_with_item(annotation)
        before = item.rect()
        item.setSelected(True)

        changed = canvas.resize_selected_items(1.5)
        after = item.rect()

        self.assertTrue(changed)
        self.assertGreater(after.width(), before.width())
        self.assertGreater(after.height(), before.height())

    def test_resize_selected_line_updates_length(self) -> None:
        """
        Ensures line length changes after resize.
        """

        annotation = AnnotationModel(
            annotation_type="line",
            x=20.0,
            y=30.0,
            width=80.0,
            height=0.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=2.0,
        )
        canvas, item = self._canvas_with_item(annotation)
        before_length = item.line().length()
        item.setSelected(True)

        changed = canvas.resize_selected_items(0.5)
        after_length = item.line().length()

        self.assertTrue(changed)
        self.assertLess(after_length, before_length)

    def test_resize_selected_text_updates_font_size(self) -> None:
        """
        Ensures text font size changes after resize.
        """

        annotation = AnnotationModel(
            annotation_type="text",
            x=15.0,
            y=15.0,
            width=20.0,
            height=10.0,
            stroke_rgba=[0, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=1.0,
            text="Resize me",
            font_size=18,
            font_family="Sans Serif",
        )
        canvas, item = self._canvas_with_item(annotation)
        before_size = item.font().pointSize()
        item.setSelected(True)

        changed = canvas.resize_selected_items(1.2)
        after_size = item.font().pointSize()

        self.assertTrue(changed)
        self.assertGreater(after_size, before_size)

    def test_resize_returns_false_without_selection(self) -> None:
        """
        Ensures resize call does nothing when nothing is selected.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_solid_pixmap(100, 80))
        self.assertFalse(canvas.resize_selected_items(1.1))

    def test_selection_creates_resize_overlay(self) -> None:
        """
        Ensures selecting a drawable item creates visible resize handles.
        """

        annotation = AnnotationModel(
            annotation_type="rect",
            x=20.0,
            y=20.0,
            width=40.0,
            height=30.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas, item = self._canvas_with_item(annotation)
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access

        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        self.assertGreater(overlay.scene_rect().width(), 0)
        self.assertGreater(overlay.scene_rect().height(), 0)

    def test_resize_overlay_geometry_updates_target(self) -> None:
        """
        Ensures dragging resize handles updates target rectangle size.
        """

        annotation = AnnotationModel(
            annotation_type="rect",
            x=30.0,
            y=25.0,
            width=50.0,
            height=30.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas, item = self._canvas_with_item(annotation)
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access
        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        assert overlay is not None

        before_width = item.sceneBoundingRect().width()
        before_height = item.sceneBoundingRect().height()
        overlay.setRect(0.0, 0.0, 90.0, 70.0)
        canvas._apply_resize_overlay_to_target()  # pylint: disable=protected-access
        after_width = item.sceneBoundingRect().width()
        after_height = item.sceneBoundingRect().height()

        self.assertGreater(after_width, before_width)
        self.assertGreater(after_height, before_height)

    def test_line_overlay_resize_updates_line_extent(self) -> None:
        """
        Ensures line resize follows overlay extent changes.
        """

        annotation = AnnotationModel(
            annotation_type="line",
            x=20.0,
            y=40.0,
            width=100.0,
            height=0.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=2.0,
        )
        canvas, item = self._canvas_with_item(annotation)
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access
        overlay = canvas._resize_overlay_item  # pylint: disable=protected-access
        self.assertIsNotNone(overlay)
        assert overlay is not None

        before_rect = item.sceneBoundingRect()
        overlay.setRect(0.0, 0.0, 160.0, 40.0)
        canvas._apply_resize_overlay_to_target()  # pylint: disable=protected-access
        after_rect = item.sceneBoundingRect()

        self.assertGreater(after_rect.width(), before_rect.width())

    def test_selection_clear_removes_resize_overlay(self) -> None:
        """
        Ensures resize overlay is removed when selection is cleared.
        """

        annotation = AnnotationModel(
            annotation_type="rect",
            x=10.0,
            y=10.0,
            width=30.0,
            height=20.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas, item = self._canvas_with_item(annotation)
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access
        self.assertIsNotNone(canvas._resize_overlay_item)  # pylint: disable=protected-access

        canvas.scene().clearSelection()
        canvas._on_selection_changed()  # pylint: disable=protected-access
        self.assertIsNone(canvas._resize_overlay_item)  # pylint: disable=protected-access

    def test_collect_annotations_excludes_resize_overlay(self) -> None:
        """
        Ensures overlay helper item is never persisted as annotation.
        """

        annotation = AnnotationModel(
            annotation_type="rect",
            x=12.0,
            y=18.0,
            width=35.0,
            height=22.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas, item = self._canvas_with_item(annotation)
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access

        collected = canvas.collect_annotations()
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0].annotation_type, "rect")

    def test_resize_selected_image_updates_scale(self) -> None:
        """
        Ensures image annotation scale changes after resize action.
        """

        image_annotation = AnnotationModel(
            annotation_type="image",
            x=40.0,
            y=25.0,
            width=30.0,
            height=20.0,
            stroke_rgba=[0, 0, 0, 0],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=0.0,
            payload={"image_png_base64": pixmap_to_base64_png(_solid_pixmap(30, 20))},
        )
        canvas, item = self._canvas_with_item(image_annotation)
        before_width = item.sceneBoundingRect().width()
        item.setSelected(True)

        changed = canvas.resize_selected_items(1.4)
        after_width = item.sceneBoundingRect().width()

        self.assertTrue(changed)
        self.assertGreater(after_width, before_width)

    def test_set_tool_updates_cursor_shape(self) -> None:
        """
        Ensures cursor shape follows active tool changes.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_solid_pixmap(150, 100))

        canvas.set_tool(Tool.SELECT)
        self.assertEqual(canvas.viewport().cursor().shape(), Qt.CursorShape.ArrowCursor)

        canvas.set_tool(Tool.TEXT)
        self.assertEqual(canvas.viewport().cursor().shape(), Qt.CursorShape.IBeamCursor)

        canvas.set_tool(Tool.RECT)
        self.assertEqual(canvas.viewport().cursor().shape(), Qt.CursorShape.CrossCursor)

    def test_crop_keeps_annotations_editable(self) -> None:
        """
        Ensures annotations remain editable after cropping.
        """

        annotation = AnnotationModel(
            annotation_type="rect",
            x=60.0,
            y=40.0,
            width=80.0,
            height=50.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        canvas, _item = self._canvas_with_item(annotation)

        canvas._apply_crop(QRectF(20.0, 20.0, 180.0, 120.0))  # pylint: disable=protected-access
        annotations_after_crop = canvas.collect_annotations()

        self.assertEqual(len(annotations_after_crop), 1)
        self.assertEqual(annotations_after_crop[0].annotation_type, "rect")

        resized_item = None
        for candidate in canvas.scene().items():
            if str(candidate.data(1001) or "") == "rect":
                resized_item = candidate
                break
        self.assertIsNotNone(resized_item)
        resized_item.setSelected(True)

        changed = canvas.resize_selected_items(1.25)
        self.assertTrue(changed)

