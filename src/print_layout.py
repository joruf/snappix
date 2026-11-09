"""
Where an image sits on a printed page.

The print preview shows a sheet of paper with the picture on it, which can be
dragged and resized before it is printed. This module is the arithmetic behind
that, with no Qt in it, so the rules -- fit, fill, keep the proportions, swap
the orientation -- can be tested without a window or a printer.

Everything is in millimetres on the sheet, measured from its top-left corner.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Paper sizes the preview offers, as (width, height) in portrait millimetres.
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
}

DEFAULT_PAPER = "A4"

#: Distance from the paper's edge that printers typically cannot reach.
DEFAULT_MARGIN_MM = 10.0

#: Smallest side a picture may be shrunk to, so a drag cannot make it vanish.
MIN_SIDE_MM = 5.0

MM_PER_INCH = 25.4

#: Screen resolution that "original size" is measured against.
ORIGINAL_SIZE_DPI = 96.0


@dataclass
class PrintLayout:
    """
    One picture on one sheet.

    Attributes:
        image_width_px: Picture width in pixels.
        image_height_px: Picture height in pixels.
        paper: Paper size name from ``PAPER_SIZES_MM``.
        landscape: True for a sheet turned on its side.
        margin_mm: Unprintable border around the sheet.
        x_mm: Left edge of the picture on the sheet.
        y_mm: Top edge of the picture on the sheet.
        width_mm: Picture width on the sheet; the height follows from the
            picture's own proportions.
    """

    image_width_px: int
    image_height_px: int
    paper: str = DEFAULT_PAPER
    landscape: bool = False
    margin_mm: float = DEFAULT_MARGIN_MM
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 0.0

    def __post_init__(self) -> None:
        """
        Starts with the picture scaled to fit the printable area and centred.
        """

        self.image_width_px = max(1, int(self.image_width_px))
        self.image_height_px = max(1, int(self.image_height_px))
        if self.paper not in PAPER_SIZES_MM:
            self.paper = DEFAULT_PAPER
        if self.width_mm <= 0.0:
            self.fit_to_page()

    # ------------------------------------------------------------------ sheet

    @property
    def aspect(self) -> float:
        """
        Returns the picture's width divided by its height.

        Returns:
            float: Proportions that every resize keeps.
        """

        return self.image_width_px / self.image_height_px

    @property
    def page_size_mm(self) -> tuple[float, float]:
        """
        Returns the sheet size in its current orientation.

        Returns:
            tuple[float, float]: Width and height in millimetres.
        """

        width, height = PAPER_SIZES_MM[self.paper]
        return (height, width) if self.landscape else (width, height)

    @property
    def printable_rect_mm(self) -> tuple[float, float, float, float]:
        """
        Returns the area a printer can actually reach.

        Returns:
            tuple[float, float, float, float]: Left, top, width, height.
        """

        width, height = self.page_size_mm
        return (
            self.margin_mm,
            self.margin_mm,
            max(1.0, width - 2.0 * self.margin_mm),
            max(1.0, height - 2.0 * self.margin_mm),
        )

    # ---------------------------------------------------------------- picture

    @property
    def height_mm(self) -> float:
        """
        Returns the picture height on the sheet.

        Returns:
            float: Height in millimetres, from the width and the proportions.
        """

        return self.width_mm / self.aspect

    @property
    def rect_mm(self) -> tuple[float, float, float, float]:
        """
        Returns where the picture sits on the sheet.

        Returns:
            tuple[float, float, float, float]: Left, top, width, height.
        """

        return (self.x_mm, self.y_mm, self.width_mm, self.height_mm)

    def set_width(self, width_mm: float, *, keep_center: bool = False) -> None:
        """
        Sets the picture width; the height follows.

        Args:
            width_mm: New width, limited to ``MIN_SIDE_MM`` on the short side.
            keep_center: True to grow and shrink around the middle instead of
                the top-left corner.
        """

        center_x = self.x_mm + self.width_mm / 2.0
        center_y = self.y_mm + self.height_mm / 2.0
        minimum = MIN_SIDE_MM * max(1.0, self.aspect)
        self.width_mm = max(minimum, float(width_mm))
        if keep_center:
            self.x_mm = center_x - self.width_mm / 2.0
            self.y_mm = center_y - self.height_mm / 2.0

    def set_height(self, height_mm: float, *, keep_center: bool = False) -> None:
        """
        Sets the picture height; the width follows.

        Args:
            height_mm: New height.
            keep_center: True to resize around the middle.
        """

        self.set_width(float(height_mm) * self.aspect, keep_center=keep_center)

    def move_to(self, x_mm: float, y_mm: float) -> None:
        """
        Moves the picture's top-left corner.

        Args:
            x_mm: Left edge on the sheet.
            y_mm: Top edge on the sheet.
        """

        self.x_mm = float(x_mm)
        self.y_mm = float(y_mm)

    def center(self) -> None:
        """
        Centres the picture on the sheet.
        """

        page_width, page_height = self.page_size_mm
        self.x_mm = (page_width - self.width_mm) / 2.0
        self.y_mm = (page_height - self.height_mm) / 2.0

    def fit_to_page(self) -> None:
        """
        Scales the picture up or down until it fills the printable area without
        being cut, and centres it.
        """

        _left, _top, area_width, area_height = self.printable_rect_mm
        self.width_mm = min(area_width, area_height * self.aspect)
        self.center()

    def fill_page(self) -> None:
        """
        Scales the picture until it covers the printable area completely, and
        centres it; the overhang is cut by the margins.
        """

        _left, _top, area_width, area_height = self.printable_rect_mm
        self.width_mm = max(area_width, area_height * self.aspect)
        self.center()

    def original_size(self, dpi: float = ORIGINAL_SIZE_DPI) -> None:
        """
        Shows the picture at its own pixel size, and centres it.

        Args:
            dpi: Pixels per inch to measure the picture against.
        """

        self.width_mm = self.image_width_px / float(dpi) * MM_PER_INCH
        self.center()

    def resize_from_corner(self, corner: str, x_mm: float, y_mm: float) -> None:
        """
        Resizes the picture by dragging one corner, keeping the opposite corner
        where it is and the proportions as they are.

        Args:
            corner: ``tl``, ``tr``, ``bl`` or ``br``.
            x_mm: Where the dragged corner is now, horizontally.
            y_mm: Where the dragged corner is now, vertically.
        """

        left, top, width, height = self.rect_mm
        anchor_x = left + width if corner in ("tl", "bl") else left
        anchor_y = top + height if corner in ("tl", "tr") else top
        # Whichever direction was dragged further decides the size, so the
        # corner follows the pointer along the diagonal rather than lagging.
        new_width = max(abs(x_mm - anchor_x), abs(y_mm - anchor_y) * self.aspect)
        minimum = MIN_SIDE_MM * max(1.0, self.aspect)
        new_width = max(minimum, new_width)
        new_height = new_width / self.aspect
        self.width_mm = new_width
        self.x_mm = anchor_x - new_width if corner in ("tl", "bl") else anchor_x
        self.y_mm = anchor_y - new_height if corner in ("tl", "tr") else anchor_y

    # ------------------------------------------------------------------ paper

    def is_fitted(self) -> bool:
        """
        Reports whether the picture currently fills the printable area as far as
        its proportions allow, centred, i.e. whether "Fit to page" would change
        nothing.

        Returns:
            bool: True for a picture that was fitted and not moved or resized since.
        """

        _left, _top, area_width, area_height = self.printable_rect_mm
        page_width, page_height = self.page_size_mm
        center_x, center_y = self._center()
        return (
            abs(self.width_mm - min(area_width, area_height * self.aspect)) < 0.05
            and abs(center_x - page_width / 2.0) < 0.05
            and abs(center_y - page_height / 2.0) < 0.05
        )

    def set_paper(self, paper: str) -> None:
        """
        Changes the paper size.

        A picture that fills the page keeps filling it. Any other picture keeps
        its share of the sheet and its relative position.

        Args:
            paper: Paper size name.
        """

        if paper not in PAPER_SIZES_MM or paper == self.paper:
            return
        was_fitted = self.is_fitted()
        old_width, old_height = self.page_size_mm
        old_center = self._center()
        self.paper = paper
        new_width, new_height = self.page_size_mm
        if was_fitted:
            self.fit_to_page()
            return
        self.width_mm *= min(new_width / old_width, new_height / old_height)
        self._place_center(old_center, old_width, old_height)

    def set_landscape(self, landscape: bool) -> None:
        """
        Turns the sheet.

        A picture that fills the page keeps filling it. Any other picture keeps
        its size and its relative position, and is only shrunk when it no longer
        fits on the turned sheet, so turning back and forth does not drift.

        Args:
            landscape: True for landscape.
        """

        if bool(landscape) == self.landscape:
            return
        was_fitted = self.is_fitted()
        old_width, old_height = self.page_size_mm
        old_center = self._center()
        self.landscape = bool(landscape)
        if was_fitted:
            self.fit_to_page()
            return
        _left, _top, area_width, area_height = self.printable_rect_mm
        self.width_mm = min(self.width_mm, area_width, area_height * self.aspect)
        self._place_center(old_center, old_width, old_height)

    def _center(self) -> tuple[float, float]:
        """
        Returns the middle of the picture on the sheet.

        Returns:
            tuple[float, float]: Horizontal and vertical position in millimetres.
        """

        return (self.x_mm + self.width_mm / 2.0, self.y_mm + self.height_mm / 2.0)

    def _place_center(
        self,
        old_center: tuple[float, float],
        old_width: float,
        old_height: float,
    ) -> None:
        """
        Puts the picture's centre at the same relative place on the changed sheet.

        Args:
            old_center: Centre before the change, in millimetres on the old sheet.
            old_width: Old sheet width.
            old_height: Old sheet height.
        """

        new_width, new_height = self.page_size_mm
        center_x = old_center[0] / old_width * new_width
        center_y = old_center[1] / old_height * new_height
        self.x_mm = center_x - self.width_mm / 2.0
        self.y_mm = center_y - self.height_mm / 2.0


def device_rect(
    rect_mm: tuple[float, float, float, float],
    paper_size_mm: tuple[float, float],
    paper_rect_px: tuple[float, float, float, float],
    page_rect_px: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """
    Converts a rectangle on the sheet into the printer's own coordinates.

    A painter on a printer has its origin at the top-left of the *printable*
    area, not of the paper, so a picture placed relative to the paper has to be
    shifted by the unprintable border.

    Args:
        rect_mm: Left, top, width, height on the sheet, in millimetres.
        paper_size_mm: Sheet width and height in millimetres.
        paper_rect_px: The paper in device pixels (``QPrinter.paperRect``).
        page_rect_px: The printable area in device pixels (``QPrinter.pageRect``).

    Returns:
        tuple[float, float, float, float]: Left, top, width, height for the painter.
    """

    scale_x = paper_rect_px[2] / paper_size_mm[0]
    scale_y = paper_rect_px[3] / paper_size_mm[1]
    left, top, width, height = rect_mm
    return (
        paper_rect_px[0] + left * scale_x - page_rect_px[0],
        paper_rect_px[1] + top * scale_y - page_rect_px[1],
        width * scale_x,
        height * scale_y,
    )
