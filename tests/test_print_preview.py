"""
Tests for the print preview dialog.

The preview shows a sheet of paper with the picture on it. These tests drive it
the way a person does -- dragging the picture, pulling a corner, typing a size,
pressing Print -- and check the result where it matters: in the PDF that comes
out, rendered back and looked at.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QSize, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtTest import QTest

    from src.print_preview_dialog import PDF_PRINTER, PrintPreviewDialog
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

BLUE = QColor(30, 90, 220)
SAVE_AS = "src.print_preview_dialog.QFileDialog.getSaveFileName"


def _picture(width: int = 600, height: int = 400) -> "QPixmap":
    """
    Builds a blue picture with a white corner marker.

    Args:
        width: Width in pixels.
        height: Height in pixels.

    Returns:
        QPixmap: The picture.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(BLUE)
    return pixmap


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class PreviewCase(unittest.TestCase):
    """
    Shared setup: a shown dialog on a landscape picture.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Opens the dialog.
        """

        self.dialog = PrintPreviewDialog(_picture())
        self.addCleanup(self._dispose)
        self.dialog.show()
        self._app.processEvents()
        self.model = self.dialog.layout_model

    def _dispose(self) -> None:
        """
        Frees the dialog so later tests are not slowed down.
        """

        self.dialog.close()
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _view_point(self, scene_point: QPointF) -> QPoint:
        """
        Converts a point on the sheet into a point in the preview's viewport.

        Args:
            scene_point: Position in sheet millimetres.

        Returns:
            QPoint: Position in the viewport.
        """

        return self.dialog._view.mapFromScene(scene_point)

    def _drag(self, start: QPointF, end: QPointF) -> None:
        """
        Drags with the left mouse button from one sheet position to another.

        Args:
            start: Sheet position to press at.
            end: Sheet position to release at.
        """

        viewport = self.dialog._view.viewport()
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self._view_point(start))
        middle = (start + end) / 2.0
        for point in (middle, end):
            QTest.mouseMove(viewport, self._view_point(point))
            self._app.processEvents()
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self._view_point(end))
        self._app.processEvents()

    def _print_pdf(self, path: Path) -> bool:
        """
        Presses Print with the PDF printer chosen.

        Args:
            path: File the stubbed save dialog answers with.

        Returns:
            bool: True when the dialog was accepted.
        """

        index = self.dialog.printer_combo.findData(PDF_PRINTER)
        self.dialog.printer_combo.setCurrentIndex(index)
        with patch(SAVE_AS, return_value=(str(path), "PDF (*.pdf)")):
            QTest.mouseClick(self.dialog.print_button, Qt.MouseButton.LeftButton)
        self._app.processEvents()
        return self.dialog.result() == self.dialog.DialogCode.Accepted

    @staticmethod
    def _render_pdf(path: Path, dpi: int = 72) -> "QImage":
        """
        Renders the first page of a PDF.

        Args:
            path: PDF file.
            dpi: Resolution to render at.

        Returns:
            QImage: The page.
        """

        document = QPdfDocument()
        document.load(str(path))
        points = document.pagePointSize(0)
        size = QSize(round(points.width() * dpi / 72), round(points.height() * dpi / 72))
        rendered = document.render(0, size)
        # The renderer leaves the paper transparent; put it on white, as a
        # printer would find it.
        page = QImage(size, QImage.Format.Format_RGB32)
        page.fill(QColor(255, 255, 255))
        painter = QPainter(page)
        painter.drawImage(0, 0, rendered)
        painter.end()
        return page


