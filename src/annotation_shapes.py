"""
Custom annotation graphics items for advanced editor tools.
"""

from __future__ import annotations

import math
from typing import cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from src.models import AnnotationModel

ITEM_ROLE_TYPE = 1001


def _configure_graphics_item(item: QGraphicsItem, annotation_type: str) -> None:
    """
    Applies generic selection flags and metadata to an item.

    Args:
        item: Graphics item to configure.
        annotation_type: Logical annotation type.

    Returns:
        None
    """

    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    item.setData(ITEM_ROLE_TYPE, annotation_type)


TEXT_STYLE_PLAIN = "plain"
TEXT_STYLE_BOX = "box"
TEXT_STYLE_BUBBLE = "speech_bubble"


class StepBadgeItem(QGraphicsEllipseItem):
    """
    Draws a numbered step badge used in tutorial callouts.
    """

    def __init__(self, step_number: int, diameter: float = 36.0) -> None:
        """
        Initializes one numbered step badge.

        Args:
            step_number: Visible step number.
            diameter: Badge diameter in scene pixels.
        """

        super().__init__(0.0, 0.0, diameter, diameter)
        self._step_number = step_number
        self._label = QGraphicsTextItem(str(step_number), self)
        label_font = QFont(self._label.font())
        label_font.setBold(True)
        label_font.setPointSize(14)
        self._label.setFont(label_font)
        self._label.setDefaultTextColor(QColor(255, 255, 255, 255))
        self.setPen(QPen(QColor(255, 255, 255, 240), 2.0))
        self.setBrush(QBrush(QColor(231, 76, 60, 240)))
        self._center_label()
        _configure_graphics_item(self, "step")

    def step_number(self) -> int:
        """
        Returns the badge step number.

        Returns:
            int: Step number.
        """

        return self._step_number

    def set_step_number(self, step_number: int) -> None:
        """
        Updates the visible step number.

        Args:
            step_number: New step number.

        Returns:
            None
        """

        self._step_number = step_number
        self._label.setPlainText(str(step_number))
        self._center_label()

    def _center_label(self) -> None:
        """
        Centers the number label inside the badge ellipse.

        Returns:
            None
        """

        label_rect = self._label.boundingRect()
        self._label.setPos(
            (self.rect().width() - label_rect.width()) / 2.0,
            (self.rect().height() - label_rect.height()) / 2.0 - 1.0,
        )

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """
        Paints the filled badge and border.

        Args:
            painter: Active painter.
            option: Style options from Qt.
            widget: Optional widget being painted.

        Returns:
            None
        """

        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawEllipse(self.rect())


