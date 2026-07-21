"""
Annotation item definitions and conversion helpers.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from src.annotation_shapes import TEXT_STYLE_PLAIN
from src.models import AnnotationModel

ITEM_ROLE_TYPE = 1001

STROKE_STYLE_SOLID = "solid"
STROKE_STYLE_DASH = "dash"
STROKE_STYLE_DOT = "dot"
STROKE_STYLE_DASH_DOT = "dash_dot"
STROKE_STYLE_VALUES = {
    STROKE_STYLE_SOLID: Qt.PenStyle.SolidLine,
    STROKE_STYLE_DASH: Qt.PenStyle.DashLine,
    STROKE_STYLE_DOT: Qt.PenStyle.DotLine,
    STROKE_STYLE_DASH_DOT: Qt.PenStyle.DashDotLine,
}


def normalize_stroke_style(value: str) -> str:
    """
    Returns a supported stroke style identifier.

    Args:
        value: Requested stroke style.

    Returns:
        str: Valid stroke style identifier.
    """

    if value in STROKE_STYLE_VALUES:
        return value
    return STROKE_STYLE_SOLID


def stroke_style_to_qt(value: str) -> Qt.PenStyle:
    """
    Converts one stroke style identifier to a Qt pen style.

    Args:
        value: Stroke style identifier.

    Returns:
        Qt.PenStyle: Matching Qt pen style.
    """

    return STROKE_STYLE_VALUES[normalize_stroke_style(value)]


@dataclass(slots=True)
class StyleState:
    """
    Aggregates drawing style options used for new annotations.

    Attributes:
        stroke_color: Pen color.
        fill_color: Brush color.
        text_color: Text color.
        stroke_width: Pen thickness.
        font_size: Font size for text annotations.
        font_family: Font family for text annotations.
        font_bold: Bold style for text annotations.
        font_italic: Italic style for text annotations.
        font_underline: Underline style for text annotations.
        stroke_style: Line style for line and arrow annotations.
        text_style: Container style for text annotations.
    """

    stroke_color: QColor
    fill_color: QColor
    text_color: QColor
    stroke_width: float
    font_size: int
    font_family: str
    font_bold: bool
    font_italic: bool
    font_underline: bool
    stroke_style: str = STROKE_STYLE_SOLID
    text_style: str = TEXT_STYLE_PLAIN


class ArrowItem(QGraphicsLineItem):
    """
    Draws a line with an arrow head at the end.
    """

    def paint(
        self,
        painter: QPainter,
        option,
        widget=None,
    ) -> None:
        """
        Paints the arrow with line and end-cap triangle.

        Args:
            painter: Painter used by Qt.
            option: Style option from Qt.
            widget: Optional target widget.

        Returns:
            None
        """

        super().paint(painter, option, widget)
        line = self.line()
        if line.length() < 1:
            return

        pen = self.pen()
        painter.setPen(pen)
        painter.setBrush(pen.color())

        angle = math.radians(line.angle())
        size = max(8.0, pen.widthF() * 3.0)
        p2 = line.p2()
        left = QPointF(
            p2.x() + size * math.cos(angle + math.radians(150)),
            p2.y() - size * math.sin(angle + math.radians(150)),
        )
        right = QPointF(
            p2.x() + size * math.cos(angle - math.radians(150)),
            p2.y() - size * math.sin(angle - math.radians(150)),
        )
        path = QPainterPath()
        path.moveTo(p2)
        path.lineTo(left)
        path.lineTo(right)
        path.closeSubpath()
        painter.drawPath(path)


def color_to_list(color: QColor) -> list[int]:
    """
    Converts QColor into RGBA integer components.

    Args:
        color: Source QColor.

    Returns:
        list[int]: [r, g, b, a] values.
    """

    return [color.red(), color.green(), color.blue(), color.alpha()]


def list_to_color(values: list[int]) -> QColor:
    """
    Converts RGBA list into QColor.

    Args:
        values: [r, g, b, a] values.

    Returns:
        QColor: Converted color.
    """

    if len(values) != 4:
        return QColor(255, 0, 0, 255)
    return QColor(values[0], values[1], values[2], values[3])


def create_pen(style: StyleState) -> QPen:
    """
    Creates a pen from current style.

    Args:
        style: Active style state.

    Returns:
        QPen: Configured pen.
    """

    pen = QPen(style.stroke_color, style.stroke_width)
    pen.setStyle(stroke_style_to_qt(style.stroke_style))
    pen.setCosmetic(False)
    return pen


def apply_stored_pen_style(pen: QPen, payload: dict) -> QPen:
    """
    Applies serialized stroke style values to one pen.

    Args:
        pen: Base pen.
        payload: Annotation payload dictionary.

    Returns:
        QPen: Updated pen.
    """

    stroke_style = normalize_stroke_style(str(payload.get("stroke_style", STROKE_STYLE_SOLID)))
    pen.setStyle(stroke_style_to_qt(stroke_style))
    return pen


def configure_graphics_item(item: QGraphicsItem, annotation_type: str) -> None:
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


def annotation_from_item(item: QGraphicsItem) -> AnnotationModel | None:
    """
    Converts a graphics item to a serializable annotation model.

    Args:
        item: Scene item.

    Returns:
        AnnotationModel | None: Serialized annotation or None if unsupported.
    """

    from src.annotation_shapes import (
        StepBadgeItem,
        StyledTextItem,
        annotation_from_step_item,
        annotation_from_styled_text_item,
    )

    annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
    if annotation_type == "step" and isinstance(item, StepBadgeItem):
        model = annotation_from_step_item(item)
        model.payload["z_index"] = item.zValue()
        return model

    if annotation_type == "text" and isinstance(item, StyledTextItem):
        model = annotation_from_styled_text_item(item)
        model.payload["z_index"] = item.zValue()
        return model

    if annotation_type in {"rect", "ellipse"}:
        shape_item = cast(QGraphicsRectItem | QGraphicsEllipseItem, item)
        rect = shape_item.rect().translated(shape_item.pos())
        pen = shape_item.pen()
        brush = shape_item.brush()
        return AnnotationModel(
            annotation_type=annotation_type,
            x=rect.x(),
            y=rect.y(),
            width=rect.width(),
            height=rect.height(),
            stroke_rgba=color_to_list(pen.color()),
            fill_rgba=color_to_list(brush.color()),
            stroke_width=pen.widthF(),
            payload={"z_index": item.zValue()},
        )

    if annotation_type in {"line", "arrow"}:
        line_item = cast(QGraphicsLineItem, item)
        line = line_item.line()
        pen = line_item.pen()
        return AnnotationModel(
            annotation_type=annotation_type,
            x=line.p1().x() + line_item.pos().x(),
            y=line.p1().y() + line_item.pos().y(),
            width=line.p2().x() - line.p1().x(),
            height=line.p2().y() - line.p1().y(),
            stroke_rgba=color_to_list(pen.color()),
            fill_rgba=[0, 0, 0, 0],
            stroke_width=pen.widthF(),
            payload={
                "stroke_style": _stroke_style_from_pen(pen),
                "z_index": item.zValue(),
            },
        )

    if annotation_type == "text":
        text_item = cast(QGraphicsTextItem, item)
        rect = text_item.boundingRect().translated(text_item.pos())
        color = text_item.defaultTextColor()
        return AnnotationModel(
            annotation_type=annotation_type,
            x=rect.x(),
            y=rect.y(),
            width=rect.width(),
            height=rect.height(),
            stroke_rgba=color_to_list(color),
            fill_rgba=[0, 0, 0, 0],
            stroke_width=1.0,
            text=text_item.toPlainText(),
            font_size=text_item.font().pointSize(),
            font_family=text_item.font().family(),
            font_bold=text_item.font().bold(),
            font_italic=text_item.font().italic(),
            font_underline=text_item.font().underline(),
            payload={"text_style": TEXT_STYLE_PLAIN, "z_index": item.zValue()},
        )

    if annotation_type == "image":
        image_item = cast(QGraphicsPixmapItem, item)
        rect = image_item.sceneBoundingRect().normalized()
        return AnnotationModel(
            annotation_type=annotation_type,
            x=rect.x(),
            y=rect.y(),
            width=rect.width(),
            height=rect.height(),
            stroke_rgba=[0, 0, 0, 0],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=0.0,
            payload={"image_png_base64": image_item.data(2001), "z_index": item.zValue()},
        )

    return None


def add_annotation_to_scene(
    scene: QGraphicsScene,
    annotation: AnnotationModel,
) -> QGraphicsItem | None:
    """
    Recreates one annotation model as a scene item.

    Args:
        scene: Target graphics scene.
        annotation: Serialized annotation model.

    Returns:
        QGraphicsItem | None: Created item.
    """

    from src.annotation_shapes import (
        add_step_to_scene,
        add_styled_text_to_scene,
        is_styled_text_annotation,
    )

    stroke = list_to_color(annotation.stroke_rgba)
    fill = list_to_color(annotation.fill_rgba)
    pen = QPen(stroke, annotation.stroke_width)
    rect = QRectF(annotation.x, annotation.y, annotation.width, annotation.height)

    if annotation.annotation_type == "step":
        item = add_step_to_scene(scene, annotation)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item
    if annotation.annotation_type == "text" and is_styled_text_annotation(annotation):
        item = add_styled_text_to_scene(scene, annotation)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item
    if annotation.annotation_type == "rect":
        item = scene.addRect(rect, pen, fill)
        configure_graphics_item(item, "rect")
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item
    if annotation.annotation_type == "ellipse":
        item = scene.addEllipse(rect, pen, fill)
        configure_graphics_item(item, "ellipse")
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item
    if annotation.annotation_type == "line":
        item = scene.addLine(
            annotation.x,
            annotation.y,
            annotation.x + annotation.width,
            annotation.y + annotation.height,
            apply_stored_pen_style(pen, annotation.payload),
        )
        configure_graphics_item(item, "line")
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item
    if annotation.annotation_type == "arrow":
        item = ArrowItem(
            annotation.x,
            annotation.y,
            annotation.x + annotation.width,
            annotation.y + annotation.height,
        )
        item.setPen(apply_stored_pen_style(pen, annotation.payload))
        configure_graphics_item(item, "arrow")
        scene.addItem(item)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item
    if annotation.annotation_type == "text":
        item = scene.addText(annotation.text)
        font = QFont(item.font())
        font.setPointSize(annotation.font_size)
        if annotation.font_family:
            font.setFamily(annotation.font_family)
        font.setBold(annotation.font_bold)
        font.setItalic(annotation.font_italic)
        font.setUnderline(annotation.font_underline)
        item.setFont(font)
        item.setDefaultTextColor(stroke)
        item.setPos(annotation.x, annotation.y)
        configure_graphics_item(item, "text")
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item
    if annotation.annotation_type == "image":
        encoded = str(annotation.payload.get("image_png_base64", ""))
        if not encoded:
            return None
        item = QGraphicsPixmapItem(_decode_base64_to_pixmap(encoded))
        item.setPos(annotation.x, annotation.y)
        pixmap = item.pixmap()
        if pixmap.width() > 0 and pixmap.height() > 0:
            scale_x = annotation.width / pixmap.width()
            scale_y = annotation.height / pixmap.height()
            item.setTransform(QTransform.fromScale(scale_x, scale_y))
        configure_graphics_item(item, "image")
        item.setData(2001, encoded)
        scene.addItem(item)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        return item

    return None


def _stroke_style_from_pen(pen: QPen) -> str:
    """
    Converts one Qt pen style to a serialized stroke style identifier.

    Args:
        pen: Source pen.

    Returns:
        str: Stroke style identifier.
    """

    for key, value in STROKE_STYLE_VALUES.items():
        if pen.style() == value:
            return key
    return STROKE_STYLE_SOLID


def _decode_base64_to_pixmap(value: str) -> QPixmap:
    """
    Decodes Base64 PNG data to QPixmap.

    Args:
        value: Base64 encoded PNG bytes.

    Returns:
        QPixmap: Decoded pixmap.
    """

    data = base64.b64decode(value.encode("utf-8"))
    image = QImage()
    image.loadFromData(data, "PNG")
    return QPixmap.fromImage(image)