class TestOpening(PreviewCase):
    """
    Verifies what the dialog shows first.
    """

    def test_it_opens_on_a_portrait_a4_sheet(self) -> None:
        """
        Ensures the sheet is A4, upright.
        """

        self.assertEqual(self.dialog.paper_combo.currentData(), "A4")
        self.assertTrue(self.dialog.portrait_radio.isChecked())
        self.assertEqual(self.model.page_size_mm, (210.0, 297.0))
        self.assertEqual(self.dialog._page.rect().width(), 210.0)
        self.assertEqual(self.dialog._page.rect().height(), 297.0)

    def test_the_picture_starts_fitted_and_centred(self) -> None:
        """
        Ensures nobody has to place it before a first print.
        """

        self.assertTrue(self.model.is_fitted())
        item = self.dialog._image_item
        self.assertAlmostEqual(item.pos().x(), self.model.x_mm)
        self.assertAlmostEqual(item.pos().y(), self.model.y_mm)
        self.assertAlmostEqual(item.scale() * 600, self.model.width_mm)

    def test_the_fields_show_the_placement(self) -> None:
        """
        Ensures the fields agree with the picture.
        """

        self.assertAlmostEqual(self.dialog.width_spin.value(), self.model.width_mm, places=1)
        self.assertAlmostEqual(self.dialog.height_spin.value(), self.model.height_mm, places=1)
        self.assertAlmostEqual(self.dialog.x_spin.value(), self.model.x_mm, places=1)
        self.assertAlmostEqual(self.dialog.y_spin.value(), self.model.y_mm, places=1)

    def test_the_whole_sheet_is_in_view(self) -> None:
        """
        Ensures the preview shows the sheet, not a corner of it.
        """

        visible = self.dialog._view.mapToScene(self.dialog._view.viewport().rect()).boundingRect()

        self.assertTrue(visible.contains(self.dialog._page.rect()))

    def test_every_offered_paper_is_listed(self) -> None:
        """
        Ensures the usual sizes are there.
        """

        names = [self.dialog.paper_combo.itemData(i) for i in range(self.dialog.paper_combo.count())]

        self.assertEqual(names, ["A3", "A4", "A5", "Letter", "Legal"])

    def test_pdf_is_always_a_choice_of_printer(self) -> None:
        """
        Ensures printing is possible on a machine without a printer.
        """

        data = [self.dialog.printer_combo.itemData(i) for i in range(self.dialog.printer_combo.count())]

        self.assertIn(PDF_PRINTER, data)


class TestPaper(PreviewCase):
    """
    Verifies the paper and orientation controls.
    """

    def test_landscape_turns_the_sheet(self) -> None:
        """
        Ensures the drawn sheet follows the choice.
        """

        self.dialog.landscape_radio.setChecked(True)

        self.assertEqual(self.dialog._page.rect().width(), 297.0)
        self.assertEqual(self.dialog._page.rect().height(), 210.0)

    def test_another_paper_resizes_the_sheet(self) -> None:
        """
        Ensures the drawn sheet follows the paper size.
        """

        self.dialog.paper_combo.setCurrentIndex(self.dialog.paper_combo.findData("A5"))

        self.assertEqual(self.dialog._page.rect().width(), 148.0)
        self.assertEqual(self.dialog._page.rect().height(), 210.0)

    def test_the_printable_border_is_drawn_inside_the_sheet(self) -> None:
        """
        Ensures the dashed margin sits inside the paper.
        """

        printable = self.dialog._printable.rect()

        self.assertTrue(self.dialog._page.rect().contains(printable))
        self.assertAlmostEqual(printable.left(), self.model.margin_mm)

    def test_the_picture_stays_on_the_sheet_when_it_is_turned(self) -> None:
        """
        Ensures turning the sheet cannot lose the picture.
        """

        self.dialog.landscape_radio.setChecked(True)
        scene_rect = self.dialog._image_item.sceneBoundingRect()

        self.assertTrue(self.dialog._page.rect().contains(scene_rect))


