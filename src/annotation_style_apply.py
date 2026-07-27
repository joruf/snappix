"""
Shared per-item style application for the image and video annotation canvases.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsItem

from src.annotation_items import (
    ITEM_ROLE_LOCKED,
    ITEM_ROLE_TYPE,
    apply_stroke_width_to_pen,
    create_stroke_pen,
    stroke_style_to_qt,
)
from src.annotation_shapes import StepBadgeItem, StyledTextItem
from src.shape_items import SHAPE_LINE_TYPES, SHAPE_RECT_TYPES, STAMP_MARK_TYPES


def apply_style_to_annotation_item(
    item: QGraphicsItem,
    *,
    stroke_color=None,
    fill_color=None,
    text_color=None,
    stroke_width: float | None = None,
    font_size: int | None = None,
    font_family: str | None = None,
    font_bold: bool | None = None,
    font_italic: bool | None = None,
    font_underline: bool | None = None,
    letter_spacing: float | None = None,
    line_spacing_factor: float | None = None,
    box_padding: float | None = None,
    corner_radius: float | None = None,
    stroke_style: str | None = None,
    text_style: str | None = None,
    styled_text_types: frozenset[str] = frozenset({"text"}),
) -> bool:
    """
    Applies style fields to one selected annotation item in place.

    Shared between the image and video canvases for the annotation kinds
    that both support (shape/stamp rects, step badges, lines, styled text).
    Kinds unique to one canvas (e.g. legacy plain-text items in the image
    editor) are handled by the caller when this returns False.

    Args:
        item: Scene item to restyle.
        stroke_color: Optional new stroke color.
        fill_color: Optional new fill color.
        text_color: Optional new text color.
        stroke_width: Optional new stroke width.
        font_size: Optional new font size.
        font_family: Optional new font family.
        font_bold: Optional bold state for text.
        font_italic: Optional italic state for text.
        font_underline: Optional underline state for text.
        letter_spacing: Optional letter spacing in pixels.
        line_spacing_factor: Optional line-spacing multiplier.
        box_padding: Optional text container padding in pixels.
        corner_radius: Optional text container corner radius in pixels.
        stroke_style: Optional line style name.
        text_style: Optional text container style.
        styled_text_types: Annotation type identifiers treated as styled text
            (the image editor uses ``{"text"}``, the video editor also
            includes its callout tool).

    Returns:
        bool: True when the item matched a known kind and was restyled.
    """

    if bool(item.data(ITEM_ROLE_LOCKED) or False):
        return False
    annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")

    if annotation_type in SHAPE_RECT_TYPES:
        shape_item = item
        if annotation_type in STAMP_MARK_TYPES:
            # Cross/checkmark are filled stamps: Border and Fill both
            # update the visible mark color (brush), keeping NoPen.
            mark_color = stroke_color if stroke_color is not None else fill_color
            if mark_color is not None:
                shape_item.setBrush(mark_color)
                shape_item.setPen(create_stroke_pen(mark_color, 0.0))
            return True
        if stroke_color is not None:
            pen = shape_item.pen()
            pen.setColor(stroke_color)
            shape_item.setPen(pen)
        if fill_color is not None:
            shape_item.setBrush(fill_color)
        if stroke_width is not None:
            shape_item.setPen(
                apply_stroke_width_to_pen(
                    shape_item.pen(),
                    stroke_width,
                    stroke_style=stroke_style,
                )
            )
        elif stroke_style is not None and shape_item.pen().style() != Qt.PenStyle.NoPen:
            pen = shape_item.pen()
            pen.setStyle(stroke_style_to_qt(stroke_style))
            shape_item.setPen(pen)
        return True

    if annotation_type == "step" and isinstance(item, StepBadgeItem):
        if stroke_color is not None:
            pen = item.pen()
            pen.setColor(stroke_color)
            item.setPen(pen)
        if fill_color is not None:
            item.setBrush(fill_color)
        if stroke_width is not None:
            item.setPen(
                apply_stroke_width_to_pen(
                    item.pen(),
                    stroke_width,
                    stroke_style=stroke_style,
                )
            )
        return True

    if annotation_type in SHAPE_LINE_TYPES:
        line_item = item
        pen = line_item.pen()
        if stroke_color is not None:
            pen.setColor(stroke_color)
        if stroke_width is not None:
            pen = apply_stroke_width_to_pen(
                pen,
                stroke_width,
                stroke_style=stroke_style,
            )
        elif stroke_style is not None and pen.style() != Qt.PenStyle.NoPen:
            pen.setStyle(stroke_style_to_qt(stroke_style))
        line_item.setPen(pen)
        return True

    if annotation_type in styled_text_types and isinstance(item, StyledTextItem):
        if text_color is not None:
            item.set_colors(text_color=text_color)
        if stroke_color is not None:
            item.set_colors(stroke_color=stroke_color)
        if fill_color is not None:
            item.set_colors(fill_color=fill_color)
        if stroke_width is not None:
            item.set_stroke_width(float(stroke_width))
        if text_style is not None:
            item.set_text_style(text_style)
        if (
            font_size is not None
            or font_family is not None
            or font_bold is not None
            or font_italic is not None
            or font_underline is not None
        ):
            font = QFont(item.font())
            if font_size is not None:
                font.setPointSize(max(1, int(font_size)))
            if font_family is not None and font_family.strip():
                font.setFamily(font_family.strip())
            if font_bold is not None:
                font.setBold(bool(font_bold))
            if font_italic is not None:
                font.setItalic(bool(font_italic))
            if font_underline is not None:
                font.setUnderline(bool(font_underline))
            item.set_font(font)
        if (
            letter_spacing is not None
            or line_spacing_factor is not None
            or box_padding is not None
            or corner_radius is not None
        ):
            item.set_layout_options(
                letter_spacing=letter_spacing,
                line_spacing_factor=line_spacing_factor,
                box_padding=box_padding,
                corner_radius=corner_radius,
            )
        return True

    return False
