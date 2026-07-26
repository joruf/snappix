"""
Shared default draw styles and palette colors for image and video editors.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from src.annotation_items import STROKE_STYLE_SOLID, TEXT_STYLE_PLAIN, StyleState
from src.editor_canvas import Tool

DEFAULT_STROKE_COLOR = QColor(231, 76, 60, 255)
DEFAULT_FILL_COLOR = QColor(231, 76, 60, 80)
DEFAULT_TEXT_COLOR = QColor(44, 62, 80, 255)
MARK_CROSS_COLOR = QColor("#e74c3c")
MARK_CHECKMARK_COLOR = QColor("#2ecc71")

STYLE_PALETTE_COLORS: list[QColor] = [
    QColor("#e74c3c"),
    QColor("#f39c12"),
    QColor("#f1c40f"),
    QColor("#2ecc71"),
    QColor("#1abc9c"),
    QColor("#3498db"),
    QColor("#9b59b6"),
    QColor("#ecf0f1"),
    QColor("#2c3e50"),
    QColor("#000000"),
]

_TOOL_DEFAULT_STROKE_COLORS: dict[str, QColor] = {
    Tool.CROSS: MARK_CROSS_COLOR,
    Tool.CHECKMARK: MARK_CHECKMARK_COLOR,
}


def create_default_style_state() -> StyleState:
    """
    Builds the default draw style shared by image and video editors.

    Returns:
        StyleState: Initial style for newly created annotations.
    """

    return StyleState(
        stroke_color=QColor(DEFAULT_STROKE_COLOR),
        fill_color=QColor(DEFAULT_FILL_COLOR),
        text_color=QColor(DEFAULT_TEXT_COLOR),
        stroke_width=6.0,
        font_size=16,
        font_family="Sans Serif",
        font_bold=False,
        font_italic=False,
        font_underline=False,
        letter_spacing=0.0,
        line_spacing_factor=1.2,
        box_padding=10.0,
        corner_radius=6.0,
        stroke_style=STROKE_STYLE_SOLID,
        text_style=TEXT_STYLE_PLAIN,
    )


def tool_default_stroke_color(tool: str) -> QColor | None:
    """
    Returns the default stroke color for one drawing tool, if any.

    Args:
        tool: Tool identifier.

    Returns:
        QColor | None: Tool-specific default stroke color.
    """

    return _TOOL_DEFAULT_STROKE_COLORS.get(str(tool or "").strip().lower())


def apply_tool_default_colors(tool: str, style: StyleState) -> bool:
    """
    Applies tool-specific default colors to one style state.

    Marks use the stroke color as the visible fill, so both targets are updated.

    Args:
        tool: Active drawing tool identifier.
        style: Style state to update in place.

    Returns:
        bool: True when a tool-specific default color was applied.
    """

    stroke_color = tool_default_stroke_color(tool)
    if stroke_color is None:
        return False
    resolved = QColor(stroke_color)
    style.stroke_color = QColor(resolved)
    style.fill_color = QColor(resolved.red(), resolved.green(), resolved.blue(), 255)
    return True
