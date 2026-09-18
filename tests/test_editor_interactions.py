"""
Tests for four editor interactions: importing into the current document,
two-finger zoom, Escape dropping a selection, and cutting a region out of one
element.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
    from PySide6.QtGui import (
        QColor,
        QImage,
        QKeyEvent,
        QNativeGestureEvent,
        QPainterPath,
        QPixmap,
        QPointingDevice,
        QWheelEvent,
    )
    from PySide6.QtWidgets import QGraphicsPixmapItem, QMenu

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _pixmap(width: int, height: int, color: "QColor | None" = None) -> "QPixmap":
    """
    Builds a filled pixmap.

    Args:
        width: Image width.
        height: Image height.
        color: Optional fill colour.

    Returns:
        QPixmap: Filled pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color or QColor(235, 235, 235, 255))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestImportIsFindable(unittest.TestCase):
    """
    Verifies importing into the current document is offered where it is sought.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _editor(self):
        """
        Opens an editor window.

        Returns:
            EditorWindow: Editor under test.
        """

        from src.editor_window import EditorWindow

        editor = EditorWindow(_pixmap(200, 150))
        self.addCleanup(editor.close)
        return editor

    def _menus_holding(self, editor, action) -> list[str]:
        """
        Returns the titles of every menu containing one action.

        Args:
            editor: Editor window.
            action: Action to look for.

        Returns:
            list[str]: Menu titles.
        """

        return [
            menu.title()
            for menu in editor.findChildren(QMenu)
            if action in menu.actions()
        ]

    def test_import_sits_in_the_file_menu(self) -> None:
        """
        Ensures it is found next to the "as new tab" variant.

        Only that variant lived in File, so importing into the open document
        looked as though it did not exist.
        """

        editor = self._editor()
        self.assertIn("File", self._menus_holding(editor, editor._import_image_action))

    def test_the_familiar_place_still_works(self) -> None:
        """
        Ensures the Edit menu keeps the entry rather than losing it.
        """

        editor = self._editor()
        self.assertIn("Edit", self._menus_holding(editor, editor._import_image_action))

    def test_both_menus_share_one_action(self) -> None:
        """
        Ensures the two entries cannot drift apart.
        """

        editor = self._editor()
        self.assertEqual(
            len(self._menus_holding(editor, editor._import_image_action)), 2
        )

    def test_the_tab_variant_is_still_offered(self) -> None:
        """
        Ensures the new entry did not displace the existing one.
        """

        editor = self._editor()
        titles = [
            action.text()
            for menu in editor.findChildren(QMenu)
            if menu.title() == "File"
            for action in menu.actions()
        ]
        self.assertIn("Import Image as New Tab...", titles)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestTwoFingerZoom(unittest.TestCase):
    """
    Verifies pinch zoom.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas(self):
        """
        Builds a canvas showing a document.

        Returns:
            EditorCanvas: Canvas under test.
        """

        from src.editor_canvas import EditorCanvas

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300))
        canvas.resize(500, 400)
        canvas.show()
        self._app.processEvents()
        return canvas

    def _pinch(self, canvas, value: float) -> None:
        """
        Sends one pinch step.

        Args:
            canvas: Target canvas.
            value: Reported zoom change; positive spreads the fingers.

        Returns:
            None
        """

        event = QNativeGestureEvent(
            Qt.NativeGestureType.ZoomNativeGesture,
            QPointingDevice.primaryPointingDevice(),
            QPointF(200.0, 150.0),
            QPointF(200.0, 150.0),
            QPointF(200.0, 150.0),
            value,
            0,
            0,
        )
        self._app.sendEvent(canvas, event)

    def test_spreading_the_fingers_zooms_in(self) -> None:
        """
        Ensures the gesture reaches the canvas at all.
        """

        canvas = self._canvas()
        before = canvas._zoom_factor
        self._pinch(canvas, 0.25)
        self.assertGreater(canvas._zoom_factor, before)

    def test_closing_the_fingers_zooms_out(self) -> None:
        """
        Ensures the gesture works in both directions.
        """

        canvas = self._canvas()
        self._pinch(canvas, 0.5)
        before = canvas._zoom_factor
        self._pinch(canvas, -0.3)
        self.assertLess(canvas._zoom_factor, before)

    def test_a_tiny_pinch_is_ignored(self) -> None:
        """
        Ensures the picture does not shimmer under the stream of near-zero
        values a touchpad reports while the fingers rest.
        """

        canvas = self._canvas()
        before = canvas._zoom_factor
        self._pinch(canvas, 0.0005)
        self.assertEqual(canvas._zoom_factor, before)

    def test_zoom_stays_within_its_limits(self) -> None:
        """
        Ensures a long pinch cannot leave the supported range.
        """

        canvas = self._canvas()
        for _ in range(60):
            self._pinch(canvas, 0.5)
        self.assertLessEqual(canvas._zoom_factor, canvas.ZOOM_MAX)

        for _ in range(120):
            self._pinch(canvas, -0.5)
        self.assertGreaterEqual(canvas._zoom_factor, canvas.ZOOM_MIN)

    def test_ctrl_and_wheel_zoom_too(self) -> None:
        """
        Ensures the common touchpad mapping works.

        Many Linux touchpads report a pinch as Ctrl plus a wheel step rather
        than as a gesture, so the canvas would otherwise scroll instead.
        """

        canvas = self._canvas()
        before = canvas._zoom_factor
        event = QWheelEvent(
            QPointF(200.0, 150.0),
            QPointF(200.0, 150.0),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        self._app.sendEvent(canvas.viewport(), event)
        self.assertGreater(canvas._zoom_factor, before)

    def test_the_video_canvas_zooms_the_same_way(self) -> None:
        """
        Ensures both editors gained the gesture, not just one.
        """

        from src.video_canvas import VideoCanvas

        canvas = VideoCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.resize(400, 300)
        canvas.show()
        self._app.processEvents()

        before = canvas._zoom_factor
        self._pinch(canvas, 0.3)
        self.assertGreater(canvas._zoom_factor, before)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestEscapeDeselects(unittest.TestCase):
    """
    Verifies Escape drops a selection.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas_with_selected_stroke(self):
        """
        Builds a canvas holding one selected annotation.

        Returns:
            EditorCanvas: Canvas under test.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300))
        canvas.resize(500, 400)
        canvas.show()
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(30.0, 60.0))
        for index in range(1, 30):
            canvas._extend_freehand_stroke(
                QPointF(30.0 + index * 5.0, 60.0 + (index % 4) * 10.0)
            )
        canvas._finalize_poly_draw()
        self._app.processEvents()
        return canvas

    def _escape(self, canvas) -> None:
        """
        Sends one Escape key press.

        Args:
            canvas: Target canvas.

        Returns:
            None
        """

        canvas.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Escape,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        self._app.processEvents()

    def test_escape_clears_the_selection(self) -> None:
        """
        Ensures a selected element can be let go of with the key that means
        "never mind" everywhere else.
        """

        canvas = self._canvas_with_selected_stroke()
        self.assertEqual(len(canvas._scene.selectedItems()), 1)

        self._escape(canvas)
        self.assertEqual(canvas._scene.selectedItems(), [])

    def test_escape_does_not_delete_anything(self) -> None:
        """
        Ensures deselecting is not confused with removing.
        """

        canvas = self._canvas_with_selected_stroke()
        self._escape(canvas)
        self.assertEqual(len(canvas.collect_annotations()), 1)

    def test_a_pending_crop_is_cancelled_first(self) -> None:
        """
        Ensures the existing meanings of Escape keep their turn.

        Backing out of something in progress has to come before dropping a
        selection, otherwise Escape would strand a half-made crop.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300))
        canvas.set_tool(Tool.CROP)
        self.assertTrue(canvas.has_pending_crop())

        self._escape(canvas)
        self.assertFalse(canvas.has_pending_crop())

    def test_a_pixel_selection_is_cleared_first(self) -> None:
        """
        Ensures a marked region is released before element selections.
        """

        from src.editor_canvas import EditorCanvas

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300))
        path = QPainterPath()
        path.addRect(QRectF(20.0, 20.0, 80.0, 60.0))
        canvas.set_pixel_selection_path(path)

        self._escape(canvas)
        self.assertFalse(canvas.has_pixel_selection())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCutOutOfElement(unittest.TestCase):
    """
    Verifies removing part of one element.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas_with_element(self, *, selected: bool = True):
        """
        Builds a canvas with one image element on it.

        Args:
            selected: Whether the element starts selected.

        Returns:
            tuple: Canvas and the element.
        """

        from src.annotation_items import configure_graphics_item
        from src.editor_canvas import EditorCanvas

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300, QColor(240, 240, 240, 255)))
        canvas.resize(500, 400)
        canvas.show()

        element = QGraphicsPixmapItem(_pixmap(200, 150, QColor(200, 60, 60, 255)))
        element.setPos(60.0, 60.0)
        configure_graphics_item(element, "image")
        canvas._scene.addItem(element)
        element.setSelected(selected)
        self._app.processEvents()
        return canvas, element

    def _mark(self, canvas, rect: QRectF) -> None:
        """
        Marks one region on the canvas.

        Args:
            canvas: Target canvas.
            rect: Region in document coordinates.

        Returns:
            None
        """

        path = QPainterPath()
        path.addRect(rect)
        canvas.set_pixel_selection_path(path)

    def test_the_marked_region_is_removed_from_the_element(self) -> None:
        """
        Ensures the cut lands on the element that was selected.
        """

        canvas, element = self._canvas_with_element()
        self._mark(canvas, QRectF(100.0, 100.0, 60.0, 40.0))

        self.assertTrue(canvas.cut_selection_from_selected_item())
        result = element.pixmap().toImage()
        self.assertEqual(result.pixelColor(70, 55).alpha(), 0)

    def test_the_rest_of_the_element_is_untouched(self) -> None:
        """
        Ensures only the marked part goes.
        """

        canvas, element = self._canvas_with_element()
        self._mark(canvas, QRectF(100.0, 100.0, 60.0, 40.0))
        canvas.cut_selection_from_selected_item()

        result = element.pixmap().toImage()
        self.assertEqual(result.pixelColor(5, 5), QColor(200, 60, 60, 255))

    def test_the_picture_underneath_is_untouched(self) -> None:
        """
        Ensures this is not the existing erase, which works on the background.
        """

        canvas, _element = self._canvas_with_element()
        self._mark(canvas, QRectF(100.0, 100.0, 60.0, 40.0))
        canvas.cut_selection_from_selected_item()

        background = canvas.screenshot().toImage()
        self.assertEqual(background.pixelColor(120, 120).alpha(), 255)

    def test_an_element_that_moved_is_still_cut_correctly(self) -> None:
        """
        Ensures the marked region is matched in document terms.

        The mark describes the document; the element may sit anywhere, so the
        two have to be brought into the same coordinates.
        """

        canvas, element = self._canvas_with_element()
        element.setPos(150.0, 40.0)
        self._app.processEvents()
        self._mark(canvas, QRectF(200.0, 80.0, 40.0, 30.0))
        canvas.cut_selection_from_selected_item()

        result = element.pixmap().toImage()
        self.assertEqual(result.pixelColor(70, 55).alpha(), 0, "cut missed the mark")
        self.assertEqual(result.pixelColor(5, 5).alpha(), 255)

    def test_nothing_happens_without_a_marked_region(self) -> None:
        """
        Ensures a selected element alone does not lose pixels.
        """

        canvas, _element = self._canvas_with_element()
        self.assertFalse(canvas.can_cut_from_selected_item())
        self.assertFalse(canvas.cut_selection_from_selected_item())

    def test_nothing_happens_without_a_selected_element(self) -> None:
        """
        Ensures the background is not cut by accident.
        """

        canvas, _element = self._canvas_with_element(selected=False)
        self._mark(canvas, QRectF(100.0, 100.0, 60.0, 40.0))

        self.assertIsNone(canvas.selected_cuttable_item())
        self.assertFalse(canvas.cut_selection_from_selected_item())

    def test_an_ambiguous_selection_is_refused(self) -> None:
        """
        Ensures two selected elements do not silently cut only one of them.
        """

        from src.annotation_items import configure_graphics_item

        canvas, element = self._canvas_with_element()
        second = QGraphicsPixmapItem(_pixmap(80, 60, QColor(40, 80, 160, 255)))
        second.setPos(250.0, 30.0)
        configure_graphics_item(second, "image")
        canvas._scene.addItem(second)
        second.setSelected(True)
        self._app.processEvents()

        self.assertIsNone(canvas.selected_cuttable_item())

    def test_the_mark_is_released_afterwards(self) -> None:
        """
        Ensures the next action does not silently repeat the cut.
        """

        canvas, _element = self._canvas_with_element()
        self._mark(canvas, QRectF(100.0, 100.0, 60.0, 40.0))
        canvas.cut_selection_from_selected_item()

        self.assertFalse(canvas.has_pixel_selection())


if __name__ == "__main__":
    unittest.main()
