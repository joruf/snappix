"""
Shared tool names and help text for tooltips and the tools reference table.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.editor_canvas import Tool


@dataclass(frozen=True)
class ToolHelpEntry:
    """
    Describes one editor drawing or pixel tool for UI help surfaces.

    Attributes:
        tool: Stable tool identifier from ``Tool``.
        name: Display name shown in tooltips and the help table.
        tooltip_blurb: Short action summary used after the name in tooltips.
        description: Fuller explanation for the tools reference table.
        shortcut_hint: Optional shortcut text shown in help UI.
    """

    tool: str
    name: str
    tooltip_blurb: str
    description: str
    shortcut_hint: str = ""


TOOL_HELP_ENTRIES: tuple[ToolHelpEntry, ...] = (
    ToolHelpEntry(
        tool=Tool.SELECT,
        name="Select",
        tooltip_blurb="move/resize annotations (Shift/Ctrl multi-select)",
        description=(
            "Selects annotation objects so you can move or resize them. "
            "Hold Shift or Ctrl to select multiple annotations."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.SELECT_RECT,
        name="Marquee",
        tooltip_blurb="rectangular pixel selection on the image",
        description=(
            "Draws a rectangular pixel selection on the screenshot. "
            "Use Fill, Brush, or Delete on that selection. Hold Shift to add to the selection."
        ),
        shortcut_hint="M",
    ),
    ToolHelpEntry(
        tool=Tool.SELECT_ELLIPSE,
        name="Ellipse Select",
        tooltip_blurb="elliptical pixel selection",
        description=(
            "Draws an elliptical pixel selection on the screenshot. "
            "Hold Shift to add to the existing selection."
        ),
        shortcut_hint="Shift+M",
    ),
    ToolHelpEntry(
        tool=Tool.SELECT_PATH,
        name="Lasso",
        tooltip_blurb="freehand pixel selection; double-click closes",
        description=(
            "Draws a freehand (lasso) pixel selection. Double-click to close the path. "
            "Hold Shift to add to the existing selection."
        ),
        shortcut_hint="L",
    ),
    ToolHelpEntry(
        tool=Tool.MAGIC_WAND,
        name="Magic Wand",
        tooltip_blurb="select similar background colors",
        description=(
            "Selects connected or similar background pixels by color. "
            "Adjust tolerance and Contiguous in the Style panel. Hold Shift to add."
        ),
        shortcut_hint="W",
    ),
    ToolHelpEntry(
        tool=Tool.BRUSH,
        name="Brush",
        tooltip_blurb="freehand paint with Border color; Width sets size",
        description=(
            "Freehand brush on the screenshot using the Border color. "
            "Set thickness with Width. If a pixel selection is active, painting stays inside it."
        ),
        shortcut_hint="B",
    ),
    ToolHelpEntry(
        tool=Tool.BUCKET,
        name="Fill",
        tooltip_blurb="paint selection with Fill color & opacity",
        description=(
            "Fills the active pixel selection with the Fill color and Fill opacity. "
            "Requires a pixel selection first. Raise Fill opacity if the result looks faint."
        ),
        shortcut_hint="G",
    ),
    ToolHelpEntry(
        tool=Tool.RECT,
        name="Rectangle",
        tooltip_blurb="draw a rectangle annotation",
        description="Draws a rectangle annotation on top of the screenshot.",
    ),
    ToolHelpEntry(
        tool=Tool.ELLIPSE,
        name="Ellipse",
        tooltip_blurb="draw an ellipse annotation",
        description="Draws an ellipse or circle annotation on top of the screenshot.",
    ),
    ToolHelpEntry(
        tool=Tool.LINE,
        name="Line",
        tooltip_blurb="draw a straight line",
        description="Draws a straight line annotation.",
    ),
    ToolHelpEntry(
        tool=Tool.ARROW,
        name="Arrow",
        tooltip_blurb="draw an arrow",
        description="Draws an arrow annotation pointing from start to end.",
    ),
    ToolHelpEntry(
        tool=Tool.TEXT,
        name="Text",
        tooltip_blurb="insert a text annotation",
        description="Inserts a text annotation. Edit content and typography in the Text panel.",
    ),
    ToolHelpEntry(
        tool=Tool.FILL_BG,
        name="Bg Fill",
        tooltip_blurb="drag a rectangle to fill the background",
        description=(
            "Fills a dragged rectangle directly on the screenshot background "
            "using the Fill color (no pixel selection required)."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.BLUR,
        name="Blur",
        tooltip_blurb="drag a rectangle to pixelate/redact",
        description="Pixelates a dragged rectangle to hide sensitive content.",
    ),
    ToolHelpEntry(
        tool=Tool.STEP,
        name="Step",
        tooltip_blurb="insert a numbered step badge",
        description="Places a numbered step badge for tutorials and walkthroughs.",
    ),
    ToolHelpEntry(
        tool=Tool.OCR,
        name="OCR",
        tooltip_blurb="select a region and copy recognized text",
        description="Selects a region, recognizes text with OCR, and copies it to the clipboard.",
    ),
    ToolHelpEntry(
        tool=Tool.CROP,
        name="Crop",
        tooltip_blurb="select area; Enter applies, Esc cancels",
        description="Selects a crop area on the canvas. Press Enter to apply or Esc to cancel.",
    ),
)


_TOOL_HELP_BY_ID: dict[str, ToolHelpEntry] = {
    entry.tool: entry for entry in TOOL_HELP_ENTRIES
}


def tool_help_entry(tool: str) -> ToolHelpEntry | None:
    """
    Returns the help entry for one tool identifier.

    Args:
        tool: Tool identifier.

    Returns:
        ToolHelpEntry | None: Matching entry, or None when unknown.
    """

    return _TOOL_HELP_BY_ID.get(tool)


def format_tool_tooltip(tool: str) -> str:
    """
    Builds the short English toolbar tooltip for one tool.

    Args:
        tool: Tool identifier.

    Returns:
        str: Tooltip in ``Name — summary (shortcut)`` form.
    """

    entry = tool_help_entry(tool)
    if entry is None:
        return "Drawing tool"
    text = f"{entry.name} — {entry.tooltip_blurb}"
    if entry.shortcut_hint:
        text = f"{text} ({entry.shortcut_hint})"
    return text


def format_tool_explanation(entry: ToolHelpEntry) -> str:
    """
    Builds the help-table explanation for one tool entry.

    Args:
        entry: Tool help catalog entry.

    Returns:
        str: Explanation including the tool name and optional shortcut.
    """

    text = f"{entry.name} — {entry.description}"
    if entry.shortcut_hint:
        text = f"{text} Shortcut: {entry.shortcut_hint}."
    return text