class StyledTextItem(QGraphicsItem):
    """
    Renders text inside a plain, boxed, or speech-bubble container.
    """

    def __init__(
        self,
        text: str,
        text_style: str = TEXT_STYLE_PLAIN,
        font: QFont | None = None,
        text_color: QColor | None = None,
        fill_color: QColor | None = None,
        stroke_color: QColor | None = None,
        stroke_width: float = 2.0,
        letter_spacing: float = 0.0,
        line_spacing_factor: float = 1.2,
        box_padding: float = 10.0,
        corner_radius: float = 6.0,
    ) -> None:
        """
        Initializes one styled text annotation item.

        Args:
            text: Visible text content.
            text_style: One of plain, box, or speech_bubble.
            font: Text font.
            text_color: Text color.
            fill_color: Background fill color.
            stroke_color: Border color.
            stroke_width: Border width.
            letter_spacing: Letter spacing in pixels.
            line_spacing_factor: Line spacing multiplier.
            box_padding: Container/text inset padding in pixels.
            corner_radius: Rounded corner radius in pixels.
        """

        super().__init__()
        self._text = text
        self._text_style = text_style
        self._font = font or QFont()
        self._text_color = text_color or QColor(44, 62, 80, 255)
        self._fill_color = fill_color or QColor(255, 255, 255, 230)
        self._stroke_color = stroke_color or QColor(52, 73, 94, 255)
        self._stroke_width = stroke_width
        self._letter_spacing = float(letter_spacing)
        self._line_spacing_factor = max(0.7, float(line_spacing_factor))
        self._box_padding = max(0.0, float(box_padding))
        self._corner_radius = max(0.0, float(corner_radius))
        self._text_rect = QRectF()
        self._bounds = QRectF()
        self._rebuild_metrics()
        _configure_graphics_item(self, "text")

    def text(self) -> str:
        """
        Returns the item text.

        Returns:
            str: Text content.
        """

        return self._text

    def text_style(self) -> str:
        """
        Returns the active text container style.

        Returns:
            str: Text style identifier.
        """

        return self._text_style

    def set_text(self, text: str) -> None:
        """
        Updates text content and geometry.

        Args:
            text: New text content.

        Returns:
            None
        """

        self._text = text
        self._rebuild_metrics()
        self.update()

    def set_font(self, font: QFont) -> None:
        """
        Updates the text font.

        Args:
            font: New font.

        Returns:
            None
        """

        self._font = QFont(font)
        self._rebuild_metrics()
        self.update()

    def set_text_style(self, text_style: str) -> None:
        """
        Updates the container style (plain, box, or speech bubble).

        Args:
            text_style: Target text style identifier.

        Returns:
            None
        """

        resolved = str(text_style or TEXT_STYLE_PLAIN).strip().lower()
        if resolved not in {TEXT_STYLE_PLAIN, TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE}:
            resolved = TEXT_STYLE_PLAIN
        if resolved == self._text_style:
            return
        self._text_style = resolved
        self._rebuild_metrics()
        self.update()

    def font(self) -> QFont:
        """
        Returns a copy of the active text font.

        Returns:
            QFont: Current font.
        """

        return QFont(self._font)

    def set_colors(
        self,
        text_color: QColor | None = None,
        fill_color: QColor | None = None,
        stroke_color: QColor | None = None,
    ) -> None:
        """
        Updates text and container colors.

        Args:
            text_color: Optional text color.
            fill_color: Optional fill color.
            stroke_color: Optional stroke color.

        Returns:
            None
        """

        if text_color is not None:
            self._text_color = text_color
        if fill_color is not None:
            self._fill_color = fill_color
        if stroke_color is not None:
            self._stroke_color = stroke_color
        self.update()

    def set_stroke_width(self, width: float) -> None:
        """
        Updates the container border width.

        Args:
            width: Border thickness in pixels; ``0`` draws no border.

        Returns:
            None
        """

        self._stroke_width = max(0.0, float(width))
        self.update()

    def set_layout_options(
        self,
        letter_spacing: float | None = None,
        line_spacing_factor: float | None = None,
        box_padding: float | None = None,
        corner_radius: float | None = None,
    ) -> None:
        """
        Updates text spacing and container geometry options.

        Args:
            letter_spacing: Optional letter spacing in pixels.
            line_spacing_factor: Optional line spacing multiplier.
            box_padding: Optional text/container padding in pixels.
            corner_radius: Optional rounded corner radius in pixels.

        Returns:
            None
        """

        if letter_spacing is not None:
            self._letter_spacing = float(letter_spacing)
        if line_spacing_factor is not None:
            self._line_spacing_factor = max(0.7, float(line_spacing_factor))
        if box_padding is not None:
            self._box_padding = max(0.0, float(box_padding))
        if corner_radius is not None:
            self._corner_radius = max(0.0, float(corner_radius))
        self._rebuild_metrics()
        self.update()

    def letter_spacing(self) -> float:
        """
        Returns the active letter spacing.

        Returns:
            float: Letter spacing in pixels.
        """

        return self._letter_spacing

    def line_spacing_factor(self) -> float:
        """
        Returns the active line-spacing multiplier.

        Returns:
            float: Line spacing multiplier.
        """

        return self._line_spacing_factor

    def box_padding(self) -> float:
        """
        Returns the active box padding.

        Returns:
            float: Padding in pixels.
        """

        return self._box_padding

    def corner_radius(self) -> float:
        """
        Returns the active corner radius.

        Returns:
            float: Corner radius in pixels.
        """

        return self._corner_radius

    def boundingRect(self) -> QRectF:
        """
        Returns the item bounds.

        Returns:
            QRectF: Bounding rectangle.
        """

        return self._bounds

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """
        Paints the styled text container.

        Args:
            painter: Active painter.
            option: Style options from Qt.
            widget: Optional widget being painted.

        Returns:
            None
        """

        draw_font = QFont(self._font)
        draw_font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            self._letter_spacing,
        )
        painter.setFont(draw_font)
        if self._text_style == TEXT_STYLE_PLAIN:
            painter.setPen(self._text_color)
            self._draw_multiline_text(painter)
            return

        path = self._container_path()
        if float(self._stroke_width) <= 0.0:
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setPen(QPen(self._stroke_color, self._stroke_width))
        painter.setBrush(QBrush(self._fill_color))
        painter.drawPath(path)
        painter.setPen(self._text_color)
        self._draw_multiline_text(painter)

    def _rebuild_metrics(self) -> None:
        """
        Recomputes text and container geometry.

        Returns:
            None
        """

        layout_font = QFont(self._font)
        layout_font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            self._letter_spacing,
        )
        metrics = QFontMetricsF(layout_font)
        lines = self._text.splitlines() or [self._text]
        if not lines:
            lines = [""]
        max_width = max((metrics.horizontalAdvance(line) for line in lines), default=0.0)
        line_height = metrics.height()
        line_spacing = max(line_height, line_height * self._line_spacing_factor)
        text_height = line_height + max(0, len(lines) - 1) * line_spacing
        raw_bounds = QRectF(0.0, 0.0, max(2.0, max_width), max(2.0, text_height))
        padding = self._box_padding if self._text_style != TEXT_STYLE_PLAIN else 0.0
        text_origin_x = padding
        text_origin_y = padding
        self.prepareGeometryChange()
        self._text_rect = QRectF(
            text_origin_x,
            text_origin_y,
            raw_bounds.width(),
            raw_bounds.height(),
        )
        self._bounds = QRectF(
            0.0,
            0.0,
            self._text_rect.right() + padding,
            self._text_rect.bottom() + padding,
        )
        if self._text_style == TEXT_STYLE_BUBBLE:
            # Reserve space below the padded text box for the speech-bubble tail.
            self._bounds = self._bounds.adjusted(0.0, 0.0, 0.0, self._bubble_tail_height())

    def _bubble_tail_height(self) -> float:
        """
        Returns the speech-bubble tail height in local pixels.

        Returns:
            float: Tail height.
        """

        return 14.0

    def _draw_multiline_text(self, painter: QPainter) -> None:
        """
        Draws text with explicit line spacing and letter spacing.

        Args:
            painter: Active painter.

        Returns:
            None
        """

        draw_font = painter.font()
        metrics = QFontMetricsF(draw_font)
        line_height = metrics.height()
        line_spacing = max(line_height, line_height * self._line_spacing_factor)
        y_base = self._text_rect.top() + metrics.ascent()
        for index, line in enumerate(self._text.splitlines() or [self._text]):
            painter.drawText(QPointF(self._text_rect.left(), y_base + index * line_spacing), line)

    def _container_path(self) -> QPainterPath:
        """
        Builds the background path for box and bubble styles.

        Returns:
            QPainterPath: Container outline path.
        """

        rect = self._text_rect.adjusted(-2.0, -2.0, 2.0, 2.0)
        if self._text_style == TEXT_STYLE_BOX:
            path = QPainterPath()
            radius = max(0.0, min(self._corner_radius, min(rect.width(), rect.height()) * 0.5))
            path.addRoundedRect(rect, radius, radius)
            return path

        radius = max(2.0, min(self._corner_radius, min(rect.width(), rect.height()) * 0.5))
        tail_height = self._bubble_tail_height()
        tail_width = min(18.0, max(10.0, rect.width() * 0.22))
        body = QPainterPath()
        body.addRoundedRect(rect, radius, radius)

        tail_left = rect.left() + rect.width() * 0.22
        tail_right = min(rect.right() - 2.0, tail_left + tail_width)
        tail_mid = (tail_left + tail_right) * 0.5
        tip = QPointF(tail_mid + tail_width * 0.15, rect.bottom() + tail_height)
        # Keep the tail base slightly inside the rounded body so the union seals.
        base_y = rect.bottom() - 1.0
        tail = QPainterPath()
        tail.moveTo(tail_left, base_y)
        tail.lineTo(tip)
        tail.lineTo(tail_right, base_y)
        tail.closeSubpath()
        return body.united(tail)


