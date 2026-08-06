"""
Regression tests for resizing styled text annotations with the handle overlay.

Text annotations exist as two item classes: the custom ``StyledTextItem`` (plain,
box, speech bubble) and legacy ``QGraphicsTextItem``. They do not share a font
setter. The resize paths called ``setFont`` unconditionally, which raised
``AttributeError`` on a ``StyledTextItem`` -- from inside a Qt virtual override,
so the process died with a segfault on the next mouse move.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont, QImage, QPixmap
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem

    from src.annotation_shapes import StyledTextItem, apply_text_item_font
    from src.editor_canvas import EditorCanvas
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int) -> QPixmap:
    """
    Creates a solid screenshot pixmap for canvas tests.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Created pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 255, 255, 255))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for styled text resize tests")
class TestApplyTextItemFont(unittest.TestCase):
    """
    Verifies the shared font setter covers both text item classes.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for graphics item tests.
        """

        cls._app = ensure_qapp()

    def test_styled_text_item_gets_the_font(self) -> None:
        """
        Ensures the custom item is fed through ``set_font`` instead of setFont.
        """

        item = StyledTextItem("hello", font=QFont("Arial", 12))
        font = QFont("Arial", 24)
        self.assertTrue(apply_text_item_font(item, font))
        self.assertEqual(item.font().pointSize(), 24)

    def test_graphics_text_item_also_updates_its_document(self) -> None:
        """
        Ensures the legacy item keeps its document default font in sync, which
        is what actually re-lays out the text.
        """

        item = QGraphicsTextItem("hello")
        font = QFont("Arial", 24)
        self.assertTrue(apply_text_item_font(item, font))
        self.assertEqual(item.font().pointSize(), 24)
        self.assertEqual(item.document().defaultFont().pointSize(), 24)

    def test_item_without_font_support_reports_failure(self) -> None:
        """
        Ensures an unexpected item type is refused instead of raising.
        """

        from PySide6.QtWidgets import QGraphicsRectItem

        self.assertFalse(apply_text_item_font(QGraphicsRectItem(), QFont("Arial", 10)))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for styled text resize tests")
class TestResizeStyledTextItem(unittest.TestCase):
    """
    Verifies both canvases resize a styled text annotation without crashing.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for canvas tests.
        """

        cls._app = ensure_qapp()

    def _styled_text_on_canvas(self):
        """
        Builds a canvas holding one selected styled text annotation.

        Returns:
            tuple[EditorCanvas, StyledTextItem]: Canvas and text item.
        """

        canvas = EditorCanvas()
        canvas.set_screenshot(_solid_pixmap(300, 200))
        item = StyledTextItem("hello", font=QFont("Arial", 12))
        item.setData(1001, "text")
        item.setPos(20.0, 30.0)
        canvas.scene().addItem(item)
        return canvas, item

    def test_handle_resize_scales_the_styled_text_font(self) -> None:
        """
        Ensures the crash path works: dragging a resize handle on a styled text
        annotation scales its font instead of raising ``AttributeError``.
        """

        canvas, item = self._styled_text_on_canvas()
        applied = canvas._resize_target_to_rect(
            item,
            QRectF(20.0, 30.0, 100.0, 40.0),
            QRectF(20.0, 30.0, 200.0, 80.0),
        )

        self.assertTrue(applied)
        self.assertGreater(item.font().pointSize(), 12)

    def test_scale_selection_scales_the_styled_text_font(self) -> None:
        """
        Ensures the keyboard/menu scale path stays working for styled text.
        """

        canvas, item = self._styled_text_on_canvas()
        item.setSelected(True)

        self.assertTrue(canvas.resize_selected_items(2.0))
        self.assertGreater(item.font().pointSize(), 12)

    def test_video_canvas_handle_resize_scales_styled_text(self) -> None:
        """
        Ensures the video editor does not carry the same crash: its text and
        callout annotations are always ``StyledTextItem``.
        """

        from src.editor_canvas import Tool
        from src.video_canvas import VideoCanvas

        canvas = VideoCanvas()
        item = StyledTextItem("hello", font=QFont("Arial", 12))
        item.setData(1001, Tool.TEXT)
        item.setPos(10.0, 10.0)
        canvas.scene().addItem(item)

        applied = canvas._resize_target_to_rect(
            item,
            QRectF(10.0, 10.0, 100.0, 40.0),
            QRectF(10.0, 10.0, 200.0, 80.0),
        )

        self.assertTrue(applied)
        self.assertGreater(item.font().pointSize(), 12)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for styled text resize tests")
class TestGeometryCallbackNeverEscapesQt(unittest.TestCase):
    """
    Verifies a failing geometry callback is contained instead of crashing Qt.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for graphics item tests.
        """

        cls._app = ensure_qapp()

    def test_raising_callback_is_logged_and_swallowed(self) -> None:
        """
        Ensures the segfault path is closed: the callback runs inside Qt virtual
        overrides, so an exception must never propagate out of it.
        """

        from src.crop_item import CropSelectionItem

        scene = QGraphicsScene()
        item = CropSelectionItem(QRectF(0.0, 0.0, 50.0, 50.0))
        scene.addItem(item)

        def boom() -> None:
            raise AttributeError("'StyledTextItem' object has no attribute 'setFont'")

        item.on_geometry_changed = boom
        with patch("src.crash_log.log_exception") as logged:
            item._notify_geometry_changed()
        logged.assert_called_once()


if __name__ == "__main__":
    unittest.main()
