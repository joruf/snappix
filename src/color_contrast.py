"""
WCAG contrast helpers for keeping UI chrome readable on any theme.

Annotation colors are user content and can be anything, including a color that
happens to match the surface behind it. These helpers let chrome guarantee a
minimum separation without dictating what the user may draw with.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# WCAG 2.1 minimum for non-text UI components and graphical objects.
MIN_UI_CONTRAST = 3.0
# How far a color may be pushed toward the contrasting extreme, in steps.
_ADJUST_STEPS = 10


def relative_luminance(color: QColor) -> float:
    """
    Computes the WCAG relative luminance of one color.

    Args:
        color: Color to measure. Alpha is ignored; blend first if needed.

    Returns:
        float: Relative luminance between 0.0 and 1.0.
    """

    channels = []
    for value in (color.redF(), color.greenF(), color.blueF()):
        channels.append(
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: QColor, second: QColor) -> float:
    """
    Computes the WCAG contrast ratio between two opaque colors.

    Args:
        first: First color.
        second: Second color.

    Returns:
        float: Ratio from 1.0 (identical) to 21.0 (black on white).
    """

    lighter = max(relative_luminance(first), relative_luminance(second))
    darker = min(relative_luminance(first), relative_luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


def blend_over(foreground: QColor, background: QColor) -> QColor:
    """
    Flattens a translucent color onto an opaque background.

    Args:
        foreground: Possibly translucent color.
        background: Opaque backdrop.

    Returns:
        QColor: Opaque result of compositing foreground over background.
    """

    alpha = foreground.alphaF()
    return QColor(
        round(foreground.red() * alpha + background.red() * (1.0 - alpha)),
        round(foreground.green() * alpha + background.green() * (1.0 - alpha)),
        round(foreground.blue() * alpha + background.blue() * (1.0 - alpha)),
    )


def ensure_min_contrast(
    color: QColor,
    background: QColor,
    *,
    minimum: float = MIN_UI_CONTRAST,
) -> QColor:
    """
    Nudges a color until it separates from its background.

    The color is mixed toward white or black -- whichever opposes the
    background -- in small steps, so its hue survives whenever a slight shift
    is already enough. Alpha is preserved.

    Args:
        color: Color to adjust.
        background: Opaque backdrop it must remain readable on.
        minimum: Required contrast ratio.

    Returns:
        QColor: Original color when it already passes, otherwise the first
        stepped variant that does.
    """

    flattened = blend_over(color, background)
    if contrast_ratio(flattened, background) >= minimum:
        return QColor(color)

    target = QColor(255, 255, 255) if relative_luminance(background) < 0.5 else QColor(0, 0, 0)
    for step in range(1, _ADJUST_STEPS + 1):
        ratio = step / _ADJUST_STEPS
        mixed = QColor(
            round(color.red() + (target.red() - color.red()) * ratio),
            round(color.green() + (target.green() - color.green()) * ratio),
            round(color.blue() + (target.blue() - color.blue()) * ratio),
            color.alpha(),
        )
        if contrast_ratio(blend_over(mixed, background), background) >= minimum:
            return mixed

    target.setAlpha(color.alpha())
    return target


# Halo width as a multiple of the annotation's own stroke width. Wide enough to
# read as a separating edge at a glance, narrow enough that it never becomes the
# dominant shape.
HALO_WIDTH_FACTOR = 2.0
# Minimum halo growth in pixels, so a hairline stroke still gets a usable edge.
HALO_MIN_GROWTH = 2.0


def halo_color_for(color: QColor) -> QColor:
    """
    Picks the halo color that separates one annotation color from any backdrop.

    Returns white behind dark annotations and black behind light ones, chosen by
    WCAG luminance rather than by hue. The annotation's own color is never
    altered -- it only gains an edge -- so a deliberate brand red stays exactly
    that red while still reading against a red banner underneath it.

    Maximising contrast against the annotation -- rather than guessing at the
    backdrop, which varies per pixel and is unknowable here -- is what makes this
    robust: if the backdrop resembles the annotation, the halo separates the two;
    if the backdrop instead resembles the halo, then by construction it already
    contrasts with the annotation. One of the two is always visible.

    Args:
        color: The annotation's stroke color.

    Returns:
        QColor: Opaque halo color.
    """

    white = QColor(255, 255, 255)
    black = QColor(0, 0, 0)
    if contrast_ratio(color, white) >= contrast_ratio(color, black):
        return white
    return black


def halo_pen_width(stroke_width: float) -> float:
    """
    Computes the halo pen width for one annotation stroke width.

    Args:
        stroke_width: The annotation's own stroke width in pixels.

    Returns:
        float: Width of the wider pen drawn underneath the stroke.
    """

    width = max(0.0, float(stroke_width))
    return max(width * HALO_WIDTH_FACTOR, width + HALO_MIN_GROWTH)