def annotation_from_step_item(item: StepBadgeItem) -> AnnotationModel:
    """
    Serializes one step badge item.

    Args:
        item: Step badge item.

    Returns:
        AnnotationModel: Serialized annotation.
    """

    rect = item.rect().translated(item.pos())
    pen = item.pen()
    brush = item.brush()
    return AnnotationModel(
        annotation_type="step",
        x=rect.x(),
        y=rect.y(),
        width=rect.width(),
        height=rect.height(),
        stroke_rgba=[pen.color().red(), pen.color().green(), pen.color().blue(), pen.color().alpha()],
        fill_rgba=[brush.color().red(), brush.color().green(), brush.color().blue(), brush.color().alpha()],
        stroke_width=pen.widthF(),
        text=str(item.step_number()),
        payload={"step_number": item.step_number()},
    )


def annotation_from_styled_text_item(item: StyledTextItem) -> AnnotationModel:
    """
    Serializes one styled text item.

    Args:
        item: Styled text item.

    Returns:
        AnnotationModel: Serialized annotation.
    """

    bounds = item.boundingRect().translated(item.pos())
    font = item._font
    return AnnotationModel(
        annotation_type="text",
        x=bounds.x(),
        y=bounds.y(),
        width=bounds.width(),
        height=bounds.height(),
        stroke_rgba=[item._stroke_color.red(), item._stroke_color.green(), item._stroke_color.blue(), item._stroke_color.alpha()],
        fill_rgba=[item._fill_color.red(), item._fill_color.green(), item._fill_color.blue(), item._fill_color.alpha()],
        stroke_width=item._stroke_width,
        text=item.text(),
        font_size=font.pointSize(),
        font_family=font.family(),
        font_bold=font.bold(),
        font_italic=font.italic(),
        font_underline=font.underline(),
        payload={
            "text_style": item.text_style(),
            "text_rgba": [
                item._text_color.red(),
                item._text_color.green(),
                item._text_color.blue(),
                item._text_color.alpha(),
            ],
            "letter_spacing": item.letter_spacing(),
            "line_spacing_factor": item.line_spacing_factor(),
            "box_padding": item.box_padding(),
            "corner_radius": item.corner_radius(),
        },
    )


