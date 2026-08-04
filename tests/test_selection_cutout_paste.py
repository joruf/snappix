"""
Tests for copying a marked region and pasting it as a reusable cutout.
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap

from tests.qt_test_utils import ensure_qapp


def _tab(color: str = "#FFFFFF"):
    """
    Builds one editor tab holding a red square at (50, 50, 80, 80).

    Args:
        color: Background color of the document.

    Returns:
        EditorWindow: The editor window.
    """

    from src.editor_window import EditorWindow

    pixmap = QPixmap(400, 300)
    pixmap.fill(QColor(color))
    painter = QPainter(pixmap)
    painter.fillRect(50, 50, 80, 80, QColor("#E5484D"))
    painter.end()
    return EditorWindow(pixmap)


class CutoutCopyTests(unittest.TestCase):
    """
    Class CutoutCopyTests

    Covers Ctrl+C honouring a pixel selection over the whole drawing area.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        self.window = _tab()
        path = QPainterPath()
        path.addRect(QRectF(50.0, 50.0, 80.0, 80.0))
        self.window.canvas.set_pixel_selection_path(path)

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        self.window.close()

    def test_cutout_matches_the_selection_bounds(self) -> None:
        """
        Returns:
            None
        """

        cutout = self.window.canvas.copy_pixel_selection_pixmap()
        self.assertEqual((cutout.width(), cutout.height()), (80, 80))

    def test_cutout_carries_the_selected_pixels(self) -> None:
        """
        Returns:
            None
        """

        cutout = self.window.canvas.copy_pixel_selection_pixmap()
        self.assertEqual(cutout.toImage().pixelColor(40, 40).name(), "#e5484d")

    def test_copy_puts_the_cutout_on_the_clipboard(self) -> None:
        """
        Returns:
            None
        """

        self.assertTrue(self.window.copy_pixel_selection_to_clipboard())
        clipboard = QGuiApplication.clipboard().pixmap()
        self.assertEqual((clipboard.width(), clipboard.height()), (80, 80))

    def test_copy_prefers_the_selection_over_the_whole_tab(self) -> None:
        """
        Ctrl+C with a marked region must not fall through to copying the entire
        drawing area, which is what it did before.

        Returns:
            None
        """

        self.window.copy_current_image_to_clipboard()
        clipboard = QGuiApplication.clipboard().pixmap()
        self.assertEqual((clipboard.width(), clipboard.height()), (80, 80))

    def test_without_a_selection_there_is_no_cutout(self) -> None:
        """
        Returns:
            None
        """

        self.window.canvas.clear_pixel_selection()
        self.assertTrue(self.window.canvas.copy_pixel_selection_pixmap().isNull())
        self.assertFalse(self.window.copy_pixel_selection_to_clipboard())

    def test_cutout_follows_the_stored_selection_path(self) -> None:
        """
        The cutout is clipped to whatever ``pixel_selection_path`` reports.

        Note this app normalizes pixel selections to a rectangle, so an ellipse
        handed to ``set_pixel_selection_path`` comes back as its bounding box --
        the cutout is rectangular by consequence, not by choice. The clip is
        still applied, which is what keeps this correct if the selection model
        ever gains real shapes.

        Returns:
            None
        """

        path = QPainterPath()
        path.addEllipse(QRectF(50.0, 50.0, 80.0, 80.0))
        self.window.canvas.set_pixel_selection_path(path)
        stored = self.window.canvas.pixel_selection_path().boundingRect()
        cutout = self.window.canvas.copy_pixel_selection_pixmap()
        self.assertEqual(cutout.width(), round(stored.width()))
        self.assertEqual(cutout.height(), round(stored.height()))


