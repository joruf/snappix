"""
Print preview: a sheet of paper with the picture on it.

The picture can be dragged around the sheet and resized by its corners, the
paper size and orientation can be changed, and "Print" sends exactly what the
preview shows to a printer, or to a PDF file. The sheet is drawn in millimetres,
so what is placed on screen is what comes out on paper.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from src.constants import APP_NAME
from src.print_layout import PAPER_SIZES_MM, PrintLayout, device_rect

#: Entry of the printer list that writes a PDF file instead of using a device.
PDF_PRINTER = "Save as PDF…"

#: Qt page sizes for the paper names in ``PAPER_SIZES_MM``.
_PAGE_SIZE_IDS = {
    "A3": QPageSize.PageSizeId.A3,
    "A4": QPageSize.PageSizeId.A4,
    "A5": QPageSize.PageSizeId.A5,
    "Letter": QPageSize.PageSizeId.Letter,
    "Legal": QPageSize.PageSizeId.Legal,
}

#: Pasteboard shown around the sheet, in millimetres.
_PASTEBOARD_MM = 14.0

#: Edge of a resize handle, in screen pixels.
_HANDLE_PIXELS = 11.0

_PAGE_SHADOW = QColor(0, 0, 0, 70)
_PASTEBOARD = QColor("#6b7280")
_ACCENT = QColor("#2f7dd1")


class _ImageItem(QGraphicsPixmapItem):
    """
    The picture on the sheet; dragging it moves it.
    """

    def __init__(self, pixmap: QPixmap, on_moved: Callable[[float, float], None]) -> None:
        """
        Creates the item.

        Args:
            pixmap: Picture to show.
            on_moved: Called with the new top-left corner after each move.
        """

        super().__init__(pixmap)
        self._on_moved = on_moved
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setZValue(2)

    def itemChange(self, change, value):  # noqa: N802 - Qt override
        """
        Reports a move to the dialog.

        Args:
            change: Kind of change.
            value: New value.

        Returns:
            The value Qt should apply.
        """

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._on_moved(self.pos().x(), self.pos().y())
        return super().itemChange(change, value)


class _Handle(QGraphicsRectItem):
    """
    A square at one corner of the picture; dragging it resizes the picture.
    """

    _CURSORS = {
        "tl": Qt.CursorShape.SizeFDiagCursor,
        "br": Qt.CursorShape.SizeFDiagCursor,
        "tr": Qt.CursorShape.SizeBDiagCursor,
        "bl": Qt.CursorShape.SizeBDiagCursor,
    }

    def __init__(self, corner: str, on_drag: Callable[[str, QPointF], None]) -> None:
        """
        Creates the handle.

        Args:
            corner: ``tl``, ``tr``, ``bl`` or ``br``.
            on_drag: Called with the corner and the pointer's sheet position.
        """

        half = _HANDLE_PIXELS / 2.0
        super().__init__(-half, -half, _HANDLE_PIXELS, _HANDLE_PIXELS)
        self.corner = corner
        self._on_drag = on_drag
        # Stays the same size on screen however far the sheet is scaled.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(Qt.GlobalColor.white))
        self.setPen(QPen(_ACCENT, 1.5))
        self.setCursor(self._CURSORS[corner])
        self.setZValue(3)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        """
        Takes the press so the picture underneath does not start a move.

        Args:
            event: Mouse event.
        """

        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        """
        Resizes while dragged.

        Args:
            event: Mouse event.
        """

        self._on_drag(self.corner, event.scenePos())
        event.accept()


class PrintPreviewDialog(QDialog):
    """
    Preview of one picture on a sheet of paper, with the controls to place it.

    Attributes:
        layout_model: The placement being edited.
    """

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        """
        Creates the dialog.

        Args:
            pixmap: Picture to print, annotations included.
            parent: Owner window.
        """

        super().__init__(parent)
        self.setWindowTitle("Print")
        self.resize(980, 700)
        self._pixmap = pixmap
        self.layout_model = PrintLayout(pixmap.width(), pixmap.height())
        self._syncing = False

        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setBackgroundBrush(QBrush(_PASTEBOARD))
        self._view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)

        self._shadow = QGraphicsRectItem()
        self._shadow.setBrush(QBrush(_PAGE_SHADOW))
        self._shadow.setPen(QPen(Qt.PenStyle.NoPen))
        self._shadow.setZValue(0)
        self._page = QGraphicsRectItem()
        self._page.setBrush(QBrush(Qt.GlobalColor.white))
        self._page.setPen(QPen(QColor("#9ca3af"), 0))
        self._page.setZValue(1)
        self._printable = QGraphicsRectItem()
        printable_pen = QPen(QColor("#c4c9d2"), 0)
        printable_pen.setStyle(Qt.PenStyle.DashLine)
        self._printable.setPen(printable_pen)
        self._printable.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._printable.setZValue(1.5)
        for item in (self._shadow, self._page, self._printable):
            self._scene.addItem(item)

        self._image_item = _ImageItem(pixmap, self._on_image_moved)
        self._scene.addItem(self._image_item)
        self._handles = {
            corner: _Handle(corner, self._on_handle_dragged) for corner in ("tl", "tr", "bl", "br")
        }
        for handle in self._handles.values():
            self._scene.addItem(handle)

        self._build_controls()
        root = QHBoxLayout(self)
        root.addWidget(self._view, 1)
        root.addWidget(self._side_panel)

        self._apply_layout(refit=True)

    # ------------------------------------------------------------------ build

    def _build_controls(self) -> None:
        """
        Builds the panel beside the preview.
        """

        self._side_panel = QWidget(self)
        self._side_panel.setFixedWidth(260)
        column = QVBoxLayout(self._side_panel)
        column.setContentsMargins(0, 0, 0, 0)

        printer_box = QGroupBox("Printer", self._side_panel)
        printer_form = QFormLayout(printer_box)
        self.printer_combo = QComboBox()
        names = list(QPrinterInfo.availablePrinterNames())
        default = QPrinterInfo.defaultPrinterName()
        if default in names:
            names.remove(default)
            names.insert(0, default)
        for name in names:
            self.printer_combo.addItem(name, name)
        self.printer_combo.addItem(PDF_PRINTER, PDF_PRINTER)
        printer_form.addRow(self.printer_combo)
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        printer_form.addRow("Copies:", self.copies_spin)
        column.addWidget(printer_box)

        paper_box = QGroupBox("Paper", self._side_panel)
        paper_form = QFormLayout(paper_box)
        self.paper_combo = QComboBox()
        for name in PAPER_SIZES_MM:
            self.paper_combo.addItem(name, name)
        self.paper_combo.setCurrentIndex(self.paper_combo.findData(self.layout_model.paper))
        paper_form.addRow("Size:", self.paper_combo)
        orientation_row = QHBoxLayout()
        self.portrait_radio = QRadioButton("Portrait")
        self.landscape_radio = QRadioButton("Landscape")
        self.portrait_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.portrait_radio)
        group.addButton(self.landscape_radio)
        orientation_row.addWidget(self.portrait_radio)
        orientation_row.addWidget(self.landscape_radio)
        paper_form.addRow(orientation_row)
        column.addWidget(paper_box)

        image_box = QGroupBox("Image", self._side_panel)
        image_form = QFormLayout(image_box)
        self.width_spin = self._millimetre_spin(1.0, 2000.0)
        self.height_spin = self._millimetre_spin(1.0, 2000.0)
        self.x_spin = self._millimetre_spin(-2000.0, 2000.0)
        self.y_spin = self._millimetre_spin(-2000.0, 2000.0)
        image_form.addRow("Width:", self.width_spin)
        image_form.addRow("Height:", self.height_spin)
        image_form.addRow("Left:", self.x_spin)
        image_form.addRow("Top:", self.y_spin)
        hint = QLabel("The proportions stay as they are.")
        hint.setWordWrap(True)
        image_form.addRow(hint)
        self.fit_button = QPushButton("Fit to page")
        self.fill_button = QPushButton("Fill page")
        self.original_button = QPushButton("Original size")
        self.center_button = QPushButton("Center")
        buttons = QHBoxLayout()
        buttons.addWidget(self.fit_button)
        buttons.addWidget(self.fill_button)
        more = QHBoxLayout()
        more.addWidget(self.original_button)
        more.addWidget(self.center_button)
        image_form.addRow(buttons)
        image_form.addRow(more)
        column.addWidget(image_box)

        column.addStretch(1)
        action_row = QHBoxLayout()
        self.print_button = QPushButton("Print")
        self.print_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        action_row.addStretch(1)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.print_button)
        column.addLayout(action_row)

        self.paper_combo.currentIndexChanged.connect(self._on_paper_changed)
        self.portrait_radio.toggled.connect(self._on_orientation_changed)
        self.width_spin.valueChanged.connect(self._on_width_edited)
        self.height_spin.valueChanged.connect(self._on_height_edited)
        self.x_spin.valueChanged.connect(self._on_position_edited)
        self.y_spin.valueChanged.connect(self._on_position_edited)
        self.fit_button.clicked.connect(lambda: self._edit_layout(self.layout_model.fit_to_page))
        self.fill_button.clicked.connect(lambda: self._edit_layout(self.layout_model.fill_page))
        self.original_button.clicked.connect(lambda: self._edit_layout(self.layout_model.original_size))
        self.center_button.clicked.connect(lambda: self._edit_layout(self.layout_model.center))
        self.print_button.clicked.connect(self._on_print_clicked)
        self.cancel_button.clicked.connect(self.reject)

    @staticmethod
    def _millimetre_spin(minimum: float, maximum: float) -> QDoubleSpinBox:
        """
        Builds one millimetre field.

        Args:
            minimum: Lowest value.
            maximum: Highest value.

        Returns:
            QDoubleSpinBox: The field.
        """

        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" mm")
        spin.setKeyboardTracking(False)
        return spin

    # --------------------------------------------------------------- syncing

    def _apply_layout(self, *, refit: bool = False) -> None:
        """
        Draws the sheet, the picture and its handles, and the fields, from the model.

        Args:
            refit: True to scale the view to the sheet again. Only a new sheet
                needs that: refitting while a handle is being dragged makes the
                view replay the last mouse move, which drags the handle again,
                without end.
        """

        self._syncing = True
        try:
            width, height = self.layout_model.page_size_mm
            self._page.setRect(0, 0, width, height)
            self._shadow.setRect(1.8, 1.8, width, height)
            left, top, area_width, area_height = self.layout_model.printable_rect_mm
            self._printable.setRect(left, top, area_width, area_height)
            self._scene.setSceneRect(
                -_PASTEBOARD_MM,
                -_PASTEBOARD_MM,
                width + 2 * _PASTEBOARD_MM,
                height + 2 * _PASTEBOARD_MM,
            )

            x, y, image_width, image_height = self.layout_model.rect_mm
            self._image_item.setScale(image_width / max(1, self._pixmap.width()))
            self._image_item.setPos(x, y)
            self._handles["tl"].setPos(x, y)
            self._handles["tr"].setPos(x + image_width, y)
            self._handles["bl"].setPos(x, y + image_height)
            self._handles["br"].setPos(x + image_width, y + image_height)

            for spin, value in (
                (self.width_spin, image_width),
                (self.height_spin, image_height),
                (self.x_spin, x),
                (self.y_spin, y),
            ):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        finally:
            self._syncing = False
        if refit:
            self._fit_view()

    def _fit_view(self) -> None:
        """
        Scales the view so the whole sheet is visible.
        """

        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """
        Keeps the whole sheet in view when the dialog is resized.

        Args:
            event: Resize event.
        """

        super().resizeEvent(event)
        self._fit_view()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        """
        Fits the sheet once the view has its real size.

        Args:
            event: Show event.
        """

        super().showEvent(event)
        self._fit_view()

    def _edit_layout(self, change: Callable[[], None]) -> None:
        """
        Applies one change to the model and redraws.

        Args:
            change: Model method to call.
        """

        change()
        self._apply_layout()

    def _on_image_moved(self, x: float, y: float) -> None:
        """
        Follows a drag of the picture.

        Args:
            x: Left edge on the sheet.
            y: Top edge on the sheet.
        """

        if self._syncing:
            return
        self.layout_model.move_to(x, y)
        self._apply_layout()

    def _on_handle_dragged(self, corner: str, position: QPointF) -> None:
        """
        Follows a drag of one resize handle.

        Args:
            corner: Dragged corner.
            position: Pointer position on the sheet.
        """

        self.layout_model.resize_from_corner(corner, position.x(), position.y())
        self._apply_layout()

    def _on_width_edited(self, value: float) -> None:
        """
        Applies a typed width.

        Args:
            value: Width in millimetres.
        """

        if not self._syncing:
            self.layout_model.set_width(value)
            self._apply_layout()

    def _on_height_edited(self, value: float) -> None:
        """
        Applies a typed height.

        Args:
            value: Height in millimetres.
        """

        if not self._syncing:
            self.layout_model.set_height(value)
            self._apply_layout()

    def _on_position_edited(self, _value: float) -> None:
        """
        Applies a typed position.

        Args:
            _value: Unused; both fields are read together.
        """

        if not self._syncing:
            self.layout_model.move_to(self.x_spin.value(), self.y_spin.value())
            self._apply_layout()

    def _on_paper_changed(self, _index: int) -> None:
        """
        Applies a paper size choice.

        Args:
            _index: Unused; the data of the current entry is read.
        """

        self.layout_model.set_paper(str(self.paper_combo.currentData()))
        self._apply_layout(refit=True)

    def _on_orientation_changed(self, _checked: bool) -> None:
        """
        Applies an orientation choice.

        Args:
            _checked: Unused; the radio buttons are read.
        """

        self.layout_model.set_landscape(self.landscape_radio.isChecked())
        self._apply_layout(refit=True)

    # --------------------------------------------------------------- printing

    def build_printer(self) -> QPrinter | None:
        """
        Creates the printer the current choices describe.

        Asks for a file name when the PDF entry is selected.

        Returns:
            QPrinter | None: A configured printer, or None when the user
            cancelled the file dialog.
        """

        choice = str(self.printer_combo.currentData())
        if choice == PDF_PRINTER:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save as PDF", f"{APP_NAME.lower()}.pdf", "PDF (*.pdf)"
            )
            if not file_name:
                return None
            if not file_name.lower().endswith(".pdf"):
                file_name += ".pdf"
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(file_name)
        else:
            printer = QPrinter(QPrinterInfo.printerInfo(choice), QPrinter.PrinterMode.HighResolution)

        printer.setPageSize(QPageSize(_PAGE_SIZE_IDS[self.layout_model.paper]))
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape
            if self.layout_model.landscape
            else QPageLayout.Orientation.Portrait
        )
        printer.setCopyCount(self.copies_spin.value())
        printer.setFullPage(False)
        return printer

    def print_to(self, printer: QPrinter) -> bool:
        """
        Draws the picture onto a printer exactly where the preview shows it.

        Args:
            printer: Printer, already set to the chosen paper.

        Returns:
            bool: True when the page was drawn.
        """

        painter = QPainter()
        if not painter.begin(printer):
            return False
        try:
            paper = printer.paperRect(QPrinter.Unit.DevicePixel)
            page = printer.pageRect(QPrinter.Unit.DevicePixel)
            x, y, width, height = device_rect(
                self.layout_model.rect_mm,
                self.layout_model.page_size_mm,
                (paper.x(), paper.y(), paper.width(), paper.height()),
                (page.x(), page.y(), page.width(), page.height()),
            )
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(x, y, width, height), self._pixmap, QRectF(self._pixmap.rect()))
        finally:
            painter.end()
        return True

    def _on_print_clicked(self) -> None:
        """
        Prints, and closes the dialog when it worked.
        """

        printer = self.build_printer()
        if printer is None:
            return
        if not self.print_to(printer):
            QMessageBox.warning(self, "Print", "The printer could not be used.")
            return
        self.accept()