def add_step_to_scene(scene: QGraphicsScene, annotation: AnnotationModel) -> StepBadgeItem:
    """
    Restores one step badge annotation on the scene.

    Args:
        scene: Target scene.
        annotation: Serialized annotation.

    Returns:
        StepBadgeItem: Created step badge item.
    """

    step_number = int(annotation.payload.get("step_number", annotation.text or "1"))
    item = StepBadgeItem(step_number, max(annotation.width, annotation.height, 36.0))
    item.setPos(annotation.x, annotation.y)
    if len(annotation.stroke_rgba) == 4:
        stroke = QColor(
            int(annotation.stroke_rgba[0]),
            int(annotation.stroke_rgba[1]),
            int(annotation.stroke_rgba[2]),
            int(annotation.stroke_rgba[3]),
        )
        width = max(1.0, float(annotation.stroke_width or 2.0))
        item.setPen(QPen(stroke, width))
    if len(annotation.fill_rgba) == 4:
        fill = QColor(
            int(annotation.fill_rgba[0]),
            int(annotation.fill_rgba[1]),
            int(annotation.fill_rgba[2]),
            int(annotation.fill_rgba[3]),
        )
        item.setBrush(QBrush(fill))
    scene.addItem(item)
    return item


def add_styled_text_to_scene(scene: QGraphicsScene, annotation: AnnotationModel) -> StyledTextItem:
    """
    Restores one styled text annotation on the scene.

    Args:
        scene: Target scene.
        annotation: Serialized annotation.

    Returns:
        StyledTextItem: Created text item.
    """

    font = QFont()
    font.setPointSize(annotation.font_size)
    if annotation.font_family:
        font.setFamily(annotation.font_family)
    font.setBold(annotation.font_bold)
    font.setItalic(annotation.font_italic)
    font.setUnderline(annotation.font_underline)
    text_style = str(annotation.payload.get("text_style", TEXT_STYLE_PLAIN))
    text_rgba = annotation.payload.get("text_rgba")
    if isinstance(text_rgba, list) and len(text_rgba) == 4:
        text_color = QColor(
            int(text_rgba[0]),
            int(text_rgba[1]),
            int(text_rgba[2]),
            int(text_rgba[3]),
        )
    else:
        text_color = QColor(*annotation.stroke_rgba)
    item = StyledTextItem(
        text=annotation.text,
        text_style=text_style,
        font=font,
        text_color=text_color,
        fill_color=QColor(*annotation.fill_rgba),
        stroke_color=QColor(*annotation.stroke_rgba),
        stroke_width=annotation.stroke_width,
        letter_spacing=float(annotation.payload.get("letter_spacing", 0.0)),
        line_spacing_factor=float(annotation.payload.get("line_spacing_factor", 1.2)),
        box_padding=float(annotation.payload.get("box_padding", 10.0)),
        corner_radius=float(annotation.payload.get("corner_radius", 6.0)),
    )
    item.setPos(annotation.x, annotation.y)
    scene.addItem(item)
    return item


def is_styled_text_annotation(annotation: AnnotationModel) -> bool:
    """
    Indicates whether one text annotation uses the styled text item path.

    Plain, box, and bubble text all restore as ``StyledTextItem`` when the
    payload declares a text style (including legacy plain payloads that only
    appear after a live promote). Box/bubble remain the historical trigger;
    plain payloads without ``text_style`` keep the legacy ``QGraphicsTextItem``
    loader for backwards compatibility.

    Args:
        annotation: Annotation model.

    Returns:
        bool: True when the annotation should restore as StyledTextItem.
    """

    text_style = str(annotation.payload.get("text_style", "")).strip().lower()
    if text_style in {TEXT_STYLE_PLAIN, TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE}:
        return True
    return False
