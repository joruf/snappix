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
        tooltip_blurb="rectangular pixel selection; menu sets Delete erase mode",
        description=(
            "Draws a rectangular pixel selection on the screenshot. "
            "Use Fill, Brush, or Delete on that selection. "
            "Open the tool menu for Delete erase mode. Hold Shift to add to the selection."
        ),
        shortcut_hint="M",
    ),
    ToolHelpEntry(
        tool=Tool.SELECT_ELLIPSE,
        name="Ellipse Select",
        tooltip_blurb="elliptical pixel selection; menu sets Delete erase mode",
        description=(
            "Draws an elliptical pixel selection on the screenshot. "
            "Hold Shift to add to the existing selection."
        ),
        shortcut_hint="Shift+M",
    ),
    ToolHelpEntry(
        tool=Tool.SELECT_PATH,
        name="Lasso",
        tooltip_blurb="freehand pixel selection; menu sets Delete erase mode",
        description=(
            "Draws a freehand (lasso) pixel selection. Double-click to close the path. "
            "Hold Shift to add to the existing selection."
        ),
        shortcut_hint="L",
    ),
    ToolHelpEntry(
        tool=Tool.MAGIC_WAND,
        name="Magic Wand",
        tooltip_blurb="select similar colors; menu for tolerance & options",

        description=(
            "Selects connected or similar background pixels by color. "
            "Use the tool menu for Tolerance, Contiguous, and Delete erase mode. "
            "Hold Shift to add."
        ),
        shortcut_hint="W",
    ),
    ToolHelpEntry(
        tool=Tool.BRUSH,
        name="Brush",
        tooltip_blurb="soft freehand paint; tool menu: Width + Hard",
        description=(
            "Freehand soft brush on the screenshot using the Border color and opacity. "
            "Open the Brush tool menu for Width and Hard (edge softness). "
            "If a pixel selection is active, painting stays inside it."
        ),
        shortcut_hint="B",
    ),
    ToolHelpEntry(
        tool=Tool.ERASER,
        name="Eraser",
        tooltip_blurb="soft freehand erase; tool menu: Width + Hard",
        description=(
            "Soft eraser that removes screenshot pixels. "
            "Open the Eraser tool menu for Width and Hard. "
            "Border opacity controls erase strength. Clips to an active pixel selection."
        ),
        shortcut_hint="E",
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
        tool=Tool.EYEDROPPER,
        name="Color Picker",
        tooltip_blurb="sample document color into Border or Fill",
        description=(
            "Samples a color from the screenshot into Border or Fill "
            "(pipette / color picker). Use the tool menu to choose the target."
        ),
        shortcut_hint="I",
    ),
    ToolHelpEntry(
        tool=Tool.RECT,
        name="Rectangle",
        tooltip_blurb="draw a rectangle; tool menu: Width, Style, Radius",
        description=(
            "Draws a rectangle annotation on top of the screenshot. "
            "Open the tool menu for Width, line Style, and corner Radius "
            "(0 = sharp corners)."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.ELLIPSE,
        name="Ellipse",
        tooltip_blurb="draw an ellipse; tool menu: Width + Style",
        description=(
            "Draws an ellipse or circle annotation on top of the screenshot. "
            "Open the tool menu for Width and line Style (solid/dash/dot)."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.TRIANGLE,
        name="Triangle",
        tooltip_blurb="draw a triangle; tool menu: Width + Style",
        description="Draws a triangle annotation for warnings and directional callouts.",
    ),
    ToolHelpEntry(
        tool=Tool.STAR,
        name="Star",
        tooltip_blurb="draw a star badge; tool menu: Width + Style",
        description="Draws a star badge to draw attention to an area.",
    ),
    ToolHelpEntry(
        tool=Tool.POLYGON,
        name="Polygon",
        tooltip_blurb="click points to draw a polygon; Enter/double-click finishes",
        description=(
            "Draws a free polygon by clicking vertices. "
            "Double-click or press Enter to close; Esc cancels."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.LINE,
        name="Line",
        tooltip_blurb="draw a straight line; tool menu: Width + Style",
        description=(
            "Draws a straight line annotation. "
            "Open the tool menu for Width and line Style (solid/dash/dot)."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.POLYLINE,
        name="Polyline",
        tooltip_blurb="click points for a bent path; Enter/double-click finishes",
        description=(
            "Draws an open multi-segment path by clicking points. "
            "Double-click or press Enter to finish; Esc cancels."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.ARROW,
        name="Arrow",
        tooltip_blurb="draw an arrow; tool menu: Width + Style",
        description=(
            "Draws an arrow annotation pointing from start to end. "
            "Open the tool menu for Width and line Style (solid/dash/dot)."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.DOUBLE_ARROW,
        name="Double Arrow",
        tooltip_blurb="draw a double-headed arrow; tool menu: Width + Style",
        description="Draws a double-headed arrow useful for distances and relationships.",
    ),
    ToolHelpEntry(
        tool=Tool.BENT_ARROW,
        name="Bent Arrow",
        tooltip_blurb="click points for a bent arrow; Enter/double-click finishes",
        description=(
            "Draws a multi-segment arrow that can bend around objects. "
            "Double-click or press Enter to finish; Esc cancels."
        ),
    ),
    ToolHelpEntry(
        tool=Tool.SPOTLIGHT,
        name="Spotlight",
        tooltip_blurb="dim surroundings and keep a focus area bright",
        description="Dims the surrounding screenshot while keeping a dragged focus region bright.",
    ),
    ToolHelpEntry(
        tool=Tool.CROSS,
        name="Cross",
        tooltip_blurb="draw an X mark",
        description="Draws an X / cross mark to indicate errors or rejected items.",
    ),
    ToolHelpEntry(
        tool=Tool.CHECKMARK,
        name="Checkmark",
        tooltip_blurb="draw a checkmark",
        description="Draws a checkmark to indicate success or approved items.",
    ),
    ToolHelpEntry(
        tool=Tool.TEXT,
        name="Text",
        tooltip_blurb="insert a text annotation",
        description="Inserts a text annotation. Use the Text tool menu for font, size, style, and spacing.",
    ),
    ToolHelpEntry(
        tool=Tool.CALLOUT,
        name="Callout",
        tooltip_blurb="insert a speech-bubble callout",
        description=(
            "Inserts text inside a speech bubble callout. "
            "The Bubble style under Text uses the same container."
        ),
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
        tooltip_blurb="pixelate/redact; menu sets pixel block size",
        description=(
            "Pixelates a dragged rectangle to hide sensitive content. "
            "Open the tool menu to set the pixel block size."
        ),
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
        tooltip_blurb="select area; Enter or Crop click applies, Esc cancels",
        description=(
            "Selects a crop area on the canvas. Press Enter or click Crop again to apply, "
            "or Esc to cancel."
        ),
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
