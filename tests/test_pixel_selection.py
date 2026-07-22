"""
Unit tests for pixel selection, wand, flatten, brush, and bucket tools.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.editor_canvas import (
        ERASE_MODE_FILL,
        ERASE_MODE_TRANSPARENT,
        EditorCanvas,
    )
    from src.models import AnnotationModel
    from src.pixel_selection import (
        build_wand_mask_image,
        colors_match,
        ellipse_selection_path,
        mask_has_selection,
        paint_path_on_image,
        polygon_selection_path,
        rect_selection_path,
    )
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_image(width: int, height: int, color: QColor) -> QImage:
    """
    Creates a solid ARGB image.

    Args:
        width: Image width.
        height: Image height.
        color: Fill color.

    Returns:
        QImage: Solid image.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)
    return image


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for pixel selection tests")
class TestPixelSelectionHelpers(unittest.TestCase):
    """
    Verifies wand matching and path helpers.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_colors_match_respects_tolerance(self) -> None:
        """
        Ensures color matching uses the configured tolerance.
        """

        self.assertTrue(colors_match(QColor(10, 10, 10), QColor(20, 10, 10), 10))
        self.assertFalse(colors_match(QColor(10, 10, 10), QColor(30, 10, 10), 10))

    def test_wand_contiguous_selects_connected_region_only(self) -> None:
        """
        Ensures contiguous wand does not jump across gaps.
        """

        image = _solid_image(20, 10, QColor(255, 0, 0))
        for x_pos in range(12, 20):
            for y_pos in range(10):
                image.setPixelColor(x_pos, y_pos, QColor(0, 0, 255))
        mask = build_wand_mask_image(image, 1, 1, tolerance=0, contiguous=True)
        self.assertTrue(mask_has_selection(mask))
        self.assertNotEqual(mask.pixelColor(2, 2).alpha(), 0)
        self.assertEqual(mask.pixelColor(15, 2).alpha(), 0)

    def test_wand_global_selects_all_matching_colors(self) -> None:
        """
        Ensures non-contiguous wand selects all matching pixels.
        """

        image = _solid_image(20, 10, QColor(0, 255, 0))
        image.setPixelColor(1, 1, QColor(255, 0, 0))
        image.setPixelColor(18, 8, QColor(255, 0, 0))
        mask = build_wand_mask_image(image, 1, 1, tolerance=0, contiguous=False)
        self.assertNotEqual(mask.pixelColor(1, 1).alpha(), 0)
        self.assertNotEqual(mask.pixelColor(18, 8).alpha(), 0)
        self.assertEqual(mask.pixelColor(5, 5).alpha(), 0)

    def test_selection_path_builders(self) -> None:
        """
        Ensures rect, ellipse, and polygon builders produce non-empty paths.
        """

        rect_path = rect_selection_path(QRectF(2, 3, 10, 8))
        ellipse_path = ellipse_selection_path(QRectF(2, 3, 10, 8))
        polygon_path = polygon_selection_path(
            [QPointF(0, 0), QPointF(10, 0), QPointF(5, 8)]
        )
        self.assertFalse(rect_path.isEmpty())
        self.assertFalse(ellipse_path.isEmpty())
        self.assertFalse(polygon_path.isEmpty())
        self.assertTrue(polygon_selection_path([QPointF(0, 0), QPointF(1, 1)]).isEmpty())

    def test_paint_path_erase_transparent(self) -> None:
        """
        Ensures erase mode clears alpha inside the clip path.
        """

        image = _solid_image(20, 20, QColor(255, 0, 0, 255))
        path = rect_selection_path(QRectF(2, 2, 6, 6))
        result = paint_path_on_image(
            image,
            path,
            QColor(0, 0, 0, 0),
            erase_transparent=True,
        )
        self.assertEqual(result.pixelColor(4, 4).alpha(), 0)
        self.assertEqual(result.pixelColor(15, 15).alpha(), 255)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for canvas pixel tool tests")
class TestEditorCanvasPixelTools(unittest.TestCase):
    """
    Verifies flatten, mask erase, brush, and bucket on the editor canvas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas_with_rect_annotation(self) -> EditorCanvas:
        """
        Creates a canvas with one rectangle annotation.

        Returns:
            EditorCanvas: Prepared canvas.
        """

        canvas = EditorCanvas()
        pixmap = QPixmap(100, 80)
        pixmap.fill(QColor(40, 40, 40))
        canvas.set_screenshot(pixmap)
        canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=10.0,
                    y=10.0,
                    width=30.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 120],
                    stroke_width=2.0,
                )
            ]
        )
        return canvas

    def test_flatten_burns_annotations_into_screenshot(self) -> None:
        """
        Ensures flatten clears annotations and changes the background.
        """

        canvas = self._canvas_with_rect_annotation()
        before = canvas.screenshot().toImage().copy()
        self.assertEqual(len(canvas.collect_annotations()), 1)
        canvas.flatten_annotations()
        self.assertEqual(len(canvas.collect_annotations()), 0)
        after = canvas.screenshot().toImage()
        self.assertNotEqual(before.pixelColor(20, 20), after.pixelColor(20, 20))

    def test_erase_selection_transparent_and_fill(self) -> None:
        """
        Ensures Delete erase modes modify only the selected region.
        """

        canvas = EditorCanvas()
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor(10, 20, 30, 255))
        canvas.set_screenshot(pixmap)
        canvas.set_pixel_selection_path(rect_selection_path(QRectF(5, 5, 10, 10)))
        canvas.set_erase_mode(ERASE_MODE_TRANSPARENT)
        self.assertTrue(canvas.erase_pixel_selection())
        self.assertEqual(canvas.screenshot().toImage().pixelColor(8, 8).alpha(), 0)
        self.assertEqual(canvas.screenshot().toImage().pixelColor(30, 30).alpha(), 255)

        canvas.set_style(fill_color=QColor(0, 255, 0, 255))
        canvas.set_pixel_selection_path(rect_selection_path(QRectF(20, 20, 8, 8)))
        canvas.set_erase_mode(ERASE_MODE_FILL)
        self.assertTrue(canvas.erase_pixel_selection())
        self.assertEqual(canvas.screenshot().toImage().pixelColor(22, 22), QColor(0, 255, 0, 255))

    def test_bucket_requires_selection_brush_does_not(self) -> None:
        """
        Ensures Fill needs a mask while Brush paints freehand without one.
        """

        canvas = EditorCanvas()
        pixmap = QPixmap(50, 50)
        pixmap.fill(QColor(255, 255, 255))
        canvas.set_screenshot(pixmap)
        canvas.set_style(
            fill_color=QColor(255, 0, 0, 255),
            stroke_color=QColor(0, 0, 255, 255),
            stroke_width=4.0,
        )
        self.assertFalse(canvas.fill_pixel_selection())
        canvas.set_pixel_selection_path(rect_selection_path(QRectF(5, 5, 20, 20)))
        self.assertTrue(canvas.fill_pixel_selection())
        self.assertEqual(canvas.screenshot().toImage().pixelColor(10, 10), QColor(255, 0, 0, 255))
        self.assertEqual(canvas.screenshot().toImage().pixelColor(40, 40), QColor(255, 255, 255, 255))

        canvas.clear_pixel_selection()
        canvas._paint_brush_segment(QPointF(40.0, 40.0), QPointF(40.0, 40.0))  # pylint: disable=protected-access
        self.assertEqual(canvas.screenshot().toImage().pixelColor(40, 40).blue(), 255)

    def test_brush_paints_freehand_dot(self) -> None:
        """
        Ensures a brush click (zero-length segment) leaves visible paint without a selection.
        """

        canvas = EditorCanvas()
        pixmap = QPixmap(60, 60)
        pixmap.fill(QColor(255, 255, 255))
        canvas.set_screenshot(pixmap)
        canvas.set_style(stroke_color=QColor(0, 128, 0, 255), stroke_width=8.0)
        canvas._paint_brush_segment(QPointF(20.0, 20.0), QPointF(20.0, 20.0))  # pylint: disable=protected-access
        self.assertEqual(canvas.screenshot().toImage().pixelColor(20, 20), QColor(0, 128, 0, 255))
        self.assertTrue(canvas._brush_stroke_dirty)  # pylint: disable=protected-access
        self.assertEqual(canvas.screenshot().toImage().pixelColor(50, 50), QColor(255, 255, 255, 255))

    def test_brush_respects_width_and_optional_selection_clip(self) -> None:
        """
        Ensures brush size follows Width and clips when a selection exists.
        """

        canvas = EditorCanvas()
        pixmap = QPixmap(80, 80)
        pixmap.fill(QColor(255, 255, 255))
        canvas.set_screenshot(pixmap)
        canvas.set_style(stroke_color=QColor(0, 0, 255, 255), stroke_width=2.0)
        canvas.set_pixel_selection_path(rect_selection_path(QRectF(10, 10, 20, 20)))
        canvas._paint_brush_segment(QPointF(15.0, 15.0), QPointF(15.0, 15.0))  # pylint: disable=protected-access
        self.assertEqual(canvas.screenshot().toImage().pixelColor(15, 15).blue(), 255)
        self.assertEqual(canvas.screenshot().toImage().pixelColor(50, 50), QColor(255, 255, 255, 255))

    def test_escape_clears_pixel_selection(self) -> None:
        """
        Ensures Esc clears an active pixel selection.
        """

        from PySide6.QtGui import QKeyEvent

        canvas = EditorCanvas()
        pixmap = QPixmap(30, 30)
        pixmap.fill(QColor(100, 100, 100))
        canvas.set_screenshot(pixmap)
        canvas.set_pixel_selection_path(rect_selection_path(QRectF(2, 2, 8, 8)))
        self.assertTrue(canvas.has_pixel_selection())
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        canvas.keyPressEvent(event)
        self.assertFalse(canvas.has_pixel_selection())

    def test_wand_tool_sets_selection(self) -> None:
        """
        Ensures magic wand creates a selection from a seed click.
        """

        canvas = EditorCanvas()
        image = _solid_image(40, 40, QColor(0, 0, 0))
        for x_pos in range(5, 15):
            for y_pos in range(5, 15):
                image.setPixelColor(x_pos, y_pos, QColor(200, 50, 50))
        canvas.set_screenshot(QPixmap.fromImage(image))
        canvas.set_wand_tolerance(5)
        canvas.set_wand_contiguous(True)
        canvas._apply_wand_at(QPointF(8.0, 8.0), add=False)  # pylint: disable=protected-access
        self.assertTrue(canvas.has_pixel_selection())
        self.assertTrue(canvas.pixel_selection_path().contains(QPointF(8.0, 8.0)))


if __name__ == "__main__":
    unittest.main()
