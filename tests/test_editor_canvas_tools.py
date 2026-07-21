"""
Unit tests for editor canvas blur, step, duplicate, z-order, and OCR tools.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import QRectF, QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QMouseEvent, QPixmap

    from src.annotation_shapes import StepBadgeItem
    from src.editor_canvas import EditorCanvas, Tool
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _checkerboard_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates a checkerboard pixmap for blur verification.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Checkerboard pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    for x_index in range(width):
        for y_index in range(height):
            color = QColor(255, 0, 0) if (x_index + y_index) % 2 == 0 else QColor(0, 0, 255)
            image.setPixelColor(x_index, y_index, color)
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for editor canvas tool tests")
class TestEditorCanvasTools(unittest.TestCase):
    """
    Verifies advanced editor canvas tool behavior.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics tests.
        """

        cls._app = ensure_qapp()

    def _canvas_with_rect(self) -> tuple[EditorCanvas, object]:
        """
        Creates a canvas with one selectable rectangle annotation.

        Returns:
            tuple[EditorCanvas, object]: Canvas and rectangle item.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_checkerboard_pixmap(200, 150))
        canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=30.0,
                    y=40.0,
                    width=50.0,
                    height=40.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[255, 0, 0, 80],
                    stroke_width=2.0,
                )
            ]
        )
        item = next(
            candidate
            for candidate in canvas.scene().items()
            if str(candidate.data(1001) or "") == "rect"
        )
        return canvas, item

    def test_blur_block_size_clamps_to_supported_range(self) -> None:
        """
        Ensures blur block size stays within configured limits.
        """

        canvas = EditorCanvas()
        canvas.set_blur_block_size(2)
        self.assertEqual(canvas.blur_block_size(), 4)
        canvas.set_blur_block_size(128)
        self.assertEqual(canvas.blur_block_size(), 64)

    def test_apply_region_blur_modifies_screenshot(self) -> None:
        """
        Ensures blur tool pixelates the target screenshot region.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_checkerboard_pixmap(80, 80))
        canvas.set_blur_block_size(8)
        before = canvas.screenshot().toImage().pixelColor(20, 20)
        canvas._apply_region_blur(QRectF(10.0, 10.0, 30.0, 30.0))  # pylint: disable=protected-access
        after = canvas.screenshot().toImage().pixelColor(20, 20)
        self.assertNotEqual(before.red(), after.red())

    def test_duplicate_selected_items_creates_offset_copy(self) -> None:
        """
        Ensures duplicate creates a second annotation with offset position.
        """

        canvas, item = self._canvas_with_rect()
        item.setSelected(True)
        before_count = len(canvas.collect_annotations())

        duplicated = canvas.duplicate_selected_items()
        after = canvas.collect_annotations()

        self.assertTrue(duplicated)
        self.assertEqual(len(after), before_count + 1)
        positions = sorted((annotation.x, annotation.y) for annotation in after)
        self.assertEqual(positions[0], (30.0, 40.0))
        self.assertEqual(positions[1], (46.0, 56.0))

    def test_duplicate_selected_items_returns_false_without_selection(self) -> None:
        """
        Ensures duplicate reports failure when nothing is selected.
        """

        canvas, _item = self._canvas_with_rect()
        self.assertFalse(canvas.duplicate_selected_items())

    def test_z_order_changes_raise_selected_item(self) -> None:
        """
        Ensures bring forward increases z-value of selected items.
        """

        canvas, item = self._canvas_with_rect()
        item.setSelected(True)
        before_z = item.zValue()
        canvas.bring_selected_forward()
        self.assertGreater(item.zValue(), before_z)

    def test_bring_selected_to_front_places_item_on_top(self) -> None:
        """
        Ensures bring to front sets highest z-value among annotations.
        """

        canvas, item = self._canvas_with_rect()
        item.setSelected(True)
        canvas.bring_selected_to_front()
        max_z = max(
            candidate.zValue()
            for candidate in canvas.scene().items()
            if str(candidate.data(1001) or "")
        )
        self.assertEqual(item.zValue(), max_z)

    def test_annotation_item_at_view_pos_detects_drawn_element(self) -> None:
        """
        Ensures context-menu hit testing resolves drawable annotations.
        """

        canvas, item = self._canvas_with_rect()
        item.setSelected(False)
        center = item.sceneBoundingRect().center()
        view_point = canvas.mapFromScene(center)

        resolved = canvas._annotation_item_at_view_pos(view_point)  # pylint: disable=protected-access

        self.assertIs(resolved, item)

    def test_reset_step_counter_and_insert_step(self) -> None:
        """
        Ensures step counter reset and step tool insert numbered badges.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_checkerboard_pixmap(120, 80))
        canvas.reset_step_counter(4)
        canvas.set_tool(Tool.STEP)
        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(60.0, 40.0),
            QPointF(60.0, 40.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        canvas.mousePressEvent(press_event)

        step_items = [
            candidate
            for candidate in canvas.scene().items()
            if isinstance(candidate, StepBadgeItem)
        ]
        self.assertEqual(len(step_items), 1)
        self.assertEqual(step_items[0].step_number(), 4)

    @patch("src.editor_canvas.extract_text_from_png_bytes", return_value="Detected text")
    @patch("src.editor_canvas.QGuiApplication")
    def test_run_ocr_on_region_copies_text_to_clipboard(
        self,
        mock_gui_app: MagicMock,
        _mock_extract: MagicMock,
    ) -> None:
        """
        Ensures OCR copies recognized text to the clipboard.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_checkerboard_pixmap(100, 60))
        clipboard = MagicMock()
        mock_gui_app.clipboard.return_value = clipboard

        canvas._run_ocr_on_region(QRectF(10.0, 10.0, 40.0, 30.0))  # pylint: disable=protected-access

        clipboard.setText.assert_called_once_with("Detected text")