class TestPlacing(PreviewCase):
    """
    Verifies dragging, resizing and typing.
    """

    def test_dragging_the_picture_moves_it(self) -> None:
        """
        Ensures a drag changes where the picture is, and the fields follow.
        """

        before = QPointF(self.model.x_mm, self.model.y_mm)
        centre = self.dialog._image_item.sceneBoundingRect().center()

        self._drag(centre, centre + QPointF(20.0, 15.0))

        self.assertAlmostEqual(self.model.x_mm, before.x() + 20.0, delta=1.5)
        self.assertAlmostEqual(self.model.y_mm, before.y() + 15.0, delta=1.5)
        self.assertAlmostEqual(self.dialog.x_spin.value(), self.model.x_mm, places=1)
        self.assertAlmostEqual(self.dialog.y_spin.value(), self.model.y_mm, places=1)

    def test_a_dragged_picture_is_no_longer_called_fitted(self) -> None:
        """
        Ensures the model notices the user took over.
        """

        centre = self.dialog._image_item.sceneBoundingRect().center()
        self._drag(centre, centre + QPointF(12.0, 0.0))

        self.assertFalse(self.model.is_fitted())

    def test_pulling_a_corner_resizes_with_the_same_proportions(self) -> None:
        """
        Ensures the handle changes the size and the shape stays.
        """

        self.dialog.width_spin.setValue(80.0)
        self.dialog.x_spin.setValue(40.0)
        self.dialog.y_spin.setValue(60.0)
        self._app.processEvents()
        rect = self.model.rect_mm
        corner = QPointF(rect[0] + rect[2], rect[1] + rect[3])

        self._drag(corner, corner + QPointF(30.0, 30.0))

        after = self.model.rect_mm
        self.assertGreater(after[2], rect[2] + 10.0)
        self.assertAlmostEqual(after[2] / after[3], 1.5, places=3)
        self.assertAlmostEqual(after[0], rect[0], delta=0.01)
        self.assertAlmostEqual(after[1], rect[1], delta=0.01)

    def test_the_handles_sit_on_the_corners_of_the_picture(self) -> None:
        """
        Ensures all four handles follow the picture.
        """

        x, y, width, height = self.model.rect_mm
        handles = self.dialog._handles

        self.assertAlmostEqual(handles["tl"].pos().x(), x)
        self.assertAlmostEqual(handles["br"].pos().x(), x + width)
        self.assertAlmostEqual(handles["bl"].pos().y(), y + height)
        self.assertAlmostEqual(handles["tr"].pos().y(), y)

    def test_a_typed_width_resizes_and_updates_the_height(self) -> None:
        """
        Ensures the height field follows, keeping the shape.
        """

        self.dialog.width_spin.setValue(90.0)

        self.assertAlmostEqual(self.model.width_mm, 90.0)
        self.assertAlmostEqual(self.dialog.height_spin.value(), 60.0, places=1)
        self.assertAlmostEqual(self.dialog._image_item.scale() * 600, 90.0)

    def test_a_typed_height_resizes_and_updates_the_width(self) -> None:
        """
        Ensures the width field follows.
        """

        self.dialog.height_spin.setValue(60.0)

        self.assertAlmostEqual(self.model.height_mm, 60.0)
        self.assertAlmostEqual(self.dialog.width_spin.value(), 90.0, places=1)

    def test_a_typed_position_moves_the_picture(self) -> None:
        """
        Ensures the position fields move the picture on the sheet.
        """

        self.dialog.x_spin.setValue(33.0)
        self.dialog.y_spin.setValue(44.0)

        self.assertAlmostEqual(self.dialog._image_item.pos().x(), 33.0)
        self.assertAlmostEqual(self.dialog._image_item.pos().y(), 44.0)

    def test_the_buttons_place_the_picture(self) -> None:
        """
        Ensures Fit, Fill, Original size and Center do what they say.
        """

        self.dialog.width_spin.setValue(50.0)
        self.dialog.x_spin.setValue(0.0)
        self.dialog.y_spin.setValue(0.0)

        QTest.mouseClick(self.dialog.center_button, Qt.MouseButton.LeftButton)
        self.assertAlmostEqual(self.model.x_mm, (210.0 - 50.0) / 2)

        QTest.mouseClick(self.dialog.fill_button, Qt.MouseButton.LeftButton)
        self.assertGreaterEqual(self.model.height_mm, 277.0 - 1e-6)

        QTest.mouseClick(self.dialog.fit_button, Qt.MouseButton.LeftButton)
        self.assertTrue(self.model.is_fitted())

        QTest.mouseClick(self.dialog.original_button, Qt.MouseButton.LeftButton)
        self.assertAlmostEqual(self.model.width_mm, 600 / 96 * 25.4)