class MultiPasteTests(unittest.TestCase):
    """
    Class MultiPasteTests

    Covers repeated Ctrl+V producing separate, visible copies.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        self.window = _tab()
        path = QPainterPath()
        path.addRect(QRectF(50.0, 50.0, 80.0, 80.0))
        self.window.canvas.set_pixel_selection_path(path)
        self.window.copy_pixel_selection_to_clipboard()

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        self.window.close()

    def test_each_paste_adds_one_copy(self) -> None:
        """
        Returns:
            None
        """

        before = len(self.window.canvas.collect_annotations())
        for _ in range(3):
            self.window.canvas.paste_from_clipboard()
        self.assertEqual(len(self.window.canvas.collect_annotations()), before + 3)

    def test_repeated_pastes_do_not_stack_on_one_spot(self) -> None:
        """
        Without a cascade every copy lands on the same point and only the last
        one is visible, which looks like paste doing nothing.

        Returns:
            None
        """

        for _ in range(3):
            self.window.canvas.paste_from_clipboard()
        placed = self.window.canvas.collect_annotations()[-3:]
        positions = {(round(item.x), round(item.y)) for item in placed}
        self.assertEqual(len(positions), 3)

    def test_cascade_restarts_for_different_content(self) -> None:
        """
        Returns:
            None
        """

        first = QPixmap(10, 10)
        second = QPixmap(20, 20)
        canvas = self.window.canvas
        canvas.paste_cascade_offset(first)
        stepped = canvas.paste_cascade_offset(first)
        self.assertGreater(stepped.x(), 0.0)
        restarted = canvas.paste_cascade_offset(second)
        self.assertEqual(restarted.x(), 0.0)

    def test_cutout_pastes_into_another_tab(self) -> None:
        """
        Returns:
            None
        """

        other = _tab("#EEEEEE")
        try:
            before = len(other.canvas.collect_annotations())
            other.canvas.paste_from_clipboard()
            self.assertEqual(len(other.canvas.collect_annotations()), before + 1)
        finally:
            other.close()


class SelectAllTests(unittest.TestCase):
    """
    Class SelectAllTests

    Covers Ctrl+A marking the whole drawing area, so the familiar
    select-all/copy/paste sequence still yields the entire tab.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        self.window = _tab()

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        self.window.close()

    def test_select_all_marks_the_whole_document(self) -> None:
        """
        Returns:
            None
        """

        self.window.select_entire_drawing_area()
        document = self.window.canvas.document_rect().toRect()
        marked = self.window.canvas.pixel_selection_path().boundingRect()
        self.assertTrue(self.window.canvas.has_pixel_selection())
        self.assertEqual(round(marked.width()), document.width())
        self.assertEqual(round(marked.height()), document.height())

    def test_select_all_then_copy_yields_the_whole_tab(self) -> None:
        """
        The point of the feature: Copy honours the selection, so selecting all
        is what reproduces the old "copy the entire drawing area".

        Returns:
            None
        """

        self.window.select_entire_drawing_area()
        self.window.copy_current_image_to_clipboard()
        document = self.window.canvas.document_rect().toRect()
        clipboard = QGuiApplication.clipboard().pixmap()
        self.assertEqual(clipboard.width(), document.width())
        self.assertEqual(clipboard.height(), document.height())

    def test_copied_area_keeps_its_content(self) -> None:
        """
        Returns:
            None
        """

        self.window.select_entire_drawing_area()
        self.window.copy_current_image_to_clipboard()
        clipboard = QGuiApplication.clipboard().pixmap()
        self.assertEqual(clipboard.toImage().pixelColor(90, 90).name(), "#e5484d")

    def test_whole_area_pastes_repeatedly(self) -> None:
        """
        Returns:
            None
        """

        self.window.select_entire_drawing_area()
        self.window.copy_current_image_to_clipboard()
        before = len(self.window.canvas.collect_annotations())
        for _ in range(2):
            self.window.canvas.paste_from_clipboard()
        self.assertEqual(len(self.window.canvas.collect_annotations()), before + 2)

    def test_whole_area_pastes_into_another_tab(self) -> None:
        """
        Returns:
            None
        """

        self.window.select_entire_drawing_area()
        self.window.copy_current_image_to_clipboard()
        other = _tab("#EEEEEE")
        try:
            other.canvas.paste_from_clipboard()
            self.assertEqual(len(other.canvas.collect_annotations()), 1)
        finally:
            other.close()


class ClipboardImageTests(unittest.TestCase):
    """
    Class ClipboardImageTests

    Covers reading an image back out of clipboard MIME data.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        self.window = _tab()

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        self.window.close()

    def test_clipboard_image_is_read_via_image_data(self) -> None:
        """
        QMimeData exposes imageData(); image() belongs to QClipboard. Calling
        the wrong one raised AttributeError and broke every image paste.

        Returns:
            None
        """

        source = QPixmap(30, 20)
        source.fill(QColor("#3B82F6"))
        QGuiApplication.clipboard().setPixmap(source)

        mime = QGuiApplication.clipboard().mimeData()
        pixmap = self.window.canvas._pixmap_from_clipboard(mime)  # pylint: disable=protected-access

        self.assertIsNotNone(pixmap)
        self.assertEqual((pixmap.width(), pixmap.height()), (30, 20))


if __name__ == "__main__":
    unittest.main()
