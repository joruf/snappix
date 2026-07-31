"""
Shared formatting helpers for the editors' selection footer.

Both editors report the selected object's geometry the same way, so the
formatting lives here rather than in either window.
"""

from __future__ import annotations

from typing import Any

# Beyond this many vertices the footer lists only the first few, otherwise a
# traced polyline would push everything else out of the status bar.
MAX_LISTED_VERTICES = 12


def format_pixels(value: float | int) -> str:
    """
    Renders one measurement as whole pixels.

    Screen geometry is measured in device pixels, so a fractional value like
    ``195.4`` is noise from scene math rather than something a user can act on.

    Args:
        value: Measurement in pixels.

    Returns:
        str: Rounded value without a unit suffix.
    """

    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return "0"


def format_pixel_pair(first: float | int, second: float | int) -> str:
    """
    Renders an x/y pair as ``10x10px``.

    Args:
        first: Horizontal component.
        second: Vertical component.

    Returns:
        str: Combined measurement with a single ``px`` suffix.
    """

    return f"{format_pixels(first)}x{format_pixels(second)}px"


def format_vertex_list(points: Any) -> str:
    """
    Renders a polygon/polyline vertex list for the footer.

    Args:
        points: Sequence of ``(x, y)`` pairs, or None when the shape has none.

    Returns:
        str: ``pts:(x/y):10x10px,20x30px`` style summary, empty when there are
        no usable vertices.
    """

    if not isinstance(points, (list, tuple)) or not points:
        return ""

    rendered: list[str] = []
    for point in points:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            x_value, y_value = point[0], point[1]
        elif hasattr(point, "x") and hasattr(point, "y"):
            x_value, y_value = point.x(), point.y()
        else:
            continue
        rendered.append(format_pixel_pair(x_value, y_value))

    if not rendered:
        return ""

    total = len(rendered)
    if total > MAX_LISTED_VERTICES:
        shown = ",".join(rendered[:MAX_LISTED_VERTICES])
        return f"pts({total})(x/y):{shown},…"
    return f"pts({total})(x/y):{','.join(rendered)}"
