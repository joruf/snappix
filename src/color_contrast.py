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
