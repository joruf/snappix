"""
Unit tests for multi-select annotation copy and paste.
"""

from __future__ import annotations

import json
import unittest

try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QMouseEvent, QPixmap
    from PySide6.QtWidgets import QGraphicsRectItem

    from src.annotation_items import add_annotation_to_scene
    from src.editor_canvas import (
        _ANNOTATIONS_CLIPBOARD_MIME,
        EditorCanvas,
    )
    from src.editor_window import (
        _ANNOTATIONS_CLIPBOARD_MIME as WINDOW_ANNOTATIONS_MIME,
        _CANVAS_CLIPBOARD_MIME,
        EditorWindow,
    )
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


def _solid_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates a solid pixmap for canvas tests.

    Args:
        width: Pixmap width.
        height: Pixmap height.

    Returns:
        QPixmap: Solid pixmap.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(230, 230, 230))
    return pixmap


def _add_rect(canvas: EditorCanvas, x: float, y: float) -> QGraphicsRectItem:
    """
    Adds one rectangle annotation and returns the scene item.

    Args:
        canvas: Target canvas.
        x: Scene X position.
        y: Scene Y position.

    Returns:
        QGraphicsRectItem: Created rectangle item.
    """

    item = add_annotation_to_scene(
        canvas.scene(),
        AnnotationModel(
            annotation_type="rect",
            x=x,
            y=y,
            width=40.0,
            height=30.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        ),
    )
    assert item is not None
    return item  # type: ignore[return-value]


