"""
Shared tool-category definitions and toolbar strip building for the image and
video vector toolbars.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from src.editor_canvas import Tool
from src.tool_icons import build_tool_icon

ToolCategory = tuple[str, list[tuple[str, str]]]

# Shared drawing-tool categories offered by both the image and video vector
# toolbars. Each host prepends/appends its own extra categories (e.g. the
# image editor's pixel-selection "Select"/"Paint" tools, or its "Image"
# category) around this shared core.
SHARED_SHAPE_TOOL_CATEGORIES: list[ToolCategory] = [
    (
        "Shapes",
        [
            (Tool.RECT, "Rectangle"),
            (Tool.ELLIPSE, "Circle"),
            (Tool.TRIANGLE, "Triangle"),
            (Tool.STAR, "Star"),
            (Tool.POLYGON, "Polygon"),
        ],
    ),
    (
        "Lines",
        [
            (Tool.LINE, "Line"),
            (Tool.FREEHAND, "Freehand"),
            (Tool.POLYLINE, "Polyline"),
            (Tool.ARROW, "Arrow"),
            (Tool.DOUBLE_ARROW, "Double Arrow"),
            (Tool.BENT_ARROW, "Bent Arrow"),
        ],
    ),
    (
        "Marks",
        [
            (Tool.CROSS, "Cross"),
            (Tool.CHECKMARK, "Checkmark"),
            (Tool.SPOTLIGHT, "Spotlight"),
            (Tool.STEP, "Step"),
        ],
    ),
    ("Text", [(Tool.TEXT, "Text"), (Tool.CALLOUT, "Callout")]),
]

TOOL_BUTTON_ICON_SIZE = QSize(28, 28)
TOOL_BUTTON_FIXED_SIZE = (38, 34)


def build_tool_category_strip(
    strip: QWidget,
    categories: list[ToolCategory],
    *,
    on_tool_clicked: Callable[[str], None],
    tool_buttons: dict[str, QToolButton],
    tool_button_order: list[str],
    tool_button_to_key: dict[QToolButton, str],
    tooltip_for: Callable[[str, str], str] = lambda tool_key, label: label,
    category_tooltip_for: Callable[[str], str] | None = None,
    event_filter_target: object | None = None,
    configure_button: Callable[[QToolButton], None] | None = None,
    on_button_created: Callable[[str, str], None] | None = None,
) -> list[QGroupBox]:
    """
    Builds one QGroupBox with a row of tool buttons per category.

    Shared between the image and video vector toolbars so button styling
    (icon size, fixed size, object names) stays identical without either
    toolbar reimplementing the loop.

    Args:
        strip: Parent flow-layout strip the category boxes will live in.
        categories: Category title to (tool id, label) tuples.
        on_tool_clicked: Callback invoked with the tool id on button click.
        tool_buttons: Host dict to populate with tool id -> button.
        tool_button_order: Host list to append tool ids to, in build order.
        tool_button_to_key: Host dict to populate with button -> tool id.
        tooltip_for: Resolves the button tooltip text from (tool id, label).
        category_tooltip_for: Optional resolver for the category box tooltip.
        event_filter_target: Optional object to install as each button's event filter.
        configure_button: Optional extra per-button setup hook.
        on_button_created: Optional hook invoked with (tool id, label) per button.

    Returns:
        list[QGroupBox]: One category box per entry in ``categories``.
    """

    category_boxes: list[QGroupBox] = []
    for category_title, tools in categories:
        category_box = QGroupBox(category_title, strip)
        category_box.setObjectName("toolCategoryBox")
        if category_tooltip_for is not None:
            category_box.setToolTip(category_tooltip_for(category_title))
        category_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        category_layout = QHBoxLayout(category_box)
        category_layout.setContentsMargins(4, 10, 4, 4)
        category_layout.setSpacing(4)
        for tool_key, label in tools:
            button = QToolButton(category_box)
            button.setText(label)
            button.setCheckable(True)
            button.setIcon(build_tool_icon(tool_key))
            button.setIconSize(TOOL_BUTTON_ICON_SIZE)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(*TOOL_BUTTON_FIXED_SIZE)
            button.setToolTip(tooltip_for(tool_key, label))
            if configure_button is not None:
                configure_button(button)
            button.clicked.connect(
                lambda _checked=False, t=tool_key: on_tool_clicked(t)
            )
            if event_filter_target is not None:
                button.installEventFilter(event_filter_target)
            tool_buttons[tool_key] = button
            tool_button_order.append(tool_key)
            tool_button_to_key[button] = tool_key
            if on_button_created is not None:
                on_button_created(tool_key, label)
            category_layout.addWidget(button)
        category_boxes.append(category_box)
    return category_boxes
