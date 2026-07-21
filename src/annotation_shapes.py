"""
Custom annotation graphics items for advanced editor tools.
"""

from __future__ import annotations

import math
from typing import cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
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

        painter.setPen(QPen(QColor(255, 255, 255, 240), 2.0))
        painter.setBrush(QBrush(QColor(231, 76, 60, 240)))
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
        """

        super().__init__()
        self._text = text
        self._text_style = text_style
        self._font = font or QFont()
        self._text_color = text_color or QColor(44, 62, 80, 255)
        self._fill_color = fill_color or QColor(255, 255, 255, 230)
        self._stroke_color = stroke_color or QColor(52, 73, 94, 255)
        self._stroke_width = stroke_width
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

        painter.setFont(self._font)
        if self._text_style == TEXT_STYLE_PLAIN:
            painter.setPen(self._text_color)
            painter.drawText(self._text_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), self._text)
            return

        path = self._container_path()
        painter.setPen(QPen(self._stroke_color, self._stroke_width))
        painter.setBrush(QBrush(self._fill_color))
        painter.drawPath(path)
        painter.setPen(self._text_color)
        painter.drawText(self._text_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), self._text)

    def _rebuild_metrics(self) -> None:
        """
        Recomputes text and container geometry.

        Returns:
            None
        """

        metrics = QFont(self._font)
        painter_path = QPainterPath()
        painter_path.addText(QPointF(0.0, 0.0), metrics, self._text)
        raw_bounds = painter_path.boundingRect()
        padding = 10.0 if self._text_style != TEXT_STYLE_PLAIN else 0.0
        self._text_rect = raw_bounds.adjusted(padding, padding, padding, padding)
        self._bounds = self._text_rect
        if self._text_style == TEXT_STYLE_BUBBLE:
            self._bounds = self._bounds.adjusted(0.0, 0.0, 0.0, 14.0)
        self.prepareGeometryChange()

    def _container_path(self) -> QPainterPath:
        """
        Builds the background path for box and bubble styles.

        Returns:
            QPainterPath: Container outline path.
        """

        rect = self._text_rect.adjusted(-2.0, -2.0, 2.0, 2.0)
        if self._text_style == TEXT_STYLE_BOX:
            path = QPainterPath()
            path.addRoundedRect(rect, 6.0, 6.0)
            return path

        radius = min(rect.width(), rect.height()) * 0.18
        tail_width = min(18.0, rect.width() * 0.22)
        tail_height = 14.0
        bubble_rect = rect.adjusted(0.0, 0.0, 0.0, -tail_height)
        path = QPainterPath()
        path.addRoundedRect(bubble_rect, radius, radius)
        tail_left = bubble_rect.left() + bubble_rect.width() * 0.2
        tail_tip = QPointF(tail_left + tail_width * 0.5, bubble_rect.bottom() + tail_height)
        path.lineTo(tail_left + tail_width, bubble_rect.bottom())
        path.lineTo(tail_tip)
        path.lineTo(tail_left, bubble_rect.bottom())
        path.closeSubpath()
        return path


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
        payload={"text_style": item.text_style()},
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
    item = StyledTextItem(
        text=annotation.text,
        text_style=text_style,
        font=font,
        text_color=QColor(*annotation.stroke_rgba),
        fill_color=QColor(*annotation.fill_rgba),
        stroke_color=QColor(*annotation.stroke_rgba),
        stroke_width=annotation.stroke_width,
    )
    item.setPos(annotation.x, annotation.y)
    scene.addItem(item)
    return item


def is_styled_text_annotation(annotation: AnnotationModel) -> bool:
    """
    Indicates whether one text annotation uses a styled container.

    Args:
        annotation: Annotation model.

    Returns:
        bool: True for box or speech bubble text.
    """

    text_style = str(annotation.payload.get("text_style", TEXT_STYLE_PLAIN))
    return text_style in {TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE}