def _local_click_event(
    canvas: EditorCanvas,
    item: QGraphicsRectItem,
    modifiers: Qt.KeyboardModifier,
) -> QMouseEvent:
    """
    Builds a left-button press event over one item center.

    Args:
        canvas: Canvas providing view mapping.
        item: Target graphics item.
        modifiers: Keyboard modifiers for the click.

    Returns:
        QMouseEvent: Local mouse press event.
    """

    view_pos = canvas.mapFromScene(item.sceneBoundingRect().center())
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(view_pos),
        QPointF(view_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for multi-select clipboard tests")
class TestEditorMultiSelectClipboard(unittest.TestCase):
    """
    Verifies Shift/Ctrl multi-select and selection clipboard transfer.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics tests.
        """

        cls._app = ensure_qapp()

    def test_shift_click_toggles_multi_selection(self) -> None:
        """
        Ensures Shift+click adds and removes annotations from the selection.
        """

        canvas = EditorCanvas()
        canvas.resize(500, 400)
        canvas.show()
        canvas.set_screenshot(_solid_pixmap(400, 300))
        first = _add_rect(canvas, 20.0, 20.0)
        second = _add_rect(canvas, 120.0, 40.0)
        canvas.scene().clearSelection()
        first.setSelected(True)

        handled = canvas._try_toggle_item_selection(  # pylint: disable=protected-access
            _local_click_event(canvas, second, Qt.KeyboardModifier.ShiftModifier)
        )
        self.assertTrue(handled)
        self.assertTrue(first.isSelected())
        self.assertTrue(second.isSelected())

        handled = canvas._try_toggle_item_selection(  # pylint: disable=protected-access
            _local_click_event(canvas, first, Qt.KeyboardModifier.ControlModifier)
        )
        self.assertTrue(handled)
        self.assertFalse(first.isSelected())
        self.assertTrue(second.isSelected())

    def test_merge_annotations_payload_preserves_relative_offset(self) -> None:
        """
        Ensures pasted selection keeps relative positions between items.
        """

        canvas = EditorCanvas()
        canvas.resize(640, 480)
        canvas.set_screenshot(_solid_pixmap(400, 300))
        source = [
            AnnotationModel(
                annotation_type="rect",
                x=10.0,
                y=10.0,
                width=20.0,
                height=20.0,
                stroke_rgba=[0, 0, 255, 255],
                fill_rgba=[0, 0, 255, 60],
                stroke_width=1.0,
            ),
            AnnotationModel(
                annotation_type="rect",
                x=50.0,
                y=10.0,
                width=20.0,
                height=20.0,
                stroke_rgba=[0, 255, 0, 255],
                fill_rgba=[0, 255, 0, 60],
                stroke_width=1.0,
            ),
        ]
        self.assertTrue(canvas.merge_annotations_payload(source))
        pasted = canvas.collect_annotations()
        self.assertEqual(len(pasted), 2)
        delta_x = pasted[1].x - pasted[0].x
        delta_y = pasted[1].y - pasted[0].y
        self.assertAlmostEqual(delta_x, 40.0, delta=1.0)
        self.assertAlmostEqual(delta_y, 0.0, delta=1.0)
        self.assertEqual(len(canvas._selected_annotation_items()), 2)  # pylint: disable=protected-access

    def test_copy_selected_annotations_prefers_selection_over_full_canvas(self) -> None:
        """
        Ensures Ctrl+C copies only the selection when annotations are selected.
        """

        from PySide6.QtGui import QGuiApplication

        window = EditorWindow(_solid_pixmap(320, 240))
        first = _add_rect(window.canvas, 30.0, 30.0)
        _add_rect(window.canvas, 140.0, 60.0)
        window.canvas.scene().clearSelection()
        first.setSelected(True)

        self.assertTrue(window.copy_selected_annotations_to_clipboard())
        mime = QGuiApplication.clipboard().mimeData()
        self.assertTrue(mime.hasFormat(WINDOW_ANNOTATIONS_MIME))
        self.assertEqual(_ANNOTATIONS_CLIPBOARD_MIME, WINDOW_ANNOTATIONS_MIME)
        payload = json.loads(bytes(mime.data(WINDOW_ANNOTATIONS_MIME)).decode("utf-8"))
        self.assertEqual(payload.get("kind"), "annotations")
        self.assertEqual(len(payload.get("annotations") or []), 1)

    def test_copy_selection_also_publishes_a_picture(self) -> None:
        """
        Ensures a copied object is usable in other applications: the clipboard
        carries a real, non-blank picture alongside Snappix's JSON payload.
        """

        from PySide6.QtGui import QGuiApplication

        window = EditorWindow(_solid_pixmap(320, 240))
        first = _add_rect(window.canvas, 30.0, 30.0)
        _add_rect(window.canvas, 140.0, 60.0)
        window.canvas.scene().clearSelection()
        first.setSelected(True)

        self.assertTrue(window.copy_selected_annotations_to_clipboard())

        mime = QGuiApplication.clipboard().mimeData()
        self.assertTrue(mime.hasImage())
        image = mime.imageData()
        self.assertGreater(image.width(), 0)
        self.assertGreater(image.height(), 0)
        opaque = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0
        )
        self.assertGreater(opaque, 0)
        # In-app paste must keep using the richer JSON payload.
        self.assertTrue(mime.hasFormat(WINDOW_ANNOTATIONS_MIME))

    def test_copy_without_selection_keeps_full_drawing_area(self) -> None:
        """
        Ensures Ctrl+C without selection still copies the full drawing area.
        """

        from PySide6.QtGui import QGuiApplication

        window = EditorWindow(_solid_pixmap(320, 240))
        _add_rect(window.canvas, 30.0, 30.0)
        _add_rect(window.canvas, 140.0, 60.0)
        window.canvas.scene().clearSelection()

        window.copy_current_image_to_clipboard()
        mime = QGuiApplication.clipboard().mimeData()
        self.assertTrue(mime.hasFormat(_CANVAS_CLIPBOARD_MIME))
        payload = json.loads(bytes(mime.data(_CANVAS_CLIPBOARD_MIME)).decode("utf-8"))
        self.assertEqual(payload.get("kind"), "canvas")
        self.assertEqual(len(payload.get("annotations") or []), 2)
        self.assertTrue(bool(payload.get("screenshot_png_base64")))
