"""
Tests for the arithmetic behind the print preview.

No window and no printer: where the picture sits on the sheet, how it is
resized, and how a place on the sheet becomes a place on a printer.
"""

from __future__ import annotations

import unittest

from src.print_layout import (
    DEFAULT_MARGIN_MM,
    MIN_SIDE_MM,
    PAPER_SIZES_MM,
    PrintLayout,
    device_rect,
)


class TestFitting(unittest.TestCase):
    """
    Verifies the starting placement and the fit/fill buttons.
    """

    def test_a_new_layout_fits_the_printable_area_and_is_centred(self) -> None:
        """
        Ensures the picture starts as large as the margins allow, in the middle.
        """

        layout = PrintLayout(1200, 800)

        self.assertAlmostEqual(layout.width_mm, 210.0 - 2 * DEFAULT_MARGIN_MM)
        self.assertAlmostEqual(layout.height_mm, layout.width_mm / 1.5)
        self.assertAlmostEqual(layout.x_mm, 10.0)
        self.assertAlmostEqual(layout.y_mm, (297.0 - layout.height_mm) / 2)

    def test_a_tall_picture_is_limited_by_the_height(self) -> None:
        """
        Ensures fitting takes whichever side runs out first.
        """

        layout = PrintLayout(400, 1600)

        self.assertAlmostEqual(layout.height_mm, 297.0 - 2 * DEFAULT_MARGIN_MM)
        self.assertLess(layout.width_mm, 210.0 - 2 * DEFAULT_MARGIN_MM)

    def test_fit_never_leaves_the_printable_area(self) -> None:
        """
        Ensures no proportions, paper or orientation push the picture past the margins.
        """

        for paper in PAPER_SIZES_MM:
            for landscape in (False, True):
                for size in ((100, 100), (3000, 200), (200, 3000), (1920, 1080), (7, 900)):
                    with self.subTest(paper=paper, landscape=landscape, size=size):
                        layout = PrintLayout(*size, paper=paper)
                        layout.set_landscape(landscape)
                        layout.fit_to_page()
                        left, top, width, height = layout.printable_rect_mm
                        x, y, w, h = layout.rect_mm
                        self.assertGreaterEqual(x, left - 1e-6)
                        self.assertGreaterEqual(y, top - 1e-6)
                        self.assertLessEqual(x + w, left + width + 1e-6)
                        self.assertLessEqual(y + h, top + height + 1e-6)

    def test_fill_covers_the_whole_printable_area(self) -> None:
        """
        Ensures filling leaves no gap, cutting the overhang instead.
        """

        layout = PrintLayout(1200, 800)
        layout.fill_page()
        left, top, width, height = layout.printable_rect_mm
        x, y, w, h = layout.rect_mm

        self.assertLessEqual(x, left + 1e-6)
        self.assertLessEqual(y, top + 1e-6)
        self.assertGreaterEqual(x + w, left + width - 1e-6)
        self.assertGreaterEqual(y + h, top + height - 1e-6)

    def test_original_size_measures_pixels_at_screen_resolution(self) -> None:
        """
        Ensures 96 pixels are one inch on paper.
        """

        layout = PrintLayout(96, 48)
        layout.original_size()

        self.assertAlmostEqual(layout.width_mm, 25.4)
        self.assertAlmostEqual(layout.height_mm, 12.7)

    def test_centre_puts_the_picture_in_the_middle_of_the_sheet(self) -> None:
        """
        Ensures centring uses the sheet, not the margins' corner.
        """

        layout = PrintLayout(1000, 1000)
        layout.set_width(100.0)
        layout.move_to(0.0, 0.0)
        layout.center()

        self.assertAlmostEqual(layout.x_mm, 55.0)
        self.assertAlmostEqual(layout.y_mm, 98.5)

    def test_an_unknown_paper_falls_back_to_the_default(self) -> None:
        """
        Ensures a bad name cannot break the layout.
        """

        self.assertEqual(PrintLayout(10, 10, paper="Bogus").paper, "A4")


