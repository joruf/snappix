"""
The pair of close buttons on a tab that is backed by a capture file.

A capture is a file in the project folder, so closing its tab can mean two
different things, and the tab offers both side by side instead of asking:

* an ``X``, which closes the tab and keeps the image in the folder,
* a trash can in the danger colour, which closes the tab and deletes the image.

The two differ in shape and colour, not just in a tooltip, so nobody has to
read anything to know which one is destructive. Both are drawn here rather than
taken from icon fonts, so they look the same on every platform and follow the
theme's text colour.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from src.theme import get_theme_colors

#: Edge of one button; the pair is two of these plus the gap.
BUTTON_SIZE = 18
#: Space between the two buttons: enough to aim at one, small enough to read as a pair.
BUTTON_GAP = 3

#: Colour of the delete button; readable on every theme's tab background.
DANGER_COLOR = "#e0524d"
#: Lighter red for the selected tab, whose accent-coloured background would
#: swallow the normal one.
DANGER_COLOR_ON_ACCENT = "#ffc9c5"

KEEP_TOOLTIP = "Close tab and keep the image in the project folder"
DELETE_TOOLTIP = "Close tab and delete the image from the project folder"

KIND_KEEP = "keep"
KIND_DELETE = "delete"


class TabCloseButton(QToolButton):
    """
    One flat, painted close button.

    The glyph is drawn in ``paintEvent`` from the current theme, so a theme
    change recolours it without anyone having to rebuild the tabs.
    """

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        """
        Creates one button.

        Args:
            kind: ``keep`` for the plain X, ``delete`` for the trash can.
            parent: Owner widget.
        """

        super().__init__(parent)
        self.kind = kind
        self.on_selected_tab = False
        self.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(DELETE_TOOLTIP if kind == KIND_DELETE else KEEP_TOOLTIP)
        self.setAccessibleName(
            "Close tab and delete image" if kind == KIND_DELETE else "Close tab, keep image"
        )

    def sizeHint(self) -> QSize:
        """
        Returns the fixed button size.

        Returns:
            QSize: Square of ``BUTTON_SIZE``.
        """

        return QSize(BUTTON_SIZE, BUTTON_SIZE)

    def glyph_color(self) -> QColor:
        """
        Returns the colour the glyph is drawn in.

        Returns:
            QColor: Red for delete, the tab's text colour for keep. The selected
            tab has an accent background, so both switch to colours made for it.
        """

        colors = get_theme_colors()
        if self.kind == KIND_DELETE:
            return QColor(DANGER_COLOR_ON_ACCENT if self.on_selected_tab else DANGER_COLOR)
        return QColor(colors.button_checked_text if self.on_selected_tab else colors.text)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        """
        Draws the hover background and the glyph.

        Args:
            event: Qt paint event.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = self.glyph_color()

        if self.underMouse() or self.isDown():
            background = QColor(colour)
            background.setAlpha(70 if self.isDown() else 42)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)

        pen = QPen(colour, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == KIND_DELETE:
            self._paint_trash(painter)
        else:
            self._paint_cross(painter)

    @staticmethod
    def _paint_cross(painter: QPainter) -> None:
        """
        Draws the X.

        Args:
            painter: Painter on the button, in its 18 x 18 pixel space.
        """

        painter.drawLine(QPointF(5.5, 5.5), QPointF(12.5, 12.5))
        painter.drawLine(QPointF(12.5, 5.5), QPointF(5.5, 12.5))

    @staticmethod
    def _paint_trash(painter: QPainter) -> None:
        """
        Draws the trash can: lid, handle, body and two slats.

        Args:
            painter: Painter on the button, in its 18 x 18 pixel space.
        """

        painter.drawLine(QPointF(4.0, 5.5), QPointF(14.0, 5.5))
        painter.drawLine(QPointF(7.2, 5.5), QPointF(7.2, 4.0))
        painter.drawLine(QPointF(7.2, 4.0), QPointF(10.8, 4.0))
        painter.drawLine(QPointF(10.8, 4.0), QPointF(10.8, 5.5))
        painter.drawPolyline(
            [QPointF(5.2, 5.5), QPointF(5.8, 14.0), QPointF(12.2, 14.0), QPointF(12.8, 5.5)]
        )
        painter.drawLine(QPointF(7.9, 7.6), QPointF(8.0, 12.0))
        painter.drawLine(QPointF(10.1, 7.6), QPointF(10.0, 12.0))


class TabClosePair(QWidget):
    """
    The two buttons, side by side, as one widget a tab bar can hold.

    Attributes:
        keep_requested: Emitted by the X.
        delete_requested: Emitted by the trash can.
    """

    keep_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Creates the pair.

        Args:
            parent: Owner widget.
        """

        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(BUTTON_GAP)
        self.keep_button = TabCloseButton(KIND_KEEP, self)
        self.delete_button = TabCloseButton(KIND_DELETE, self)
        layout.addWidget(self.keep_button)
        layout.addWidget(self.delete_button)
        self.keep_button.clicked.connect(self.keep_requested)
        self.delete_button.clicked.connect(self.delete_requested)
        self.setFixedSize(pair_width(), BUTTON_SIZE)

    def set_selected(self, selected: bool) -> None:
        """
        Tells the buttons whether their tab is the selected one.

        Args:
            selected: True for the current tab.
        """

        for button in (self.keep_button, self.delete_button):
            button.on_selected_tab = selected
            button.update()


def pair_width() -> int:
    """
    Returns the width the pair needs.

    Returns:
        int: Two buttons and the gap between them.
    """

    return 2 * BUTTON_SIZE + BUTTON_GAP
