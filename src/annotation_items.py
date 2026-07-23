"""
Annotation item definitions and conversion helpers.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QTransform,
)
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
ITEM_ROLE_ID = 1002
ITEM_ROLE_LOCKED = 1003
ITEM_ROLE_TRANSFORM = 1004

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


def normalize_transform_payload(payload: dict | None) -> dict[str, float | bool]:
    """
    Extracts and sanitizes geometric transform fields from a payload.

    Args:
        payload: Annotation payload dictionary.

    Returns:
        dict[str, float | bool]: Normalized transform keys.
    """

    source = payload if isinstance(payload, dict) else {}
    return {
        "rotation": float(source.get("rotation", 0.0) or 0.0),
        "mirror_h": bool(source.get("mirror_h", False)),
        "mirror_v": bool(source.get("mirror_v", False)),
        "skew_x": float(source.get("skew_x", 0.0) or 0.0),
        "skew_y": float(source.get("skew_y", 0.0) or 0.0),
    }


def transform_payload_from_item(item: QGraphicsItem) -> dict[str, float | bool]:
    """
    Reads stored geometric transform metadata from one graphics item.

    Args:
        item: Scene annotation item.

    Returns:
        dict[str, float | bool]: Normalized transform payload fragment.
    """

    stored = item.data(ITEM_ROLE_TRANSFORM)
    if isinstance(stored, dict):
        return normalize_transform_payload(stored)
    return normalize_transform_payload(None)


def merge_transform_into_payload(item: QGraphicsItem, payload: dict) -> dict:
    """
    Merges item transform metadata into an annotation payload.

    Args:
        item: Source graphics item.
        payload: Existing payload dictionary (mutated and returned).

    Returns:
        dict: Payload including transform fields when non-default.
    """

    transform = transform_payload_from_item(item)
    if abs(float(transform["rotation"])) > 0.001:
        payload["rotation"] = float(transform["rotation"])
    elif "rotation" in payload:
        del payload["rotation"]
    if transform["mirror_h"]:
        payload["mirror_h"] = True
    elif "mirror_h" in payload:
        del payload["mirror_h"]
    if transform["mirror_v"]:
        payload["mirror_v"] = True
    elif "mirror_v" in payload:
        del payload["mirror_v"]
    if abs(float(transform["skew_x"])) > 0.001:
        payload["skew_x"] = float(transform["skew_x"])
    elif "skew_x" in payload:
        del payload["skew_x"]
    if abs(float(transform["skew_y"])) > 0.001:
        payload["skew_y"] = float(transform["skew_y"])
    elif "skew_y" in payload:
        del payload["skew_y"]
    return payload


def apply_item_transform(
    item: QGraphicsItem,
    *,
    rotation: float = 0.0,
    mirror_h: bool = False,
    mirror_v: bool = False,
    skew_x: float = 0.0,
    skew_y: float = 0.0,
    base_scale_x: float = 1.0,
    base_scale_y: float = 1.0,
) -> None:
    """
    Applies rotation, mirror, and skew to one annotation item.

    Args:
        item: Target graphics item.
        rotation: Rotation in degrees.
        mirror_h: Horizontal mirror flag.
        mirror_v: Vertical mirror flag.
        skew_x: Horizontal skew angle in degrees.
        skew_y: Vertical skew angle in degrees.
        base_scale_x: Optional base X scale (used by image annotations).
        base_scale_y: Optional base Y scale (used by image annotations).

    Returns:
        None
    """

    payload = {
        "rotation": float(rotation),
        "mirror_h": bool(mirror_h),
        "mirror_v": bool(mirror_v),
        "skew_x": float(skew_x),
        "skew_y": float(skew_y),
        "base_scale_x": float(base_scale_x),
        "base_scale_y": float(base_scale_y),
    }
    item.setData(ITEM_ROLE_TRANSFORM, payload)
    local_rect = item.boundingRect()
    origin = local_rect.center()
    item.setTransformOriginPoint(origin)

    transform = QTransform()
    scale_x = (-1.0 if mirror_h else 1.0) * float(base_scale_x)
    scale_y = (-1.0 if mirror_v else 1.0) * float(base_scale_y)
    transform.scale(scale_x, scale_y)
    shear_x = math.tan(math.radians(float(skew_x))) if abs(float(skew_x)) > 0.001 else 0.0
    shear_y = math.tan(math.radians(float(skew_y))) if abs(float(skew_y)) > 0.001 else 0.0
    if abs(shear_x) > 0.0001 or abs(shear_y) > 0.0001:
        transform.shear(shear_x, shear_y)
    item.setTransform(transform)
    item.setRotation(float(rotation))


def apply_payload_transform(item: QGraphicsItem, payload: dict | None) -> None:
    """
    Applies transform fields from an annotation payload to a scene item.

    Args:
        item: Target graphics item.
        payload: Annotation payload.

    Returns:
        None
    """

    transform = normalize_transform_payload(payload)
    base_scale_x = 1.0
    base_scale_y = 1.0
    if isinstance(item, QGraphicsPixmapItem):
        pixmap = item.pixmap()
        if pixmap.width() > 0 and pixmap.height() > 0:
            scene_w = float((payload or {}).get("_image_width", 0.0) or 0.0)
            scene_h = float((payload or {}).get("_image_height", 0.0) or 0.0)
            # Prefer explicit geometry when restoring from model dimensions.
            if scene_w > 0.0 and scene_h > 0.0:
                base_scale_x = scene_w / float(pixmap.width())
                base_scale_y = scene_h / float(pixmap.height())
    apply_item_transform(
        item,
        rotation=float(transform["rotation"]),
        mirror_h=bool(transform["mirror_h"]),
        mirror_v=bool(transform["mirror_v"]),
        skew_x=float(transform["skew_x"]),
        skew_y=float(transform["skew_y"]),
        base_scale_x=base_scale_x,
        base_scale_y=base_scale_y,
    )


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
        letter_spacing: Additional letter spacing in pixels.
        line_spacing_factor: Line spacing multiplier for multiline text.
        box_padding: Text container padding in pixels.
        corner_radius: Rounded container corner radius in pixels.
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
    letter_spacing: float = 0.0
    line_spacing_factor: float = 1.2
    box_padding: float = 10.0
    corner_radius: float = 6.0
    stroke_style: str = STROKE_STYLE_SOLID
    text_style: str = TEXT_STYLE_PLAIN


class StrokeLineItem(QGraphicsLineItem):
    """
    Line annotation with a thicker clickable stroke for reliable selection.
    """

    HIT_PADDING = 8.0

    def shape(self) -> QPainterPath:
        """
        Returns a stroked path around the line for mouse hit testing.

        Returns:
            QPainterPath: Clickable stroke geometry.
        """

        line = self.line()
        path = QPainterPath()
        if line.length() < 0.001:
            half = self.HIT_PADDING
            path.addRect(QRectF(line.p1().x() - half, line.p1().y() - half, half * 2.0, half * 2.0))
            return path

        base = QPainterPath()
        base.moveTo(line.p1())
        base.lineTo(line.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(float(self.pen().widthF()), 1.0) + (self.HIT_PADDING * 2.0))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(base)

    def boundingRect(self) -> QRectF:
        """
        Returns bounds that include the expanded hit stroke.

        Returns:
            QRectF: Item bounds for painting and layout.
        """

        return self.shape().controlPointRect().adjusted(-1.0, -1.0, 1.0, 1.0)


class ArrowItem(StrokeLineItem):
    """
    Draws a line with an arrow head at the end.
    """

    def _arrow_head_path(self) -> QPainterPath:
        """
        Builds the triangular arrow head path at the line end.

        Returns:
            QPainterPath: Closed arrow-head triangle, or empty when too short.
        """

        line = self.line()
        path = QPainterPath()
        length = float(line.length())
        if length < 1.0:
            return path

        # Use the geometric direction p1→p2 in screen coordinates so the head
        # always follows the drawn shaft (independent of QLineF.angle quirks).
        dx = float(line.dx()) / length
        dy = float(line.dy()) / length
        size = max(8.0, float(self.pen().widthF()) * 3.0)
        tip = line.p2()
        back_x = -dx
        back_y = -dy
        # Wing directions: rotate the back vector by ±30°.
        left = QPointF(
            tip.x() + size * (back_x * math.cos(math.radians(30.0)) - back_y * math.sin(math.radians(30.0))),
            tip.y() + size * (back_x * math.sin(math.radians(30.0)) + back_y * math.cos(math.radians(30.0))),
        )
        right = QPointF(
            tip.x() + size * (back_x * math.cos(math.radians(-30.0)) - back_y * math.sin(math.radians(-30.0))),
            tip.y() + size * (back_x * math.sin(math.radians(-30.0)) + back_y * math.cos(math.radians(-30.0))),
        )
        path.moveTo(tip)
        path.lineTo(left)
        path.lineTo(right)
        path.closeSubpath()
        return path

    def shape(self) -> QPainterPath:
        """
        Returns clickable geometry for the shaft and arrow head.

        Returns:
            QPainterPath: Combined hit area.
        """

        path = super().shape()
        head = self._arrow_head_path()
        if not head.isEmpty():
            path.addPath(head)
        return path

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
        head = self._arrow_head_path()
        if head.isEmpty():
            return

        pen = self.pen()
        painter.setPen(pen)
        painter.setBrush(pen.color())
        painter.drawPath(head)


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

    A stroke width of ``0`` disables the border (``NoPen``). Qt treats a pen
    width of ``0`` as a cosmetic hairline, so borderless shapes must use NoPen.

    Args:
        style: Active style state.

    Returns:
        QPen: Configured pen.
    """

    return create_stroke_pen(
        style.stroke_color,
        style.stroke_width,
        stroke_style=style.stroke_style,
    )