class TestResizing(unittest.TestCase):
    """
    Verifies that resizing keeps the proportions.
    """

    def test_width_drives_the_height(self) -> None:
        """
        Ensures a new width keeps the picture's shape.
        """

        layout = PrintLayout(1200, 800)
        layout.set_width(90.0)

        self.assertAlmostEqual(layout.height_mm, 60.0)

    def test_height_drives_the_width(self) -> None:
        """
        Ensures the same in the other direction.
        """

        layout = PrintLayout(1200, 800)
        layout.set_height(60.0)

        self.assertAlmostEqual(layout.width_mm, 90.0)

    def test_resizing_around_the_centre_keeps_the_middle_still(self) -> None:
        """
        Ensures the keep-centre option leaves the middle where it was.
        """

        layout = PrintLayout(1000, 1000)
        layout.set_width(100.0)
        layout.move_to(50.0, 60.0)
        layout.set_width(60.0, keep_center=True)

        self.assertAlmostEqual(layout.x_mm + layout.width_mm / 2, 100.0)
        self.assertAlmostEqual(layout.y_mm + layout.height_mm / 2, 110.0)

    def test_the_picture_cannot_shrink_to_nothing(self) -> None:
        """
        Ensures a drag past zero leaves a picture that can still be grabbed.
        """

        layout = PrintLayout(1000, 500)
        layout.set_width(0.0)

        self.assertGreaterEqual(layout.width_mm, MIN_SIDE_MM)
        self.assertGreaterEqual(layout.height_mm, MIN_SIDE_MM / 2)

    def test_a_thin_picture_keeps_its_short_side_grabbable(self) -> None:
        """
        Ensures a very wide picture is not squashed below the minimum thickness.
        """

        layout = PrintLayout(4000, 100)
        layout.set_width(1.0)

        self.assertGreaterEqual(layout.height_mm, MIN_SIDE_MM - 1e-6)

    def test_dragging_a_corner_keeps_the_opposite_corner_fixed(self) -> None:
        """
        Ensures each corner resizes away from its opposite.
        """

        anchors = {
            "tl": lambda r: (r[0] + r[2], r[1] + r[3]),
            "tr": lambda r: (r[0], r[1] + r[3]),
            "bl": lambda r: (r[0] + r[2], r[1]),
            "br": lambda r: (r[0], r[1]),
        }
        pull = {"tl": (-20, -20), "tr": (20, -20), "bl": (-20, 20), "br": (20, 20)}
        for corner, anchor_of in anchors.items():
            with self.subTest(corner=corner):
                layout = PrintLayout(1000, 500)
                layout.set_width(80.0)
                layout.move_to(60.0, 100.0)
                before = layout.rect_mm
                anchor = anchor_of(before)
                corner_x = before[0] + (before[2] if corner in ("tr", "br") else 0)
                corner_y = before[1] + (before[3] if corner in ("bl", "br") else 0)

                layout.resize_from_corner(
                    corner, corner_x + pull[corner][0], corner_y + pull[corner][1]
                )

                after = layout.rect_mm
                self.assertAlmostEqual(anchor_of(after)[0], anchor[0])
                self.assertAlmostEqual(anchor_of(after)[1], anchor[1])
                self.assertGreater(after[2], before[2])
                self.assertAlmostEqual(after[2] / after[3], 2.0)

    def test_dragging_a_corner_over_the_opposite_one_does_not_flip(self) -> None:
        """
        Ensures the picture stays a picture, at its minimum, rather than inverting.
        """

        layout = PrintLayout(1000, 1000)
        layout.set_width(80.0)
        layout.move_to(50.0, 50.0)
        layout.resize_from_corner("br", 0.0, 0.0)

        self.assertGreaterEqual(layout.width_mm, MIN_SIDE_MM)
        self.assertAlmostEqual(layout.x_mm, 50.0)


