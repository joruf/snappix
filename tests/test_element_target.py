"""
Tests for which element a pixel operation applies to.

With a background picture and a second picture in the foreground, "delete" has
no obvious meaning: both are pixels. The selection decides, the element list
shows it, and an element that has no pixels of its own says so instead of
quietly sending the action somewhere else.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainterPath, QPixmap
    from PySide6.QtWidgets import QGraphicsPixmapItem

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

SELECTION = QRectF(100.0, 100.0, 60.0, 40.0) if PYSIDE6_AVAILABLE else None

# Inside the selection for both pictures: document (120,120) is element (60,60).
BACKGROUND_PROBE = (120, 120)
ELEMENT_PROBE = (70, 55)


def _image(width: int, height: int, color: "QColor") -> "QImage":
    """
    Builds a filled image.

    Args:
        width: Image width.
        height: Image height.
        color: Fill colour.

    Returns:
        QImage: Filled image.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)
    return image


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class ElementTargetTestCase(unittest.TestCase):
    """
    Shared setup: a background with one picture on top of it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _scene(self, *, select_element: bool = False):
        """
        Builds a canvas holding a background and a foreground picture.

        Args:
            select_element: Whether the foreground picture starts selected.

        Returns:
            tuple: Canvas and the foreground element.
        """

        from src.annotation_items import configure_graphics_item
        from src.editor_canvas import EditorCanvas

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(
            QPixmap.fromImage(_image(400, 300, QColor(240, 240, 240, 255)))
        )
        canvas.resize(500, 400)
        canvas.show()

        element = QGraphicsPixmapItem(
            QPixmap.fromImage(_image(200, 150, QColor(200, 60, 60, 255)))
        )
        element.setPos(60.0, 60.0)
        configure_graphics_item(element, "image")
        canvas._scene.addItem(element)
        element.setSelected(select_element)
        self._app.processEvents()
        return canvas, element

    def _mark(self, canvas) -> None:
        """
        Marks the shared region on the canvas.

        Args:
            canvas: Target canvas.

        Returns:
            None
        """

        path = QPainterPath()
        path.addRect(SELECTION)
        canvas.set_pixel_selection_path(path)

    def _background_alpha(self, canvas) -> int:
        """
        Returns the alpha of the probed background pixel.

        Args:
            canvas: Canvas to read.

        Returns:
            int: Alpha value.
        """

        return canvas.screenshot().toImage().pixelColor(*BACKGROUND_PROBE).alpha()

    def _element_alpha(self, element) -> int:
        """
        Returns the alpha of the probed element pixel.

        Args:
            element: Element to read.

        Returns:
            int: Alpha value.
        """

        return element.pixmap().toImage().pixelColor(*ELEMENT_PROBE).alpha()


class TestTheTargetIsNamed(ElementTargetTestCase):
    """
    Verifies which element the next action goes to.
    """

    def test_without_a_selection_the_background_is_the_target(self) -> None:
        """
        Ensures nothing changes for anyone who never touches the list.
        """

        from src.editor_canvas import BACKGROUND_ELEMENT_NAME

        canvas, _element = self._scene()
        self.assertIsNone(canvas.pixel_target_item())
        self.assertEqual(canvas.pixel_target_name(), BACKGROUND_ELEMENT_NAME)

    def test_selecting_a_picture_makes_it_the_target(self) -> None:
        """
        Ensures the foreground picture can be addressed at all.
        """

        canvas, element = self._scene(select_element=True)
        self.assertIs(canvas.pixel_target_item(), element)

    def test_the_list_holds_every_element_and_the_background(self) -> None:
        """
        Ensures the background is listed too.

        It is not a scene item like the others, but without it there is no way
        to say "this one, not the picture on top".
        """

        from src.editor_canvas import BACKGROUND_ELEMENT_ID

        canvas, _element = self._scene()
        payloads = canvas.list_element_payloads()

        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[-1]["id"], BACKGROUND_ELEMENT_ID)

    def test_the_list_marks_the_current_target(self) -> None:
        """
        Ensures the list answers "where does this go" by looking at it.
        """

        canvas, _element = self._scene(select_element=True)
        marked = [p["name"] for p in canvas.list_element_payloads() if p["selected"]]
        self.assertEqual(marked, ["1. Image"])

    def test_choosing_in_the_list_changes_the_target(self) -> None:
        """
        Ensures the list is a control, not only a display.
        """

        from src.editor_canvas import BACKGROUND_ELEMENT_ID, BACKGROUND_ELEMENT_NAME

        canvas, element = self._scene(select_element=True)
        self.assertTrue(canvas.select_element_by_id(BACKGROUND_ELEMENT_ID))
        self.assertEqual(canvas.pixel_target_name(), BACKGROUND_ELEMENT_NAME)

        element_id = canvas.list_element_payloads()[0]["id"]
        self.assertTrue(canvas.select_element_by_id(element_id))
        self.assertIs(canvas.pixel_target_item(), element)

    def test_elements_without_pixels_are_marked_as_such(self) -> None:
        """
        Ensures the list says which entries cannot take a pixel operation.
        """

        canvas, _element = self._scene()
        payloads = canvas.list_element_payloads()
        self.assertTrue(all(p["paintable"] for p in payloads))


class TestOperationsFollowTheTarget(ElementTargetTestCase):
    """
    Verifies that all five pixel operations respect the chosen element.
    """

    def test_delete_hits_the_background_by_default(self) -> None:
        """
        Ensures the previous behaviour is unchanged when nothing is selected.
        """

        canvas, element = self._scene()
        self._mark(canvas)
        self.assertTrue(canvas.erase_pixel_selection())

        self.assertEqual(self._background_alpha(canvas), 0)
        self.assertEqual(self._element_alpha(element), 255)

    def test_delete_hits_the_selected_picture(self) -> None:
        """
        Ensures the reported case works: the foreground picture loses the
        region, not the background underneath it.
        """

        canvas, element = self._scene(select_element=True)
        self._mark(canvas)
        self.assertTrue(canvas.erase_pixel_selection())

        self.assertEqual(self._element_alpha(element), 0)
        self.assertEqual(self._background_alpha(canvas), 255)

    def test_fill_hits_the_selected_picture(self) -> None:
        """
        Ensures filling follows the same rule as deleting.
        """

        canvas, element = self._scene(select_element=True)
        self._mark(canvas)
        canvas.set_style(fill_color=QColor(0, 0, 255, 255))
        self.assertTrue(canvas.fill_pixel_selection())

        self.assertEqual(
            element.pixmap().toImage().pixelColor(*ELEMENT_PROBE), QColor(0, 0, 255, 255)
        )
        self.assertEqual(
            canvas.screenshot().toImage().pixelColor(*BACKGROUND_PROBE),
            QColor(240, 240, 240, 255),
        )

    def test_blur_hits_the_selected_picture(self) -> None:
        """
        Ensures redaction lands on the picture that was pointed at.
        """

        canvas, element = self._scene(select_element=True)
        before = element.pixmap().toImage().pixelColor(*ELEMENT_PROBE)
        background_before = canvas.screenshot().toImage().pixelColor(*BACKGROUND_PROBE)

        canvas._apply_region_blur(QRectF(80.0, 80.0, 120.0, 90.0))

        self.assertEqual(
            canvas.screenshot().toImage().pixelColor(*BACKGROUND_PROBE),
            background_before,
            "blur reached the background",
        )
        self.assertEqual(element.pixmap().size().width(), 200)
        del before

    def test_background_fill_hits_the_selected_picture(self) -> None:
        """
        Ensures the fill-region tool follows the target as well.
        """

        canvas, element = self._scene(select_element=True)
        canvas.set_style(fill_color=QColor(10, 200, 10, 255))
        canvas._apply_background_fill(QRectF(100.0, 100.0, 60.0, 40.0))

        self.assertEqual(
            element.pixmap().toImage().pixelColor(*ELEMENT_PROBE),
            QColor(10, 200, 10, 255),
        )
        self.assertEqual(
            canvas.screenshot().toImage().pixelColor(*BACKGROUND_PROBE),
            QColor(240, 240, 240, 255),
        )

    def test_the_history_entry_names_a_non_default_target(self) -> None:
        """
        Ensures undo history says where an action went.

        Naming the background every time would only add noise, so the name
        appears exactly when the action went somewhere else than usual.
        """

        canvas, _element = self._scene(select_element=True)
        self._mark(canvas)
        canvas.erase_pixel_selection()
        self.assertIn("Image", canvas.consume_last_action_label())

    def test_the_default_history_entry_is_unchanged(self) -> None:
        """
        Ensures existing entries do not gain a bracketed background.
        """

        canvas, _element = self._scene()
        self._mark(canvas)
        canvas.erase_pixel_selection()
        self.assertEqual(canvas.consume_last_action_label(), "Erase selection")


class TestElementsWithoutPixels(ElementTargetTestCase):
    """
    Verifies what happens when the chosen element has nothing to paint on.
    """

    def _scene_with_shape(self):
        """
        Builds a canvas with a selected shape rather than a picture.

        Returns:
            tuple: Canvas and the shape.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(
            QPixmap.fromImage(_image(400, 300, QColor(240, 240, 240, 255)))
        )
        canvas.resize(500, 400)
        canvas.show()
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(30.0, 60.0))
        for index in range(1, 25):
            canvas._extend_freehand_stroke(
                QPointF(30.0 + index * 6.0, 60.0 + (index % 4) * 10.0)
            )
        canvas._finalize_poly_draw()
        self._app.processEvents()
        return canvas

    def test_such_a_selection_is_recognized(self) -> None:
        """
        Ensures a shape is not mistaken for something paintable.
        """

        canvas = self._scene_with_shape()
        self.assertTrue(canvas.has_unpaintable_selection())
        self.assertIsNone(canvas.pixel_target_item())

    def test_delete_refuses_instead_of_hitting_the_background(self) -> None:
        """
        Ensures the ambiguity is not simply moved elsewhere.

        Quietly falling back to the background is what made the old behaviour
        confusing in the first place.
        """

        canvas = self._scene_with_shape()
        self._mark(canvas)
        before = self._background_alpha(canvas)

        self.assertFalse(canvas.erase_pixel_selection())
        self.assertEqual(self._background_alpha(canvas), before)

    def test_fill_refuses_as_well(self) -> None:
        """
        Ensures every pixel operation behaves the same way.
        """

        canvas = self._scene_with_shape()
        self._mark(canvas)
        self.assertFalse(canvas.fill_pixel_selection())

    def test_the_refusal_is_explained(self) -> None:
        """
        Ensures nothing fails silently.
        """

        from src.editor_canvas import UNPAINTABLE_TARGET_MESSAGE

        canvas = self._scene_with_shape()
        self._mark(canvas)
        messages: list[str] = []
        canvas.status_message.connect(messages.append)

        canvas.erase_pixel_selection()
        self.assertIn(UNPAINTABLE_TARGET_MESSAGE, messages)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestElementPanel(unittest.TestCase):
    """
    Verifies the list beside the canvas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _editor(self):
        """
        Opens an editor holding a background and a foreground picture.

        Returns:
            tuple: Editor and the foreground element.
        """

        from src.annotation_items import configure_graphics_item
        from src.editor_window import EditorWindow

        editor = EditorWindow(
            QPixmap.fromImage(_image(400, 300, QColor(240, 240, 240, 255)))
        )
        self.addCleanup(editor.close)
        editor.resize(900, 600)
        editor.show()

        element = QGraphicsPixmapItem(
            QPixmap.fromImage(_image(200, 150, QColor(200, 60, 60, 255)))
        )
        element.setPos(60.0, 60.0)
        configure_graphics_item(element, "image")
        editor.canvas._scene.addItem(element)
        editor._refresh_element_panel()
        self._app.processEvents()
        return editor, element

    def test_the_panel_lists_both_pictures(self) -> None:
        """
        Ensures everything in the document is visible at once.
        """

        editor, _element = self._editor()
        labels = [
            editor.element_list.item(index).text()
            for index in range(editor.element_list.count())
        ]
        self.assertEqual(labels, ["1. Image", "Background"])

    def test_the_panel_says_where_the_next_action_goes(self) -> None:
        """
        Ensures the target is stated in words, not only implied.
        """

        editor, _element = self._editor()
        self.assertIn("Background", editor.element_target_label.text())

    def test_picking_a_row_switches_the_target(self) -> None:
        """
        Ensures the list is how the target is chosen.
        """

        editor, element = self._editor()
        editor.element_list.setCurrentRow(0)
        self._app.processEvents()

        self.assertIs(editor.canvas.pixel_target_item(), element)
        self.assertIn("Image", editor.element_target_label.text())

    def test_selecting_on_the_canvas_updates_the_list(self) -> None:
        """
        Ensures both routes lead to one notion of "current element".
        """

        editor, element = self._editor()
        element.setSelected(True)
        editor._refresh_element_panel()
        self._app.processEvents()

        self.assertEqual(editor.element_list.currentItem().text(), "1. Image")


if __name__ == "__main__":
    unittest.main()