class TestPrinting(PreviewCase):
    """
    Verifies what actually comes out.
    """

    def test_print_writes_a_pdf_of_the_chosen_paper(self) -> None:
        """
        Ensures an A4 portrait sheet comes out as A4 portrait.
        """

        with TemporaryDirectory() as directory:
            target = Path(directory) / "out.pdf"
            accepted = self._print_pdf(target)
            data = target.read_bytes()

        self.assertTrue(accepted)
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertRegex(data.decode("latin-1"), r"/MediaBox\s*\[\s*0\s+0\s+595(\.\d+)?\s+842(\.\d+)?")

    def test_landscape_comes_out_landscape(self) -> None:
        """
        Ensures the orientation reaches the printer.
        """

        self.dialog.landscape_radio.setChecked(True)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "out.pdf"
            self._print_pdf(target)
            text = target.read_bytes().decode("latin-1")

        match = re.search(r"/MediaBox\s*\[\s*0\s+0\s+(\d+)(?:\.\d+)?\s+(\d+)", text)
        self.assertIsNotNone(match)
        self.assertGreater(int(match.group(1)), int(match.group(2)))

    def test_another_paper_reaches_the_printer(self) -> None:
        """
        Ensures A3 is A3 on paper, not A4.
        """

        self.dialog.paper_combo.setCurrentIndex(self.dialog.paper_combo.findData("A3"))
        with TemporaryDirectory() as directory:
            target = Path(directory) / "out.pdf"
            self._print_pdf(target)
            text = target.read_bytes().decode("latin-1")

        match = re.search(r"/MediaBox\s*\[\s*0\s+0\s+(\d+)(?:\.\d+)?\s+(\d+)", text)
        self.assertEqual((int(match.group(1)), int(match.group(2))), (842, 1191))

    def test_the_picture_lands_where_the_preview_shows_it(self) -> None:
        """
        Ensures the printed page matches the sheet: blue inside the placement,
        white everywhere else.
        """

        self.dialog.width_spin.setValue(100.0)
        self.dialog.x_spin.setValue(40.0)
        self.dialog.y_spin.setValue(60.0)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "out.pdf"
            self._print_pdf(target)
            page = self._render_pdf(target, dpi=72)

        points_per_mm = 72 / 25.4
        x, y, width, height = self.model.rect_mm

        def pixel(x_mm: float, y_mm: float) -> QColor:
            return QColor(page.pixel(round(x_mm * points_per_mm), round(y_mm * points_per_mm)))

        inside = pixel(x + width / 2, y + height / 2)
        self.assertLess(abs(inside.blue() - BLUE.blue()), 12)
        self.assertLess(inside.red(), 80)
        for outside in ((x - 6, y + height / 2), (x + width + 6, y + height / 2), (x + width / 2, y - 6), (x + width / 2, y + height + 6)):
            colour = pixel(*outside)
            self.assertGreater(colour.red(), 240, f"{outside} should be paper")
        edge_left = pixel(x + 1.5, y + height / 2)
        edge_right = pixel(x + width - 1.5, y + height / 2)
        self.assertLess(edge_left.red(), 80)
        self.assertLess(edge_right.red(), 80)

    def test_the_printed_size_matches_the_preview(self) -> None:
        """
        Ensures 100 mm in the preview are 100 mm on the paper.
        """

        self.dialog.width_spin.setValue(100.0)
        self.dialog.x_spin.setValue(30.0)
        self.dialog.y_spin.setValue(30.0)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "out.pdf"
            self._print_pdf(target)
            page = self._render_pdf(target, dpi=150)

        blue_columns = [
            x for x in range(page.width()) if QColor(page.pixel(x, int(60 * 150 / 25.4))).red() < 90
        ]
        measured_mm = (blue_columns[-1] - blue_columns[0] + 1) * 25.4 / 150

        self.assertAlmostEqual(measured_mm, 100.0, delta=1.0)

    def test_the_number_of_copies_reaches_the_printer(self) -> None:
        """
        Ensures the Copies field is not decoration.
        """

        self.dialog.copies_spin.setValue(3)
        self.dialog.printer_combo.setCurrentIndex(self.dialog.printer_combo.findData(PDF_PRINTER))
        with patch(SAVE_AS, return_value=("/tmp/unused-copies-test.pdf", "PDF (*.pdf)")):
            printer = self.dialog.build_printer()

        self.assertEqual(printer.copyCount(), 3)

    def test_cancelling_the_file_dialog_prints_nothing(self) -> None:
        """
        Ensures backing out of the PDF file name keeps the preview open.
        """

        self.dialog.printer_combo.setCurrentIndex(self.dialog.printer_combo.findData(PDF_PRINTER))
        with patch(SAVE_AS, return_value=("", "")):
            QTest.mouseClick(self.dialog.print_button, Qt.MouseButton.LeftButton)

        self.assertNotEqual(self.dialog.result(), self.dialog.DialogCode.Accepted)

    def test_a_pdf_name_without_an_extension_gets_one(self) -> None:
        """
        Ensures the file is recognisably a PDF.
        """

        with TemporaryDirectory() as directory:
            bare = Path(directory) / "output"
            self._print_pdf(bare)
            exists = bare.with_suffix(".pdf").is_file()

        self.assertTrue(exists)

    def test_cancel_closes_without_printing(self) -> None:
        """
        Ensures Cancel is a way out.
        """

        QTest.mouseClick(self.dialog.cancel_button, Qt.MouseButton.LeftButton)

        self.assertEqual(self.dialog.result(), self.dialog.DialogCode.Rejected)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestEditorEntry(unittest.TestCase):
    """
    Verifies the editor opens this preview.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_the_print_action_opens_the_preview_with_the_composited_image(self) -> None:
        """
        Ensures File > Print shows the sheet, with the annotated picture on it.
        """

        from src.editor_window import EditorWindow

        pixmap = QPixmap(300, 200)
        pixmap.fill(QColor(200, 40, 40))
        editor = EditorWindow(pixmap)
        self.addCleanup(editor.close)
        seen: dict = {}

        def fake_exec(dialog) -> int:
            seen["size"] = (dialog._pixmap.width(), dialog._pixmap.height())
            seen["class"] = type(dialog).__name__
            return 0

        with patch.object(PrintPreviewDialog, "exec", fake_exec):
            editor.print_image()

        self.assertEqual(seen["class"], "PrintPreviewDialog")
        self.assertEqual(seen["size"], (300, 200))


if __name__ == "__main__":
    unittest.main()