def create_stroke_pen(
    color: QColor,
    width: float,
    *,
    stroke_style: str = STROKE_STYLE_SOLID,
) -> QPen:
    """
    Builds a stroke pen, using NoPen when width is zero.

    Args:
        color: Stroke color retained even when the pen is disabled.
        width: Stroke thickness in pixels; ``0`` means no border.
        stroke_style: Named stroke style for visible pens.

    Returns:
        QPen: Configured pen.
    """

    if float(width) <= 0.0:
        pen = QPen(Qt.PenStyle.NoPen)
        pen.setColor(color)
        pen.setWidthF(0.0)
        return pen
    pen = QPen(color, float(width))
    pen.setStyle(stroke_style_to_qt(stroke_style))
    pen.setCosmetic(False)
    return pen


def pen_stroke_width(pen: QPen) -> float:
    """
    Returns the logical stroke width for one pen.

    Args:
        pen: Source pen.

    Returns:
        float: ``0`` when the pen is disabled, otherwise ``widthF()``.
    """

    if pen.style() == Qt.PenStyle.NoPen:
        return 0.0
    return float(pen.widthF())


def apply_stroke_width_to_pen(pen: QPen, width: float, *, stroke_style: str | None = None) -> QPen:
    """
    Updates pen width, switching to NoPen when width is zero.

    Args:
        pen: Pen to update.
        width: New stroke thickness in pixels.
        stroke_style: Optional style restored when re-enabling a border.

    Returns:
        QPen: Updated pen.
    """

    resolved = float(width)
    if resolved <= 0.0:
        color = pen.color()
        disabled = QPen(Qt.PenStyle.NoPen)
        disabled.setColor(color)
        disabled.setWidthF(0.0)
        return disabled
    if pen.style() == Qt.PenStyle.NoPen:
        style_name = stroke_style if stroke_style is not None else STROKE_STYLE_SOLID
        pen.setStyle(stroke_style_to_qt(style_name))
    elif stroke_style is not None:
        pen.setStyle(stroke_style_to_qt(stroke_style))
    pen.setWidthF(resolved)
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
    if not item.data(ITEM_ROLE_ID):
        item.setData(ITEM_ROLE_ID, uuid4().hex)
    if item.data(ITEM_ROLE_LOCKED) is None:
        item.setData(ITEM_ROLE_LOCKED, False)


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
        merge_transform_into_payload(item, model.payload)
        return model

    if annotation_type == "text" and isinstance(item, StyledTextItem):
        model = annotation_from_styled_text_item(item)
        model.payload["z_index"] = item.zValue()
        merge_transform_into_payload(item, model.payload)
        return model

    if annotation_type in {"rect", "ellipse"}:
        shape_item = cast(QGraphicsRectItem | QGraphicsEllipseItem, item)
        rect = shape_item.rect().translated(shape_item.pos())
        pen = shape_item.pen()
        brush = shape_item.brush()
        payload = {
            "stroke_style": _stroke_style_from_pen(pen),
            "z_index": item.zValue(),
        }
        merge_transform_into_payload(item, payload)
        return AnnotationModel(
            annotation_type=annotation_type,
            x=rect.x(),
            y=rect.y(),
            width=rect.width(),
            height=rect.height(),
            stroke_rgba=color_to_list(pen.color()),
            fill_rgba=color_to_list(brush.color()),
            stroke_width=pen_stroke_width(pen),
            payload=payload,
        )

    if annotation_type in {"line", "arrow"}:
        line_item = cast(QGraphicsLineItem, item)
        line = line_item.line()
        pen = line_item.pen()
        payload = {
            "stroke_style": _stroke_style_from_pen(pen),
            "z_index": item.zValue(),
        }
        merge_transform_into_payload(item, payload)
        return AnnotationModel(
            annotation_type=annotation_type,
            x=line.p1().x() + line_item.pos().x(),
            y=line.p1().y() + line_item.pos().y(),
            width=line.p2().x() - line.p1().x(),
            height=line.p2().y() - line.p1().y(),
            stroke_rgba=color_to_list(pen.color()),
            fill_rgba=[0, 0, 0, 0],
            stroke_width=pen_stroke_width(pen),
            payload=payload,
        )

    if annotation_type == "text":
        text_item = cast(QGraphicsTextItem, item)
        rect = text_item.boundingRect().translated(text_item.pos())
        color = text_item.defaultTextColor()
        payload = {
            "text_style": TEXT_STYLE_PLAIN,
            "letter_spacing": float(text_item.font().letterSpacing()),
            "z_index": item.zValue(),
        }
        merge_transform_into_payload(item, payload)
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
            payload=payload,
        )

    if annotation_type == "image":
        image_item = cast(QGraphicsPixmapItem, item)
        pixmap = image_item.pixmap()
        stored = image_item.data(ITEM_ROLE_TRANSFORM)
        base_scale_x = 1.0
        base_scale_y = 1.0
        if isinstance(stored, dict):
            base_scale_x = float(stored.get("base_scale_x", 1.0) or 1.0)
            base_scale_y = float(stored.get("base_scale_y", 1.0) or 1.0)
        width = float(pixmap.width()) * abs(base_scale_x) if pixmap.width() > 0 else 1.0
        height = float(pixmap.height()) * abs(base_scale_y) if pixmap.height() > 0 else 1.0
        payload = {"image_png_base64": image_item.data(2001), "z_index": item.zValue()}
        merge_transform_into_payload(item, payload)
        return AnnotationModel(
            annotation_type=annotation_type,
            x=image_item.pos().x(),
            y=image_item.pos().y(),
            width=width,
            height=height,
            stroke_rgba=[0, 0, 0, 0],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=0.0,
            payload=payload,
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
    pen = create_stroke_pen(
        stroke,
        annotation.stroke_width,
        stroke_style=str(annotation.payload.get("stroke_style", STROKE_STYLE_SOLID)),
    )
    rect = QRectF(annotation.x, annotation.y, annotation.width, annotation.height)

    if annotation.annotation_type == "step":
        item = add_step_to_scene(scene, annotation)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        apply_payload_transform(item, annotation.payload)
        return item
    if annotation.annotation_type == "text" and is_styled_text_annotation(annotation):
        item = add_styled_text_to_scene(scene, annotation)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        apply_payload_transform(item, annotation.payload)
        return item
    if annotation.annotation_type == "rect":
        item = scene.addRect(rect, pen, fill)
        configure_graphics_item(item, "rect")
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        apply_payload_transform(item, annotation.payload)
        return item
    if annotation.annotation_type == "ellipse":
        item = scene.addEllipse(rect, pen, fill)
        configure_graphics_item(item, "ellipse")
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        apply_payload_transform(item, annotation.payload)
        return item
    if annotation.annotation_type == "line":
        item = StrokeLineItem(
            annotation.x,
            annotation.y,
            annotation.x + annotation.width,
            annotation.y + annotation.height,
        )
        item.setPen(apply_stored_pen_style(pen, annotation.payload))
        configure_graphics_item(item, "line")
        scene.addItem(item)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        apply_payload_transform(item, annotation.payload)
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
        apply_payload_transform(item, annotation.payload)
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
        font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            float(annotation.payload.get("letter_spacing", 0.0)),
        )
        item.setFont(font)
        item.setDefaultTextColor(stroke)
        item.setPos(annotation.x, annotation.y)
        configure_graphics_item(item, "text")
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        apply_payload_transform(item, annotation.payload)
        return item
    if annotation.annotation_type == "image":
        encoded = str(annotation.payload.get("image_png_base64", ""))
        if not encoded:
            return None
        item = QGraphicsPixmapItem(_decode_base64_to_pixmap(encoded))
        item.setPos(annotation.x, annotation.y)
        configure_graphics_item(item, "image")
        item.setData(2001, encoded)
        scene.addItem(item)
        item.setZValue(float(annotation.payload.get("z_index", 0.0)))
        image_payload = dict(annotation.payload)
        image_payload["_image_width"] = float(annotation.width)
        image_payload["_image_height"] = float(annotation.height)
        apply_payload_transform(item, image_payload)
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