class TestSheetChanges(unittest.TestCase):
    """
    Verifies paper and orientation changes.
    """

    def test_turning_the_sheet_keeps_the_picture_on_it(self) -> None:
        """
        Ensures a picture that fitted still fits after the sheet is turned.
        """

        layout = PrintLayout(1200, 800)
        layout.set_landscape(True)
        width, height = layout.page_size_mm
        x, y, w, h = layout.rect_mm

        self.assertEqual((width, height), (297.0, 210.0))
        self.assertGreaterEqual(x, -1e-6)
        self.assertGreaterEqual(y, -1e-6)
        self.assertLessEqual(x + w, width + 1e-6)
        self.assertLessEqual(y + h, height + 1e-6)

    def test_a_fitted_picture_keeps_filling_the_page_when_turned(self) -> None:
        """
        Ensures the page stays used as well as it can be.
        """

        layout = PrintLayout(1200, 800)
        layout.set_landscape(True)

        self.assertTrue(layout.is_fitted())
        self.assertAlmostEqual(layout.width_mm, 277.0)

    def test_a_fitted_picture_keeps_filling_the_page_on_other_paper(self) -> None:
        """
        Ensures switching to A3 enlarges a fitted picture to the new margins.
        """

        layout = PrintLayout(1000, 1000)
        layout.set_paper("A3")

        self.assertTrue(layout.is_fitted())
        self.assertAlmostEqual(layout.width_mm, 297.0 - 2 * DEFAULT_MARGIN_MM)

    def test_a_placed_picture_keeps_its_share_of_a_bigger_sheet(self) -> None:
        """
        Ensures a picture the user sized keeps its proportion of the sheet.
        """

        layout = PrintLayout(1000, 1000, paper="A5")
        layout.set_width(60.0)
        layout.move_to(20.0, 30.0)
        share = layout.width_mm / layout.page_size_mm[0]
        center_share = (
            (layout.x_mm + layout.width_mm / 2) / layout.page_size_mm[0],
            (layout.y_mm + layout.height_mm / 2) / layout.page_size_mm[1],
        )
        layout.set_paper("A3")

        self.assertFalse(layout.is_fitted())
        self.assertAlmostEqual(layout.width_mm / layout.page_size_mm[0], share, places=2)
        self.assertAlmostEqual(
            (layout.x_mm + layout.width_mm / 2) / layout.page_size_mm[0], center_share[0], places=6
        )
        self.assertAlmostEqual(
            (layout.y_mm + layout.height_mm / 2) / layout.page_size_mm[1], center_share[1], places=6
        )

    def test_a_placed_picture_keeps_its_size_when_the_sheet_is_turned(self) -> None:
        """
        Ensures turning the sheet does not shrink a picture that still fits.
        """

        layout = PrintLayout(1200, 800)
        layout.set_width(100.0)
        layout.move_to(30.0, 40.0)
        layout.set_landscape(True)

        self.assertAlmostEqual(layout.width_mm, 100.0)

    def test_a_picture_too_big_for_the_turned_sheet_is_shrunk_to_it(self) -> None:
        """
        Ensures nothing is left hanging off the sheet by turning it.
        """

        layout = PrintLayout(400, 1600)
        layout.set_height(250.0)
        layout.move_to(60.0, 20.0)
        layout.set_landscape(True)

        _left, _top, _width, height = layout.printable_rect_mm
        self.assertLessEqual(layout.height_mm, height + 1e-6)

    def test_choosing_the_same_paper_changes_nothing(self) -> None:
        """
        Ensures re-selecting an entry does not move the picture.
        """

        layout = PrintLayout(1000, 1000)
        before = layout.rect_mm
        layout.set_paper("A4")
        layout.set_landscape(False)

        self.assertEqual(layout.rect_mm, before)

    def test_there_and_back_restores_the_placement(self) -> None:
        """
        Ensures turning the sheet twice does not drift the picture.
        """

        layout = PrintLayout(1200, 800)
        layout.move_to(33.0, 44.0)
        before = layout.rect_mm
        layout.set_landscape(True)
        layout.set_landscape(False)

        for got, expected in zip(layout.rect_mm, before):
            self.assertAlmostEqual(got, expected, places=6)


class TestDeviceRect(unittest.TestCase):
    """
    Verifies the sheet-to-printer conversion.
    """

    # A4 at 300 dpi, with a printer that cannot reach the outer 4 mm.
    PAPER = (0.0, 0.0, 2480.0, 3508.0)
    PAGE = (47.0, 47.0, 2386.0, 3414.0)

    def test_the_origin_of_the_painter_is_the_printable_area(self) -> None:
        """
        Ensures the unprintable border is subtracted, or everything prints too far in.
        """

        x, y, w, h = device_rect((10.0, 20.0, 100.0, 50.0), (210.0, 297.0), self.PAPER, self.PAGE)

        self.assertAlmostEqual(x, 10.0 * 2480 / 210 - 47.0)
        self.assertAlmostEqual(y, 20.0 * 3508 / 297 - 47.0)
        self.assertAlmostEqual(w, 100.0 * 2480 / 210)
        self.assertAlmostEqual(h, 50.0 * 3508 / 297)

    def test_a_picture_at_the_paper_corner_lands_left_of_the_painter_origin(self) -> None:
        """
        Ensures a picture touching the paper edge is cut by the printer, not shifted.
        """

        x, y, _w, _h = device_rect((0.0, 0.0, 10.0, 10.0), (210.0, 297.0), self.PAPER, self.PAGE)

        self.assertAlmostEqual(x, -47.0)
        self.assertAlmostEqual(y, -47.0)

    def test_a_printer_without_a_border_needs_no_shift(self) -> None:
        """
        Ensures a PDF, whose page is its paper, is not shifted.
        """

        paper = (0.0, 0.0, 595.0, 842.0)
        x, y, _w, _h = device_rect((10.0, 10.0, 50.0, 50.0), (210.0, 297.0), paper, paper)

        self.assertAlmostEqual(x, 10.0 * 595 / 210)
        self.assertAlmostEqual(y, 10.0 * 842 / 297)


if __name__ == "__main__":
    unittest.main()
